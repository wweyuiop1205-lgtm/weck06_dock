"""Authenticated ERP API. Domain authorization stays in backend services."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import sqlite3

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend import database
from backend.access_control import (
    APPROVAL_QUEUE_READ,
    PROPOSAL_EVIDENCE_READ,
    RISK_ANALYSIS_READ,
    RISK_OVERVIEW_READ,
    RISK_WHAT_IF_RUN,
    RISK_WORKSPACE_WRITE,
    AccessContext,
    load_principal,
    require_capability,
)
from backend.auth import check_login
from backend.decision_evidence import (
    add_outcome_feedback,
    build_heatmap_alert_draft,
    build_what_if_decision_draft,
    create_decision_record,
    decide_decision_record,
    get_decision_record,
    get_what_if_erp_snapshot,
    list_decision_records,
)
from backend.l1_monitoring import get_latest_event_alerts, get_latest_risk_summary
from backend.news_review import get_news_review_history, list_news_for_review, review_news
from backend.supply_chain_risk import (
    add_risk_event,
    capture_what_if_erp_evidence,
    get_region_exposure,
    get_retracted_risk_events,
    get_risk_events_list,
    get_risk_heatmap_data,
    get_suppliers_for_map,
    retract_risk_event,
    what_if_simulation,
)
from backend.supply_chain_news import refresh_news_for_countries
from backend.purchase_proposals import (
    ApprovalDecision,
    decide_purchase_proposal,
    get_purchase_operation_timeline,
    get_purchase_proposal_evidence,
    list_alternative_suppliers,
    list_impacted_purchase_options,
    prepare_alternative_purchase_proposal,
    proposal_operation_id,
    submit_purchase_proposal,
)


SESSION_COOKIE = "erp_session"
SESSION_HOURS = 8
COOKIE_SECURE = os.getenv("ERP_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    with sqlite3.connect(database.DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS web_sessions (
            token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
            csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL
        )""")
    yield


app = FastAPI(title="ERP API", version="0.1.0", lifespan=lifespan)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)


class ProposalBody(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=80)
    affected_po_id: str
    product_id: str
    source_po_item_id: int
    alternative_supplier_id: str
    alternative_supplier_product_id: int
    reason: str = Field(min_length=1, max_length=1000)
    estimated_delay_days: int | None = Field(default=None, ge=0, le=3650)
    source_event_id: int | None = None


class DecisionBody(BaseModel):
    outcome: str
    reason: str = ""


class RiskEventBody(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=100)
    country: str = Field(default="", max_length=100)
    impact_days: int = Field(ge=0, le=365)
    description: str = Field(min_length=1, max_length=2000)


class RetractEventBody(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class WhatIfBody(BaseModel):
    question: str = Field(min_length=5, max_length=1000)


class RecordDecisionBody(BaseModel):
    outcome: str
    reason: str = Field(default="", max_length=2000)


class FeedbackBody(BaseModel):
    outcome: str
    action_taken: str = Field(min_length=1, max_length=2000)
    outcome_evidence: str = Field(min_length=1, max_length=2000)
    note: str = Field(default="", max_length=2000)


class NewsRefreshBody(BaseModel):
    within_days: int = Field(default=7, ge=1, le=90)
    max_per_country: int = Field(default=8, ge=1, le=15)


class NewsReviewBody(BaseModel):
    action: str
    note: str = Field(default="", max_length=1000)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session(request: Request) -> tuple[AccessContext, str]:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(401, "請先登入")
    with sqlite3.connect(database.DB_FILE) as conn:
        row = conn.execute(
            "SELECT username, csrf_token, expires_at FROM web_sessions WHERE token_hash=?",
            (_hash(token),),
        ).fetchone()
    if row is None or datetime.fromisoformat(row[2]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "登入已失效")
    principal = load_principal(row[0])
    if principal is None:
        raise HTTPException(401, "登入已失效")
    return principal, row[1]


def current_principal(request: Request) -> AccessContext:
    return _session(request)[0]


def modifying_principal(
    request: Request, x_csrf_token: str | None = Header(default=None)
) -> AccessContext:
    principal, expected_hash = _session(request)
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, expected_hash):
        raise HTTPException(403, "CSRF 驗證失敗")
    return principal


