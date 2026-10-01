"""Create delayed demo purchase orders in the isolated browser-test database."""

from datetime import date
import sqlite3

from backend import database
from backend.decision_evidence import build_what_if_decision_draft, create_decision_record
from backend.news_store import store_analysis, store_raw
from backend.supply_chain_risk import capture_what_if_erp_evidence


def main() -> None:
    database.init_db()
    with sqlite3.connect(database.DB_FILE) as conn:
        product = conn.execute("SELECT product_id FROM inventory LIMIT 1").fetchone()
        alternative = conn.execute("SELECT supplier_id FROM suppliers WHERE is_official=1 LIMIT 1").fetchone()
        if product is None or alternative is None:
            raise RuntimeError("E2E demo seed requires a product and official supplier")
        original = conn.execute(
            "SELECT supplier_id FROM suppliers WHERE supplier_id<>? LIMIT 1", (alternative[0],)
        ).fetchone()
        if original is None:
            raise RuntimeError("E2E demo seed requires a second supplier")

        for po_id, delay_days in (("E2E-DELAYED", 5), ("E2E-REJECTED", 4)):
            if not conn.execute("SELECT 1 FROM purchase_orders WHERE po_id=?", (po_id,)).fetchone():
                conn.execute(
                    "INSERT INTO purchase_orders(po_id,supplier_id,order_date,status,estimated_delay_days) VALUES (?,?,?,?,?)",
                    (po_id, original[0], date.today().isoformat(), "進行中", delay_days),
                )
                conn.execute(
                    "INSERT INTO purchase_order_items(po_id,product_id,qty,unit_price) VALUES (?,?,?,?)",
                    (po_id, product[0], 3, 100),
                )
        country, region = conn.execute(
            "SELECT country,region FROM suppliers WHERE supplier_id=?", (alternative[0],)
        ).fetchone()
        news_id, _ = store_raw(conn, {
            "country": country, "region": region, "title": "E2E 港口運輸中斷",
            "summary": "測試用新聞：港口運輸可能延遲五天。",
            "url": "https://example.invalid/e2e-port", "source": "E2E 測試來源",
            "published_at": date.today().isoformat(), "relevance_tag": "supply_chain",
        })
        store_analysis(conn, news_id, {
            "analysis_status": "succeeded", "is_relevant": True,
            "estimated_delay": 5, "event_type": "交通", "country": country,
            "region": region, "chinese_summary": "測試分析：供應區域運輸延誤。",
        })
    with sqlite3.connect(database.DB_FILE) as conn:
        seeded_decision = conn.execute("SELECT 1 FROM decision_records WHERE decision_id='E2E-WHATIF'").fetchone()
    if not seeded_decision:
        context = capture_what_if_erp_evidence(actor="planner")
        draft = build_what_if_decision_draft(
            question="E2E 港口延誤時哪些採購單受影響？",
            answer="E2E-DELAYED 採購單需人工覆核。",
            model_name="e2e-fixture", data_as_of=context["captured_at"],
        )
        create_decision_record(actor="planner", decision_id="E2E-WHATIF", erp_context=context, **draft)
    print("E2E purchase orders, news and What-if evidence seeded")


if __name__ == "__main__":
    main()
