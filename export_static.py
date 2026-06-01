import argparse
import json
import os
from datetime import date, datetime

from sqlalchemy import text

from database import init_db, get_session


def _json_serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Typ {type(obj)} nie jest serializowalny")


def export_promotions(session):
    query = """
        SELECT
            p.id AS product_id, p.name, p.category, p.weight_or_volume,
            pr.main_price, pr.old_price, pr.discount_percentage,
            pr.offer_type, pr.promotion_condition,
            pr.lowest_price_30d, pr.source_image, pr.image_url,
            l.date_label, l.leaflet_id AS ext_leaflet_id,
            l.valid_from, l.valid_to
        FROM promotions pr
        JOIN products p ON pr.product_id = p.id
        JOIN leaflets l ON pr.leaflet_id = l.id
        ORDER BY l.date_label DESC, p.name
    """
    rows = session.execute(text(query)).fetchall()
    today = date.today()

    seen = {}
    for r in rows:
        valid_to_str = str(r.valid_to) if r.valid_to else None
        is_expired = False
        if r.valid_to:
            try:
                is_expired = date.fromisoformat(str(r.valid_to)) < today
            except (ValueError, TypeError):
                pass

        dedup_key = (
            r.product_id,
            r.main_price,
            r.promotion_condition or "",
        )

        if dedup_key in seen:
            entry = seen[dedup_key]
            if r.date_label and r.date_label not in entry["date_labels"]:
                entry["date_labels"].append(r.date_label)
            if r.ext_leaflet_id and r.ext_leaflet_id not in entry["leaflet_ids"]:
                entry["leaflet_ids"].append(r.ext_leaflet_id)
            if r.image_url and not entry.get("image_url"):
                entry["image_url"] = r.image_url
            if r.old_price and not entry.get("old_price"):
                entry["old_price"] = r.old_price
            if r.discount_percentage and not entry.get("discount_percentage"):
                entry["discount_percentage"] = r.discount_percentage
            if r.lowest_price_30d and not entry.get("lowest_price_30d"):
                entry["lowest_price_30d"] = r.lowest_price_30d
            if not entry["is_expired"] and not is_expired:
                pass
            elif not is_expired:
                entry["is_expired"] = False
            if r.valid_from:
                vf = str(r.valid_from)
                if not entry.get("valid_from") or vf < entry["valid_from"]:
                    entry["valid_from"] = vf
            if r.valid_to:
                vt = str(r.valid_to)
                if not entry.get("valid_to") or vt > entry["valid_to"]:
                    entry["valid_to"] = vt
            continue

        seen[dedup_key] = {
            "product_id": r.product_id,
            "name": r.name,
            "category": r.category,
            "weight_or_volume": r.weight_or_volume,
            "main_price": r.main_price,
            "old_price": r.old_price,
            "discount_percentage": r.discount_percentage,
            "offer_type": r.offer_type,
            "promotion_condition": r.promotion_condition,
            "lowest_price_30d": r.lowest_price_30d,
            "source_image": r.source_image,
            "image_url": r.image_url,
            "date_label": r.date_label,
            "date_labels": [r.date_label] if r.date_label else [],
            "leaflet_id": r.ext_leaflet_id,
            "leaflet_ids": [r.ext_leaflet_id] if r.ext_leaflet_id else [],
            "valid_from": str(r.valid_from) if r.valid_from else None,
            "valid_to": valid_to_str,
            "is_expired": is_expired,
        }

    return list(seen.values())


def export_stats(session):
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
    history_dir = os.path.join(out_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

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

    print(f"  Wyeksportowano historie cen dla {len(product_ids)} produktow")
    return len(product_ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="biedronka.db")
    parser.add_argument("--out", default="site/data")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print(f"Eksport danych z {args.db} -> {args.out}/")
    session = get_session(args.db)

    try:
        promotions = export_promotions(session)
        with open(os.path.join(args.out, "promotions.json"), "w", encoding="utf-8") as f:
            json.dump(promotions, f, ensure_ascii=False, indent=2, default=_json_serial)
        print(f"  promotions.json — {len(promotions)} rekordow")

        stats = export_stats(session)
        with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, default=_json_serial)
        print("  stats.json — OK")

        export_histories(session, args.out)
        print("Eksport zakonczony!")
    finally:
        session.close()


if __name__ == "__main__":
    main()
