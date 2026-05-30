"""
dashboard.py — Dashboard Flask do przeglądania promocji z gazetek Biedronki.

Użycie:
    python dashboard.py
"""

import os
from datetime import date

from flask import Flask, render_template, request, jsonify
from sqlalchemy import text

from database import init_db, get_session, purge_expired

app = Flask(__name__)
DB_PATH = os.environ.get("BIEDRONKA_DB", "biedronka.db")


@app.route("/")
def index():
    session = get_session(DB_PATH)
    try:
        categories = [
            row[0] for row in session.execute(
                text("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category")
            ).fetchall()
        ]
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
    finally:
        session.close()

    return render_template("index.html", categories=categories, stats={
        "products": total_products,
        "promotions": total_promos,
        "leaflets": total_leaflets,
        "expired": expired_count,
    })


@app.route("/api/promotions")
def api_promotions():
    session = get_session(DB_PATH)
    category = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()
    hide_expired = request.args.get("hide_expired", "true").strip().lower() == "true"

    try:
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
            WHERE 1=1
        """
        params = {}

        if category:
            query += " AND p.category = :category"
            params["category"] = category
        if search:
            query += " AND LOWER(p.name) LIKE :search"
            params["search"] = f"%{search.lower()}%"
        if hide_expired:
            query += " AND (l.valid_to IS NULL OR l.valid_to >= date('now'))"

        query += " GROUP BY pr.id ORDER BY l.date_label DESC, p.name"
        rows = session.execute(text(query), params).fetchall()

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

        return jsonify(result)
    finally:
        session.close()


@app.route("/api/product/<int:product_id>/history")
def api_product_history(product_id):
    session = get_session(DB_PATH)
    try:
        product_row = session.execute(
            text("SELECT id, name, category, weight_or_volume FROM products WHERE id = :pid"),
            {"pid": product_id},
        ).fetchone()

        if not product_row:
            return jsonify({"error": "Nie znaleziono produktu"}), 404

        history_rows = session.execute(text(
            "SELECT ph.price, ph.observed_date, l.date_label "
            "FROM price_history ph "
            "LEFT JOIN leaflets l ON ph.leaflet_id = l.id "
            "WHERE ph.product_id = :pid ORDER BY ph.observed_date ASC"
        ), {"pid": product_id}).fetchall()

        return jsonify({
            "product": {
                "id": product_row.id, "name": product_row.name,
                "category": product_row.category,
                "weight_or_volume": product_row.weight_or_volume,
            },
            "history": [
                {"date": str(h.observed_date), "price": h.price, "leaflet_label": h.date_label}
                for h in history_rows
            ],
        })
    finally:
        session.close()


@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    """Ręczne usuwanie przeterminowanych danych z poziomu dashboardu."""
    session = get_session(DB_PATH)
    try:
        stats = purge_expired(session)
        return jsonify({"status": "ok", "removed": stats})
    finally:
        session.close()


if __name__ == "__main__":
    init_db(DB_PATH)
    app.run(debug=True, port=5000)
