import argparse, json, os, re, shutil, time, random
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from database import (
    init_db, get_session, Leaflet, Promotion, PriceHistory,
    find_or_create_product, purge_expired,
)

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-3.1-flash-lite"

PROMPT = """\
Jesteś precyzyjnym systemem ekstrakcji danych z obrazów (OCR i rozumienie układu).
Przeanalizuj zdjęcie strony z gazetki Biedronka i wyciągnij dane o produktach.

ZASADY:
1. Jeśli strona to okładka, przepis, reklama bez produktów i cen — zwróć pustą listę "produkty". Nie zmyślaj.
2. Rozróżniaj typy ofert. Cena bez przekreśleń/warunków = "cena_regularna". Z promocją = "promocja".
3. Zwróć TYLKO poprawny JSON, bez tekstu przed/po.
4. Kategorię przypisuj starannie — "Inne" używaj TYLKO gdy produkt naprawdę nie pasuje do żadnej z poniższych:
   - "Nabiał" — mleko, jogurty, sery, masło, śmietana, kefir, twaróg
   - "Mięso" — mięso, wędliny, drób, kiełbasy, szynki, parówki, kabanosy, ryby
   - "Pieczywo" — chleb, bułki, bagietki, ciasta, torty
   - "Owoce i Warzywa" — owoce, warzywa, sałatki, ziemniaki, grzyby
   - "Napoje" — woda, soki, napoje gazowane, kawa, herbata, energy drinki
   - "Słodycze" — czekolady, cukierki, batony, wafle, ciastka, lody, chipsy
   - "Chemia" — proszki, płyny do prania, środki czystości, kosmetyki, higiena, papier toaletowy
   - "Alkohol" — piwo, wino, wódka, likier
   - "Mrożonki" — mrożone warzywa, ryby mrożone, pizza mrożona, lody (jeśli mrożone)
   - "Inne" — TYLKO jeśli produkt nie pasuje do żadnej powyższej kategorii

JSON:
{
  "strona_zawiera_produkty": true/false,
  "data_waznosci_od": "DD-MM lub null",
  "data_waznosci_do": "DD-MM lub null",
  "produkty": [
    {
      "nazwa_produktu": "Pełna nazwa z marką",
      "kategoria": "jedna z: Nabiał, Mięso, Pieczywo, Owoce i Warzywa, Napoje, Słodycze, Chemia, Alkohol, Mrożonki, Inne",
      "waga_lub_pojemnosc": "np. 1 L, 500 g lub null",
      "typ_oferty": "promocja|cena_regularna",
      "cena_glowna_widoczna": "np. 5.99",
      "warunek_promocji": "np. PRZY ZAKUPIE 2 lub null",
      "najnizsza_cena_z_30_dni": "np. 5.92 lub null",
      "cena_za_1_sztuke_regularna": "lub null"
    }
  ]
}
"""

MAX_RETRIES = 5
BASE_RETRY_DELAY = 4

RETRIABLE_PATTERNS = ["429", "rate", "quota", "503", "overload", "unavailable", "internal", "capacity"]


def _is_retriable(error_msg: str) -> bool:
    err_lower = error_msg.lower()
    return any(p in err_lower for p in RETRIABLE_PATTERNS)


def parse_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", ".").replace("zł", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def parse_date_from_label(label: str, year: int = None) -> date | None:
    if not label:
        return None
    year = year or date.today().year
    match = re.search(r"(\d{2})-(\d{2})", label)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def parse_validity_date(dd_mm: str, year: int = None) -> date | None:
    if not dd_mm:
        return None
    year = year or date.today().year
    match = re.match(r"(\d{2})-(\d{2})", str(dd_mm).strip())
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def is_folder_expired(date_label: str) -> bool:
    if not date_label:
        return False
    if date_label.upper().startswith("OD"):
        return False
    parsed = parse_date_from_label(date_label)
    if parsed and parsed < date.today():
        return True
    return False


