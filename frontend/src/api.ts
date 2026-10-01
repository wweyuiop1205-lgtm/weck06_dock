export type Principal = { username: string; role: string; name: string; organization_id: string; capabilities: string[] }
export type Alert = { id?: number; news_id?: number; title?: string; event_type?: string; country?: string; region?: string; severity?: string; ack_status?: string; news_source?: string; news_url?: string; url?: string; observed_at?: string; proposal?: unknown }
export type Alerts = { confirmed: Alert[]; candidates: Alert[]; confirmed_count: number; candidate_count: number; highest_severity: string; generated_at: string }
export type Order = { po_id: string; product_id: string; product_name?: string; source_po_item_id: number; qty: number; supplier_name: string; estimated_delay_days?: number; alternative_suggestion?: string; proposal?: { status: string; proposal_id: string } }
export type Supplier = { supplier_product_id: number; supplier_id: string; name: string; price: number; risk_level?: string }
export type Approval = { approval_id: string; operation_id?: string; requester_username?: string; status: string; created_at?: string }
export type RiskPoint = { region_key: string; display_name: string; latitude: number; longitude: number; risk_pct: number; risk_reason: string; ai_summary?: string; updated_at?: string; event_count: number }
export type RiskEvent = { id: number; event_type: string; country: string; region: string; impact_days: number; description: string; created_at: string; news_id?: number; news_title?: string; news_url?: string; news_source?: string; news_published_at?: string; news_fetched_at?: string }
export type RetractedRiskEvent = RiskEvent & { retracted_by: string; reason: string; retracted_at: string }
export type Exposure = { supplier_count: number; official_supplier_count: number; open_po_count: number; open_po_amount: number }
export type DecisionRecord = { decision_id: string; decision_type: string; model_name: string; status: string; created_at: string; ai_output: { recommendation: string; reasoning: string; limitations: string }; evidence_snapshot: { risk_score: number; affected_entity: string; data_as_of: string }; snapshot_digest: string; erp_context_digest?: string | null; feedback: { outcome: string; action_taken: string; outcome_evidence: string }[] }
export type ErpEvidence = { decision_id: string; captured_at: string; context_digest: string; erp_context: { captured_at: string; suppliers: Record<string, unknown>[]; open_purchase_orders: Record<string, unknown>[]; inventory: Record<string, unknown>[] } }
export type NewsItem = { id: number; title?: string; summary?: string; url?: string; source?: string; published_at?: string; fetched_at?: string; analysis_status: string; analysis_error?: string; analysis_summary?: string; analysis_country?: string; analysis_region?: string; category?: string; is_relevant?: number; estimated_delay?: number; analyzed_at?: string; review_status: string; reviewed_by?: string; reviewed_at?: string; review_note?: string; event_id?: number; event_retracted?: number }
export type NewsReviewAction = { action_id: number; action: 'confirm' | 'dismiss'; actor: string; note: string; event_id?: number; recorded_at: string }
export type NewsRefresh = { status: string; countries: string[]; fetched_count: number; saved_count: number; duplicate_count: number; analyzed_count: number; failed_count: number; pending_count: number; fetch_failed_count: number; remaining_analysis_count: number }

let csrf = ''

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD'].includes(method) && !(path === '/session' && method === 'POST')) {
    headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
  return payload as T
}

export function setCsrf(value: string) { csrf = value }
export function clearCsrf() { csrf = '' }