def _actor(principal: AccessContext) -> str:
    return principal.username


@app.exception_handler(PermissionError)
async def permission_error(_request: Request, _exc: PermissionError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403, content={"detail": "沒有操作權限"})


@app.exception_handler(ValueError)
async def value_error(_request: Request, exc: ValueError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready():
    try:
        with sqlite3.connect(database.DB_FILE, timeout=2) as conn:
            conn.execute("SELECT 1 FROM app_metadata LIMIT 1").fetchone()
    except sqlite3.Error:
        raise HTTPException(503, "資料庫尚未就緒")
    return {"status": "ready"}


@app.post("/api/v1/session")
def login(body: LoginBody, response: Response):
    if check_login(body.username, body.password) is None:
        raise HTTPException(401, "帳號或密碼錯誤")
    principal = load_principal(body.username)
    if principal is None:
        raise HTTPException(403, "帳號尚未配置組織與權限")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    with sqlite3.connect(database.DB_FILE) as conn:
        conn.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (datetime.now(timezone.utc).isoformat(),))
        conn.execute(
            "INSERT INTO web_sessions(token_hash,username,csrf_token,expires_at) VALUES (?,?,?,?)",
            (_hash(token), principal.username, csrf, expires.isoformat()),
        )
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE,
        samesite="lax", path="/api/v1", max_age=SESSION_HOURS * 3600,
    )
    return {"user": asdict(principal), "csrf_token": csrf}


@app.get("/api/v1/session")
def get_session(request: Request):
    principal, csrf = _session(request)
    return {"user": asdict(principal), "csrf_token": csrf}


@app.delete("/api/v1/session")
def logout(request: Request, response: Response, _principal: AccessContext = Depends(modifying_principal)):
    with sqlite3.connect(database.DB_FILE) as conn:
        conn.execute("DELETE FROM web_sessions WHERE token_hash=?", (_hash(request.cookies[SESSION_COOKIE]),))
    response.delete_cookie(SESSION_COOKIE, path="/api/v1")
    return {"status": "logged_out"}


@app.get("/api/v1/l1/alerts")
def alerts(since_days: int = 30, limit: int = 10, principal: AccessContext = Depends(current_principal)):
    return get_latest_event_alerts(actor=_actor(principal), since_days=min(max(since_days, 0), 365), limit=min(max(limit, 1), 100))


@app.get("/api/v1/l1/summary")
def summary(principal: AccessContext = Depends(current_principal)):
    return get_latest_risk_summary(actor=_actor(principal))


@app.get("/api/v1/risk/map")
def risk_map(principal: AccessContext = Depends(current_principal)):
    require_capability(_actor(principal), RISK_OVERVIEW_READ)
    return get_risk_heatmap_data()


@app.get("/api/v1/risk/map/exposure")
def risk_map_exposure(region_key: str, principal: AccessContext = Depends(current_principal)):
    require_capability(_actor(principal), RISK_ANALYSIS_READ)
    if not any(item["region_key"] == region_key for item in get_risk_heatmap_data()):
        raise HTTPException(404, "找不到供應據點")
    return get_region_exposure(region_key)


@app.get("/api/v1/risk/events")
def risk_events(limit: int = 30, principal: AccessContext = Depends(current_principal)):
    require_capability(_actor(principal), RISK_OVERVIEW_READ)
    frame = get_risk_events_list(limit=min(max(limit, 1), 100))
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


@app.get("/api/v1/risk/events/retracted")
def retracted_risk_events(limit: int = 30, principal: AccessContext = Depends(current_principal)):
    return get_retracted_risk_events(actor=_actor(principal), limit=limit)


