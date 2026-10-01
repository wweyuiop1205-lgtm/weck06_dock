"""Human review boundary between analyzed news and confirmed risk events."""

from __future__ import annotations

import sqlite3

from backend import database
from backend.access_control import RISK_ANALYSIS_READ, RISK_WORKSPACE_WRITE, require_capability
from backend.news_store import now
from backend.risk_contract import validate_event


def _news_rows(conn: sqlite3.Connection, *, news_id: int | None = None, limit: int = 100) -> list[dict]:
    conn.row_factory = sqlite3.Row
    where = "n.id=?" if news_id is not None else "1=1"
    params = (news_id,) if news_id is not None else (max(1, min(int(limit), 200)),)
    sql = f"""SELECT n.id,n.title,n.summary,n.url,n.source,n.published_at,n.fetched_at,
                     n.analysis_status,n.analysis_error,n.analysis_summary,n.analysis_country,
                     n.analysis_region,n.category,n.is_relevant,n.estimated_delay,n.analyzed_at,
                     n.review_status,n.reviewed_by,n.reviewed_at,n.review_note,
                     (SELECT MIN(e.id) FROM supply_chain_events e WHERE e.news_id=n.id) AS event_id,
                     (SELECT 1 FROM supply_chain_events e JOIN risk_event_retractions r ON r.event_id=e.id
                      WHERE e.news_id=n.id LIMIT 1) AS event_retracted
              FROM supply_chain_news n WHERE {where}
              ORDER BY COALESCE(NULLIF(n.published_at,''),n.fetched_at) DESC,n.id DESC"""
    if news_id is None:
        sql += " LIMIT ?"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def list_news_for_review(*, actor: str, limit: int = 100) -> list[dict]:
    require_capability(actor, RISK_ANALYSIS_READ)
    with sqlite3.connect(database.DB_FILE) as conn:
        return _news_rows(conn, limit=limit)


def get_news_review_history(*, actor: str, news_id: int) -> list[dict]:
    require_capability(actor, RISK_ANALYSIS_READ)
    with sqlite3.connect(database.DB_FILE) as conn:
        if conn.execute("SELECT 1 FROM supply_chain_news WHERE id=?", (news_id,)).fetchone() is None:
            raise ValueError("找不到新聞。")
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(
            """SELECT action_id,action,actor,note,event_id,recorded_at
               FROM news_review_actions WHERE news_id=? ORDER BY action_id""", (news_id,)
        ).fetchall()]


def review_news(*, actor: str, news_id: int, action: str, note: str = "") -> dict:
    """Confirm one analyzed article as an event, or dismiss it with an audit reason."""
    principal = require_capability(actor, RISK_WORKSPACE_WRITE)
    if action not in {"confirm", "dismiss"}:
        raise ValueError("新聞審查結果必須是 confirm 或 dismiss。")
    note = str(note or "").strip()
    if len(note) > 1000:
        raise ValueError("審查備註過長。")
    with database.transaction(immediate=True) as conn:
        row = conn.execute(
            """SELECT id,title,analysis_status,is_relevant,estimated_delay,category,
                      analysis_region,analysis_country,review_status
               FROM supply_chain_news WHERE id=?""",
            (news_id,),
        ).fetchone()
        if row is None:
            raise ValueError("找不到新聞。")
        existing_event = conn.execute(
            "SELECT id FROM supply_chain_events WHERE news_id=? ORDER BY id LIMIT 1", (news_id,)
        ).fetchone()
        reviewed_at = now()
        if action == "dismiss":
            if existing_event is not None or row[8] == "confirmed":
                raise ValueError("已登錄的新聞不能略過；請走事件更正流程。")
            if row[8] == "dismissed":
                return _news_rows(conn, news_id=news_id)[0]
            if not note:
                raise ValueError("略過新聞時必須填寫原因。")
            conn.execute(
                """UPDATE supply_chain_news SET review_status='dismissed',
                   reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?""",
                (principal.username, reviewed_at, note, news_id),
            )
            conn.execute(
                "INSERT INTO news_review_actions(news_id,action,actor,note,event_id,recorded_at) VALUES (?,'dismiss',?,?,NULL,?)",
                (news_id, principal.username, note, reviewed_at),
            )
        else:
            if existing_event is not None and row[8] == "confirmed":
                return _news_rows(conn, news_id=news_id)[0]
            if row[2] != "succeeded" or row[3] != 1 or row[4] is None:
                raise ValueError("只有分析成功、相關且有延遲估計的新聞可確認為事件。")
            if existing_event is None:
                event_type, region, country, days, description, source_news_id = validate_event(
                    conn, row[5], row[6], row[7], row[4],
                    f"【新聞人工確認】{str(row[1] or '').strip()[:400]}", news_id,
                )
                conn.execute(
                    """INSERT INTO supply_chain_events
                       (event_type,region,country,impact_days,description,created_at,news_id)
                       VALUES (?,?,?,?,?,?,?)""",
                    (event_type, region, country, days, description, reviewed_at, source_news_id),
                )
            conn.execute(
                """UPDATE supply_chain_news SET review_status='confirmed',
                   reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?""",
                (principal.username, reviewed_at, note, news_id),
            )
            event = conn.execute("SELECT id FROM supply_chain_events WHERE news_id=? ORDER BY id LIMIT 1", (news_id,)).fetchone()
            conn.execute(
                "INSERT INTO news_review_actions(news_id,action,actor,note,event_id,recorded_at) VALUES (?,'confirm',?,?,?,?)",
                (news_id, principal.username, note, event[0] if event else None, reviewed_at),
            )
        return _news_rows(conn, news_id=news_id)[0]
