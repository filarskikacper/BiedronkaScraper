"""
export_static.py — Eksportuje dane z bazy SQLite do statycznych plików JSON.

Generuje:
  site/data/promotions.json  — lista wszystkich aktywnych i nieaktywnych promocji
  site/data/stats.json       — statystyki (liczba produktów, gazetek itd.)
  site/data/history/<id>.json — historia cen per produkt

Użycie:
    python export_static.py [--db biedronka.db] [--out site/data]
"""

import argparse
import json
import os
from datetime import date, datetime

from sqlalchemy import text

from database import init_db, get_session


def _json_serial(obj):
    """Serializacja typów date/datetime do JSON."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Typ {type(obj)} nie jest serializowalny")


def export_promotions(session):
    """Eksportuje wszystkie promocje (aktywne i nieaktywne)."""
    query = """
        SELECT
            p.id AS product_id, p.name, p.category, p.weight_or_volume,
            pr.main_price, pr.offer_type, pr.promotion_condition,
            pr.lowest_price_30d, pr.source_image,
            l.date_label, l.leaflet_id AS ext_leaflet_id,
            l.valid_from, l.valid_to,
            MIN(ph.price) AS min_price_30d
        FROM promotions pr
        JOIN products p ON pr.product_id = p.id
        JOIN leaflets l ON pr.leaflet_id = l.id
        LEFT JOIN price_history ph ON ph.product_id = p.id
            AND ph.observed_date >= date('now', '-30 days')
        GROUP BY pr.id
        ORDER BY l.date_label DESC, p.name
    """
    rows = session.execute(text(query)).fetchall()
    today = date.today()

    result = []
    for r in rows:
        valid_to_str = str(r.valid_to) if r.valid_to else None
        is_expired = False
        if r.valid_to:
            try:
                is_expired = date.fromisoformat(str(r.valid_to)) < today
            except (ValueError, TypeError):
                pass

        result.append({
            "product_id": r.product_id,
            "name": r.name,
            "category": r.category,
            "weight_or_volume": r.weight_or_volume,
            "main_price": r.main_price,
            "offer_type": r.offer_type,
            "promotion_condition": r.promotion_condition,
            "lowest_price_30d": r.lowest_price_30d,
            "min_price_30d_calculated": r.min_price_30d,
            "source_image": r.source_image,
            "date_label": r.date_label,
            "leaflet_id": r.ext_leaflet_id,
            "valid_from": str(r.valid_from) if r.valid_from else None,
            "valid_to": valid_to_str,
            "is_expired": is_expired,
        })
    return result


def export_stats(session):
    """Eksportuje statystyki dashboardu."""
    total_products = session.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0
    total_promos = session.execute(
        text("SELECT COUNT(*) FROM promotions WHERE offer_type = 'promocja'")
    ).scalar() or 0
    total_leaflets = session.execute(
        text("SELECT COUNT(*) FROM leaflets WHERE processed = 1")
    ).scalar() or 0
    expired_count = session.execute(text(
        "SELECT COUNT(*) FROM promotions pr "
        "JOIN leaflets l ON pr.leaflet_id = l.id "
        "WHERE l.valid_to IS NOT NULL AND l.valid_to < date('now')"
    )).scalar() or 0

    categories = [
        row[0] for row in session.execute(
            text("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category")
        ).fetchall()
    ]

    return {
        "products": total_products,
        "promotions": total_promos,
        "leaflets": total_leaflets,
        "expired": expired_count,
        "categories": categories,
        "last_updated": date.today().isoformat(),
    }


def export_histories(session, out_dir):
    """Eksportuje historię cen per produkt do osobnych plików JSON."""
    history_dir = os.path.join(out_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    # Pobierz unikalne ID produktów, które mają historię cen
    product_ids = [
        row[0] for row in session.execute(
            text("SELECT DISTINCT product_id FROM price_history")
        ).fetchall()
    ]

    for pid in product_ids:
        product_row = session.execute(
            text("SELECT id, name, category, weight_or_volume FROM products WHERE id = :pid"),
            {"pid": pid},
        ).fetchone()

        if not product_row:
            continue

        history_rows = session.execute(text(
            "SELECT ph.price, ph.observed_date, l.date_label "
            "FROM price_history ph "
            "LEFT JOIN leaflets l ON ph.leaflet_id = l.id "
            "WHERE ph.product_id = :pid ORDER BY ph.observed_date ASC"
        ), {"pid": pid}).fetchall()

        data = {
            "product": {
                "id": product_row.id,
                "name": product_row.name,
                "category": product_row.category,
                "weight_or_volume": product_row.weight_or_volume,
            },
            "history": [
                {"date": str(h.observed_date), "price": h.price, "leaflet_label": h.date_label}
                for h in history_rows
            ],
        }

        with open(os.path.join(history_dir, f"{pid}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=_json_serial)

    print(f"  Wyeksportowano historię cen dla {len(product_ids)} produktów")
    return len(product_ids)


def main():
    parser = argparse.ArgumentParser(description="Eksport danych do statycznych plików JSON")
    parser.add_argument("--db", default="biedronka.db", help="Ścieżka do bazy SQLite")
    parser.add_argument("--out", default="site/data", help="Katalog wyjściowy")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print(f"Eksport danych z {args.db} -> {args.out}/")
    session = get_session(args.db)

    try:
        # 1. Promocje
        promotions = export_promotions(session)
        with open(os.path.join(args.out, "promotions.json"), "w", encoding="utf-8") as f:
            json.dump(promotions, f, ensure_ascii=False, indent=2, default=_json_serial)
        print(f"  promotions.json — {len(promotions)} rekordów")

        # 2. Statystyki
        stats = export_stats(session)
        with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, default=_json_serial)
        print(f"  stats.json — OK")

        # 3. Historie cen
        export_histories(session, args.out)

        print("Eksport zakończony pomyślnie!")
    finally:
        session.close()


if __name__ == "__main__":
    main()
