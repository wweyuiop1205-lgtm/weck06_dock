"""Idempotent, clearly labeled synthetic fixture for the portable meeting demo."""

from __future__ import annotations

from datetime import date
import sqlite3

from backend import database
from backend.decision_evidence import build_what_if_decision_draft, create_decision_record
from backend.news_store import store_analysis, store_raw
from backend.supply_chain_risk import capture_what_if_erp_evidence


def main() -> None:
    if not database.is_demo_mode_enabled() or not database.is_demo_seed_enabled():
        raise RuntimeError("Meeting fixture requires explicit Demo Mode and demo seed")
    database.init_db()
    with sqlite3.connect(database.DB_FILE) as conn:
        product = conn.execute("SELECT product_id FROM inventory ORDER BY product_id LIMIT 1").fetchone()
        original = conn.execute(
            """SELECT supplier_id,country,region FROM suppliers
               WHERE is_official=0 AND COALESCE(country,'')<>'' ORDER BY supplier_id LIMIT 1"""
        ).fetchone()
        alternative = conn.execute(
            """SELECT s.supplier_id FROM suppliers s
               JOIN supplier_products sp ON sp.supplier_id=s.supplier_id
               WHERE s.is_official=1 AND sp.product_id=? ORDER BY s.supplier_id LIMIT 1""",
            (product[0],) if product else ("",),
        ).fetchone()
        if not product or not original or not alternative:
            raise RuntimeError("Demo fixture needs an item and two supplier roles")
        po_id = "DEMO-RISK-PO"
        if conn.execute("SELECT 1 FROM purchase_orders WHERE po_id=?", (po_id,)).fetchone() is None:
            conn.execute(
                """INSERT INTO purchase_orders(po_id,supplier_id,order_date,status,estimated_delay_days)
                   VALUES (?,?,?,?,?)""",
                (po_id, original[0], date.today().isoformat(), "進行中", 5),
            )
            conn.execute(
                "INSERT INTO purchase_order_items(po_id,product_id,qty,unit_price) VALUES (?,?,?,?)",
                (po_id, product[0], 3, 100),
            )
        news_id, _ = store_raw(conn, {
            "country": original[1], "region": original[2],
            "title": "【DEMO 合成資料】港口運輸中斷",
            "summary": "供展示用的假設新聞：供應商所在地的港口運輸可能延遲五天。非真實報導。",
            "url": "demo://meeting/news/port", "source": "合成示範來源（無真實原文）",
            "published_at": date.today().isoformat(), "relevance_tag": "supply_chain",
        })
        store_analysis(conn, news_id, {
            "analysis_status": "succeeded", "is_relevant": True,
            "estimated_delay": 5, "event_type": "交通", "country": original[1],
            "region": original[2], "chinese_summary": "合成示範判讀：運輸中斷可能影響交期。",
        })
    with sqlite3.connect(database.DB_FILE) as conn:
        has_decision = conn.execute("SELECT 1 FROM decision_records WHERE decision_id='DEMO-WHATIF'").fetchone()
    if not has_decision:
        context = capture_what_if_erp_evidence(actor="planner")
        draft = build_what_if_decision_draft(
            question="【DEMO 合成資料】港口延誤五天時哪些採購單需要覆核？",
            answer="合成示範回覆：DEMO-RISK-PO 可能受影響，請人工核對供應商與庫存。",
            model_name="demo-fixture", data_as_of=context["captured_at"],
        )
        create_decision_record(actor="planner", decision_id="DEMO-WHATIF", erp_context=context, **draft)
    print(f"Meeting demo fixture ready: {po_id}; news {news_id}")


if __name__ == "__main__":
    main()