@app.post("/api/v1/risk/events/{event_id}/retract")
def retract_risk_event_api(event_id: int, body: RetractEventBody,
                           principal: AccessContext = Depends(modifying_principal)):
    return retract_risk_event(event_id, actor=_actor(principal), reason=body.reason)


@app.get("/api/v1/risk/news")
def risk_news(limit: int = 100, principal: AccessContext = Depends(current_principal)):
    return list_news_for_review(actor=_actor(principal), limit=limit)


@app.post("/api/v1/risk/news/refresh")
def refresh_risk_news(body: NewsRefreshBody, principal: AccessContext = Depends(modifying_principal)):
    require_capability(_actor(principal), RISK_WORKSPACE_WRITE)
    suppliers = get_suppliers_for_map()
    countries = sorted({str(country).strip() for country in suppliers["country"].dropna()
                        if str(country).strip()}) if suppliers is not None and "country" in suppliers else []
    if not countries:
        raise HTTPException(400, "尚無正式供應商國家，無法限定新聞擷取範圍")
    result = refresh_news_for_countries(
        countries, within_days=body.within_days, max_per_country=body.max_per_country,
        actor=_actor(principal), apply_ai_heatmap=False,
    )
    zero_counts = {key: 0 for key in (
        "fetched_count", "saved_count", "duplicate_count", "analyzed_count",
        "failed_count", "pending_count", "fetch_failed_count", "remaining_analysis_count",
    )}
    return {"countries": countries, **zero_counts, **result}


@app.post("/api/v1/risk/news/{news_id}/review")
def decide_risk_news(news_id: int, body: NewsReviewBody, principal: AccessContext = Depends(modifying_principal)):
    return review_news(actor=_actor(principal), news_id=news_id, **body.model_dump())


@app.get("/api/v1/risk/news/{news_id}/history")
def risk_news_review_history(news_id: int, principal: AccessContext = Depends(current_principal)):
    return get_news_review_history(actor=_actor(principal), news_id=news_id)


@app.post("/api/v1/risk/events")
def create_risk_event(body: RiskEventBody, principal: AccessContext = Depends(modifying_principal)):
    event_id = add_risk_event(**body.model_dump(), actor=_actor(principal))
    return {"id": event_id}


@app.post("/api/v1/risk/what-if")
def run_what_if(body: WhatIfBody, principal: AccessContext = Depends(modifying_principal)):
    require_capability(_actor(principal), RISK_WHAT_IF_RUN)
    erp_context = capture_what_if_erp_evidence(actor=_actor(principal))
    answer = what_if_simulation(None, body.question, actor=_actor(principal), evidence=erp_context)
    if not answer or answer.startswith("模擬分析暫時無法產生："):
        raise HTTPException(503, "AI 分析暫時無法產生，請檢查服務設定後重試")
    draft = build_what_if_decision_draft(
        question=body.question, answer=answer,
        model_name=os.getenv("LLM_ANALYSIS_MODEL") or os.getenv("LLM_MODEL") or "configured-llm",
        data_as_of=erp_context["captured_at"],
    )
    record = create_decision_record(actor=_actor(principal), erp_context=erp_context, **draft)
    return {"answer": answer, "decision_record": record}


@app.get("/api/v1/risk/decisions")
def risk_decisions(limit: int = 30, principal: AccessContext = Depends(current_principal)):
    return list_decision_records(actor=_actor(principal), limit=limit)


@app.get("/api/v1/risk/decisions/{decision_id}")
def risk_decision(decision_id: str, principal: AccessContext = Depends(current_principal)):
    return get_decision_record(actor=_actor(principal), decision_id=decision_id)


@app.get("/api/v1/risk/decisions/{decision_id}/erp-evidence")
def risk_decision_erp_evidence(decision_id: str, principal: AccessContext = Depends(current_principal)):
    return get_what_if_erp_snapshot(actor=_actor(principal), decision_id=decision_id)