def process_image(session, leaflet, img_path, image_url=None):
    print(f"    [Obraz] {img_path.name} ... ", end="", flush=True)

    uploaded = None
    try:
        uploaded = client.files.upload(file=str(img_path))
    except Exception as e:
        print(f"Upload failed: {e}")
        return False

    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[uploaded, PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(response.text)
            break
        except Exception as e:
            err = str(e)
            if _is_retriable(err) and attempt < MAX_RETRIES:
                base_delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                jitter = base_delay * random.uniform(-0.3, 0.3)
                delay = max(2, base_delay + jitter)
                print(f"Retry {attempt}/{MAX_RETRIES} za {delay:.0f}s... ", end="", flush=True)
                time.sleep(delay)
            else:
                print(f"{err}")
                return False

    if not data or not data.get("strona_zawiera_produkty"):
        print("Brak produktow")
        return True

    vf = parse_validity_date(data.get("data_waznosci_od"))
    vt = parse_validity_date(data.get("data_waznosci_do"))
    if vf and not leaflet.valid_from:
        leaflet.valid_from = vf
    if vt and not leaflet.valid_to:
        leaflet.valid_to = vt

    products_found = data.get("produkty", [])
    added = 0
    for prod in products_found:
        name = prod.get("nazwa_produktu")
        if not name:
            continue
        product = find_or_create_product(session, name=name,
            category=prod.get("kategoria"), weight_or_volume=prod.get("waga_lub_pojemnosc"))
        if not product:
            continue

        existing_promo = session.query(Promotion).filter_by(
            leaflet_id=leaflet.id,
            product_id=product.id,
            source_image=img_path.name,
        ).first()
        if existing_promo:
            continue

        main_price = parse_price(prod.get("cena_glowna_widoczna"))
        session.add(Promotion(
            leaflet_id=leaflet.id, product_id=product.id,
            offer_type=prod.get("typ_oferty", "cena_regularna"),
            main_price=main_price,
            regular_unit_price=parse_price(prod.get("cena_za_1_sztuke_regularna")),
            promotion_condition=prod.get("warunek_promocji"),
            lowest_price_30d=parse_price(prod.get("najnizsza_cena_z_30_dni")),
            source_image=img_path.name,
            image_url=image_url,
        ))
        if main_price is not None:
            observed = leaflet.valid_from or parse_date_from_label(leaflet.date_label) or date.today()
            existing_ph = session.query(PriceHistory).filter_by(
                product_id=product.id,
                leaflet_id=leaflet.id,
                observed_date=observed,
            ).first()
            if not existing_ph:
                session.add(PriceHistory(product_id=product.id, price=main_price,
                    observed_date=observed, leaflet_id=leaflet.id))
        added += 1

    session.flush()
    print(f"Dodano {added} nowych / {len(products_found)} znalezionych")
    return True


def process_leaflets(leaflet_dir="biedronka/gazetki", db_path="biedronka.db"):
    session = get_session(db_path)
    base = Path(leaflet_dir)

    if not base.exists():
        print(f"Nie znaleziono katalogu: {base}")
        return

    print("Czyszczenie przeterminowanych promocji...")
    stats = purge_expired(session)
    if any(stats.values()):
        print(f"   Usunieto: {stats['leaflets']} gazetek, {stats['promotions']} promocji, "
              f"{stats['price_history']} historii, {stats['products']} produktow")
    else:
        print("   Baza czysta.")

    folders = sorted(f for f in base.iterdir() if f.is_dir())
    print(f"\nZnaleziono {len(folders)} folderow w {base}")

    processed_count = 0
    skipped = 0
    deleted = 0

    for folder in folders:
        parts = folder.name.rsplit(" ", 1)
        if len(parts) != 2:
            print(f"Dziwna nazwa, pomijam: {folder.name}")
            continue

        date_label, ext_id = parts

        expired = False
        if is_folder_expired(date_label):
            expired = True
        else:
            existing_check = session.query(Leaflet).filter_by(leaflet_id=ext_id).first()
            if existing_check and existing_check.valid_to and existing_check.valid_to < date.today():
                expired = True

        if expired:
            shutil.rmtree(folder, ignore_errors=True)
            print(f"Usunieto nieaktualna gazetke: {folder.name}")
            skipped += 1
            deleted += 1
            continue

        existing = session.query(Leaflet).filter_by(leaflet_id=ext_id).first()
        if existing and existing.processed:
            missing_urls = session.query(Promotion).filter(
                Promotion.leaflet_id == existing.id,
                Promotion.image_url.is_(None),
                Promotion.source_image.isnot(None),
            ).all()
            if missing_urls:
                urls_file = folder / "_urls.json"
                if urls_file.exists():
                    with open(urls_file, encoding="utf-8") as f:
                        urls_map = json.load(f)
                    updated = 0
                    for promo in missing_urls:
                        url = urls_map.get(promo.source_image)
                        if url:
                            promo.image_url = url
                            updated += 1
                    if updated:
                        session.commit()
                        print(f"Uzupelniono {updated} URL-i obrazow: {folder.name}")
                    else:
                        print(f"Juz przetworzona: {folder.name}")
                else:
                    print(f"Juz przetworzona: {folder.name}")
            else:
                print(f"Juz przetworzona: {folder.name}")
            continue

        print(f"Przetwarzam: {folder.name}")
        if not existing:
            leaflet = Leaflet(leaflet_id=ext_id, date_label=date_label, folder_path=str(folder))
            session.add(leaflet)
            session.flush()
        else:
            leaflet = existing

        images = sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg"))
        total = len(images)
        failed_pages = []

        urls_map = {}
        urls_file = folder / "_urls.json"
        if urls_file.exists():
            with open(urls_file, encoding="utf-8") as f:
                urls_map = json.load(f)

        for i, img in enumerate(images):
            print(f"  [{i+1}/{total}] ", end="")
            success = process_image(session, leaflet, img, image_url=urls_map.get(img.name))
            if not success:
                failed_pages.append(img.name)
            time.sleep(1)

        if not failed_pages:
            leaflet.processed = True
            print(f"  Gazetka kompletna ({total} stron)")
        else:
            print(f"  {len(failed_pages)}/{total} stron nie udalo sie — "
                  f"gazetka NIE oznaczona jako przetworzona (retry przy nastepnym uruchomieniu)")
            print(f"     Nieudane: {', '.join(failed_pages)}")

        session.commit()
        processed_count += 1

    print(f"\nGotowe! Przetworzono {processed_count} gazetek.")
    if deleted:
        print(f"Usunieto {deleted} nieaktualnych folderow z dysku.")
    if skipped:
        print(f"Pominieto {skipped} przeterminowanych.")
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--leaflet-dir", default="biedronka/gazetki")
    parser.add_argument("--db", default="biedronka.db")
    parser.add_argument("--purge", action="store_true")
    args = parser.parse_args()

    if args.purge:
        s = get_session(args.db)
        print("Czyszczenie...")
        st = purge_expired(s)
        print(f"   Gazetki: {st['leaflets']}, Promocje: {st['promotions']}, "
              f"Historia: {st['price_history']}, Produkty: {st['products']}")
        s.close()
    else:
        process_leaflets(args.leaflet_dir, args.db)