@app.post("/api/v1/risk/map/{region_key}/decision")
def record_heatmap_decision(region_key: str, principal: AccessContext = Depends(modifying_principal)):
    require_capability(_actor(principal), RISK_ANALYSIS_READ)
    row = next((item for item in get_risk_heatmap_data() if item["region_key"] == region_key), None)
    if row is None:
        raise HTTPException(404, "找不到供應據點")
    draft = build_heatmap_alert_draft(
        region_name=row["display_name"], risk_score=row["risk_pct"],
        ai_summary=row.get("ai_summary"), data_as_of=row.get("updated_at") or None,
    )
    return create_decision_record(actor=_actor(principal), **draft)


@app.post("/api/v1/risk/decisions/{decision_id}/decision")
def decide_risk_record(decision_id: str, body: RecordDecisionBody, principal: AccessContext = Depends(modifying_principal)):
    return decide_decision_record(actor=_actor(principal), decision_id=decision_id, **body.model_dump())


@app.post("/api/v1/risk/decisions/{decision_id}/feedback")
def feedback_risk_record(decision_id: str, body: FeedbackBody, principal: AccessContext = Depends(modifying_principal)):
    return add_outcome_feedback(actor=_actor(principal), decision_id=decision_id, **body.model_dump())


@app.get("/api/v1/l2/impacted-orders")
def impacted_orders(principal: AccessContext = Depends(current_principal)):
    return list_impacted_purchase_options(actor=_actor(principal))


@app.get("/api/v1/l2/alternatives")
def alternatives(affected_po_id: str, product_id: str, source_po_item_id: int, principal: AccessContext = Depends(current_principal)):
    return list_alternative_suppliers(
        affected_po_id=affected_po_id, product_id=product_id,
        source_po_item_id=source_po_item_id, actor=_actor(principal),
    )


@app.post("/api/v1/l2/proposals")
def create_proposal(body: ProposalBody, principal: AccessContext = Depends(modifying_principal)):
    proposal = prepare_alternative_purchase_proposal(**body.model_dump(), actor=_actor(principal))
    result = submit_purchase_proposal(proposal, actor=_actor(principal))
    return {"proposal": asdict(proposal), "submission": {
        "status": result.status, "approval_id": result.approval_id, "message": result.message,
    }}


@app.get("/api/v1/l3/queue")
def approval_queue(principal: AccessContext = Depends(current_principal)):
    require_capability(_actor(principal), APPROVAL_QUEUE_READ)
    from backend.agent_logger import get_pending_approvals
    return [
        {key: item[key] for key in ("approval_id", "operation_id", "requester_username", "status", "created_at")}
        for item in get_pending_approvals(status_filter="pending")
        if str(item.get("operation_id") or "").startswith("proposal:create-po:")
    ]


@app.get("/api/v1/proposals/{proposal_id}")
def proposal_evidence(proposal_id: str, principal: AccessContext = Depends(current_principal)):
    proposal = get_purchase_proposal_evidence(proposal_id, actor=_actor(principal))
    if proposal is None:
        raise HTTPException(404, "找不到提案")
    return asdict(proposal)


@app.post("/api/v1/l3/proposals/{proposal_id}/decision")
def decision(proposal_id: str, body: DecisionBody, principal: AccessContext = Depends(modifying_principal)):
    result = decide_purchase_proposal(
        ApprovalDecision(proposal_id=proposal_id, outcome=body.outcome, reason=body.reason),
        actor=_actor(principal),
    )
    return {"status": result.status, "approval_id": result.approval_id, "message": result.message}


@app.get("/api/v1/l3/proposals/{proposal_id}/timeline")
def timeline(proposal_id: str, principal: AccessContext = Depends(current_principal)):
    require_capability(_actor(principal), PROPOSAL_EVIDENCE_READ)
    return get_purchase_operation_timeline(proposal_operation_id(proposal_id), actor=_actor(principal))
