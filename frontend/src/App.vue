<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, clearCsrf, setCsrf, type Alerts, type Approval, type DecisionRecord, type ErpEvidence, type Exposure, type NewsItem, type NewsRefresh, type NewsReviewAction, type Order, type Principal, type RetractedRiskEvent, type RiskEvent, type RiskPoint, type Supplier } from './api'

const user = ref<Principal | null>(null)
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const active = ref<'l1' | 'map' | 'news' | 'events' | 'whatif' | 'decisions' | 'l2' | 'l3'>('l1')
const workspacePages = {
  l1: { index: '01 / OBSERVE', title: '全球供應風險總覽', description: '把據點、事件與判讀依據放在同一個視野。從地圖找到受影響地區，再查看證據與後續處置。' },
  map: { index: '02 / MAP', title: '全球曝險地圖', description: '查看供應商所在區域的風險分數，並追溯事件與採購曝險。' },
  news: { index: '03 / VERIFY', title: '情報來源與審查', description: '外部訊號先保留來源，再由人員核實；確認後才建立風險事件。' },
  events: { index: '04 / EVENTS', title: '事件與處置', description: '記錄已確認事件、影響範圍與撤銷歷程。' },
  whatif: { index: '05 / SIMULATE', title: 'What-if 情境推演', description: '使用目前的 ERP 資料模擬供應情境，保留分析時的證據快照。' },
  decisions: { index: '06 / DECIDE', title: '決策與回饋', description: '檢視風險證據、人工處置與後續回饋。' },
  l2: { index: '07 / PROPOSE', title: '替代採購提案', description: '評估備援供應商與受影響採購單，提出方案並送交核准。' },
  l3: { index: '08 / APPROVE', title: '人工核准', description: '覆核提案證據與歷程，再決定是否執行採購。' },
}
const workspacePage = computed(() => workspacePages[active.value])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const alerts = ref<Alerts | null>(null)
const summary = ref<unknown>(null)
const orders = ref<Order[]>([])
const alternatives = ref<Supplier[]>([])
const approvals = ref<Approval[]>([])
const selectedOrder = ref<Order | null>(null)
const selectedSupplierProductId = ref<number | null>(null)
const reason = ref('')
const selectedApproval = ref<Approval | null>(null)
const selectedEvidence = ref<Record<string, unknown> | null>(null)
const rejectionReason = ref('')
const timeline = ref<{ kind: string; receipt_id?: string; summary: string; time: string }[]>([])
const points = ref<RiskPoint[]>([])
const events = ref<RiskEvent[]>([])
const retractedEvents = ref<RetractedRiskEvent[]>([])
const openRetractionId = ref<number | null>(null)
const retractionReasons = ref<Record<number, string>>({})
const decisions = ref<DecisionRecord[]>([])
const selectedPoint = ref<RiskPoint | null>(null)
const exposure = ref<Exposure | null>(null)
const question = ref('')
const whatIfAnswer = ref('')
const selectedRiskDecision = ref<DecisionRecord | null>(null)
const erpEvidence = ref<ErpEvidence | null>(null)
const erpSources = [{ key: 'suppliers', label: '供應商' }, { key: 'open_purchase_orders', label: '未結採購單' }, { key: 'inventory', label: '庫存' }] as const
const riskDecisionReason = ref('')
const feedbackAction = ref('')
const feedbackEvidence = ref('')
const feedbackOutcome = ref('effective')
const newEvent = ref({ event_type: '', country: '', region: '', impact_days: 0, description: '' })
const newsItems = ref<NewsItem[]>([])
const newsFilter = ref<'all' | 'review' | 'failed' | 'confirmed' | 'dismissed'>('review')
const newsDays = ref(7)
const newsRefreshResult = ref<NewsRefresh | null>(null)
const newsNotes = ref<Record<number, string>>({})
const newsHistories = ref<Record<number, NewsReviewAction[]>>({})

const canL1 = computed(() => user.value?.capabilities.includes('risk.overview.read') ?? false)
const canL2 = computed(() => user.value?.capabilities.includes('erp.exchange.propose') ?? false)
const canL3 = computed(() => user.value?.capabilities.includes('approval.queue.read') ?? false)
const canRiskWrite = computed(() => user.value?.capabilities.includes('risk.workspace.write') ?? false)
const canRiskAnalysis = computed(() => user.value?.capabilities.includes('risk.analysis.read') ?? false)
const canWhatIf = computed(() => user.value?.capabilities.includes('risk.what_if.run') ?? false)
const canDecisionRead = computed(() => user.value?.capabilities.includes('decision.evidence.read') ?? false)
const canDecisionWrite = computed(() => user.value?.capabilities.includes('decision.record.write') ?? false)
const highRiskPoints = computed(() => points.value.filter(item => item.risk_pct >= 70).length)
const filteredNews = computed(() => newsItems.value.filter(item => {
  if (newsFilter.value === 'all') return true
  if (newsFilter.value === 'review') return item.analysis_status === 'succeeded' && item.is_relevant === 1 && item.estimated_delay != null && item.review_status === 'pending' && !item.event_id
  if (newsFilter.value === 'failed') return item.analysis_status === 'failed' || item.analysis_status === 'pending' || item.analysis_status === 'legacy_unverified'
  if (newsFilter.value === 'confirmed') return item.review_status === 'confirmed' || !!item.event_id
  return item.review_status === 'dismissed'
}))

function safeNewsUrl(value?: string): string | null {
  try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : null }
  catch { return null }
}

function refreshStatusLabel(status: string): string {
  return ({ succeeded: '已完成', pending_analysis: '待 AI 分析', partial_failure: '部分失敗', busy: '已有更新作業進行中' } as Record<string, string>)[status] || status
}

function pointStyle(point: RiskPoint) {
  return {
    left: `${Math.min(97, Math.max(3, (point.longitude + 180) / 360 * 100))}%`,
    top: `${Math.min(94, Math.max(6, (90 - point.latitude) / 180 * 100))}%`,
    background: point.risk_pct >= 70 ? '#ad5145' : point.risk_pct >= 45 ? '#be7839' : '#66876e',
  }
}

function proposalIdFromOperation(operationId?: string): string | null {
  const prefix = 'proposal:create-po:'
  const suffix = ':v1'
  return operationId?.startsWith(prefix) && operationId.endsWith(suffix)
    ? operationId.slice(prefix.length, -suffix.length) : null
}

function newProposalId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

async function run(task: () => Promise<void>) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await task() } catch (e) { error.value = e instanceof Error ? e.message : '發生錯誤' }
  finally { busy.value = false }
}

async function signIn() {
  await run(async () => {
    const result = await api<{ user: Principal; csrf_token: string }>('/session', {
      method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }),
    })
    user.value = result.user
    setCsrf(result.csrf_token)
    password.value = ''
    showPassword.value = false
    active.value = canL1.value ? 'l1' : canL2.value ? 'l2' : 'l3'
    await refresh()
  })
}

async function signOut() {
  await run(async () => {
    await api('/session', { method: 'DELETE' })
    user.value = null
    showPassword.value = false
    clearCsrf()
    alerts.value = null
    orders.value = []
    approvals.value = []
    points.value = []
    events.value = []
    retractedEvents.value = []
    decisions.value = []
    newsItems.value = []
    newsHistories.value = {}
    selectedPoint.value = null
    exposure.value = null
    selectedRiskDecision.value = null
    erpEvidence.value = null
  })
}

async function refresh() {
  if (active.value === 'l1' && canL1.value) {
    alerts.value = await api<Alerts>('/l1/alerts')
    summary.value = await api('/l1/summary')
    points.value = await api<RiskPoint[]>('/risk/map')
    if (!points.value.some(point => point.region_key === selectedPoint.value?.region_key)) {
      selectedPoint.value = [...points.value].sort((a, b) => b.risk_pct - a.risk_pct)[0] || null
      exposure.value = null
    }
  } else if (active.value === 'l2' && canL2.value) {
    orders.value = await api<Order[]>('/l2/impacted-orders')
  } else if (active.value === 'l3' && canL3.value) {
    const all = await api<Approval[]>('/l3/queue')
    approvals.value = all.filter(item => proposalIdFromOperation(item.operation_id))
  } else if (active.value === 'map' && canL1.value) {
    points.value = await api<RiskPoint[]>('/risk/map')
  } else if (active.value === 'events' && canL1.value) {
    events.value = await api<RiskEvent[]>('/risk/events')
    retractedEvents.value = await api<RetractedRiskEvent[]>('/risk/events/retracted')
  } else if (active.value === 'news' && canRiskAnalysis.value) {
    newsItems.value = await api<NewsItem[]>('/risk/news')
  } else if (active.value === 'decisions' && canDecisionRead.value) {
    decisions.value = await api<DecisionRecord[]>('/risk/decisions')
  }
}

async function refreshNews() {
  await run(async () => {
    newsRefreshResult.value = await api<NewsRefresh>('/risk/news/refresh', {
      method: 'POST', body: JSON.stringify({ within_days: newsDays.value, max_per_country: 8 }),
    })
    newsItems.value = await api<NewsItem[]>('/risk/news')
    if (newsRefreshResult.value.status === 'pending_analysis') newsFilter.value = 'failed'
    notice.value = `情報更新：新增 ${newsRefreshResult.value.saved_count}、重複 ${newsRefreshResult.value.duplicate_count}、分析成功 ${newsRefreshResult.value.analyzed_count}。`
  })
}

async function reviewNews(item: NewsItem, action: 'confirm' | 'dismiss') {
  await run(async () => {
    await api(`/risk/news/${item.id}/review`, {
      method: 'POST', body: JSON.stringify({ action, note: newsNotes.value[item.id] || '' }),
    })
    newsItems.value = await api<NewsItem[]>('/risk/news')
    delete newsHistories.value[item.id]
    notice.value = action === 'confirm' ? '新聞已確認並建立風險事件。' : '新聞已略過，審查原因已保存。'
  })
}

async function loadNewsHistory(newsId: number) {
  await run(async () => {
    newsHistories.value[newsId] = await api<NewsReviewAction[]>(`/risk/news/${newsId}/history`)
  })
}

async function choosePoint(point: RiskPoint) {
  selectedPoint.value = point
  exposure.value = null
  if (canRiskAnalysis.value) await run(async () => { exposure.value = await api<Exposure>(`/risk/map/exposure?region_key=${encodeURIComponent(point.region_key)}`) })
}

async function addEvent() {
  await run(async () => {
    await api('/risk/events', { method: 'POST', body: JSON.stringify(newEvent.value) })
    events.value = await api<RiskEvent[]>('/risk/events')
    newEvent.value = { event_type: '', country: '', region: '', impact_days: 0, description: '' }
    notice.value = '風險事件已儲存。'
  })
}

async function retractEvent(eventId: number) {
  await run(async () => {
    await api(`/risk/events/${eventId}/retract`, {
      method: 'POST', body: JSON.stringify({ reason: retractionReasons.value[eventId] || '' }),
    })
    events.value = await api<RiskEvent[]>('/risk/events')
    retractedEvents.value = await api<RetractedRiskEvent[]>('/risk/events/retracted')
    newsItems.value = []
    openRetractionId.value = null
    notice.value = '風險事件已撤銷，原紀錄與原因仍可追查。'
  })
}

async function runWhatIf() {
  await run(async () => {
    const result = await api<{ answer: string; decision_record: DecisionRecord }>('/risk/what-if', { method: 'POST', body: JSON.stringify({ question: question.value }) })
    whatIfAnswer.value = result.answer
    selectedRiskDecision.value = result.decision_record
    notice.value = `分析與證據快照已儲存：${result.decision_record.decision_id}`
  })
}

async function loadErpEvidence() {
  if (!selectedRiskDecision.value || !canRiskAnalysis.value) return
  await run(async () => {
    const decisionId = selectedRiskDecision.value!.decision_id
    const result = await api<ErpEvidence>(`/risk/decisions/${encodeURIComponent(decisionId)}/erp-evidence`)
    if (selectedRiskDecision.value?.decision_id === decisionId) erpEvidence.value = result
  })
}

async function recordMapAlert() {
  if (!selectedPoint.value) return
  await run(async () => {
    selectedRiskDecision.value = await api<DecisionRecord>(`/risk/map/${encodeURIComponent(selectedPoint.value!.region_key)}/decision`, { method: 'POST' })
    notice.value = `預警證據已儲存：${selectedRiskDecision.value.decision_id}`
  })
}

async function decideRisk(outcome: 'adopted' | 'rejected' | 'needs_more_evidence') {
  if (!selectedRiskDecision.value) return
  await run(async () => {
    selectedRiskDecision.value = await api<DecisionRecord>(`/risk/decisions/${encodeURIComponent(selectedRiskDecision.value!.decision_id)}/decision`, { method: 'POST', body: JSON.stringify({ outcome, reason: riskDecisionReason.value }) })
    decisions.value = await api<DecisionRecord[]>('/risk/decisions')
    notice.value = '決策結果已儲存。'
  })
}

async function addFeedback() {
  if (!selectedRiskDecision.value) return
  await run(async () => {
    selectedRiskDecision.value = await api<DecisionRecord>(`/risk/decisions/${encodeURIComponent(selectedRiskDecision.value!.decision_id)}/feedback`, {
      method: 'POST', body: JSON.stringify({ outcome: feedbackOutcome.value, action_taken: feedbackAction.value, outcome_evidence: feedbackEvidence.value }),
    })
    decisions.value = await api<DecisionRecord[]>('/risk/decisions')
    notice.value = '結果回饋已儲存。'
  })
}

watch(active, () => { void run(refresh) })
watch(() => selectedRiskDecision.value?.decision_id, () => { erpEvidence.value = null })
onMounted(() => {
  void (async () => {
    try {
      const result = await api<{ user: Principal; csrf_token: string }>('/session')
      user.value = result.user
      setCsrf(result.csrf_token)
      await refresh()
    } catch { /* Anonymous is an expected initial state. */ }
  })()
})

async function chooseOrder(order: Order) {
  selectedOrder.value = order
  reason.value = order.alternative_suggestion || '供應鏈事件導致延遲，建議由備援供應商供貨。'
  await run(async () => {
    const query = new URLSearchParams({
      affected_po_id: order.po_id,
      product_id: order.product_id,
      source_po_item_id: String(order.source_po_item_id),
    })
    alternatives.value = await api<Supplier[]>(`/l2/alternatives?${query}`)
    selectedSupplierProductId.value = alternatives.value[0]?.supplier_product_id ?? null
  })
}

async function submitProposal() {
  if (!selectedOrder.value) return
  const supplier = alternatives.value.find(item => item.supplier_product_id === selectedSupplierProductId.value)
  if (!supplier) return
  await run(async () => {
    const result = await api<{ submission: { status: string; approval_id: string } }>('/l2/proposals', {
      method: 'POST',
      body: JSON.stringify({
        proposal_id: newProposalId(),
        affected_po_id: selectedOrder.value!.po_id,
        product_id: selectedOrder.value!.product_id,
        source_po_item_id: selectedOrder.value!.source_po_item_id,
        alternative_supplier_id: supplier.supplier_id,
        alternative_supplier_product_id: supplier.supplier_product_id,
        reason: reason.value,
        estimated_delay_days: selectedOrder.value!.estimated_delay_days ?? null,
      }),
    })
    notice.value = result.submission.status === 'pending'
      ? `已送交 L3 審核：${result.submission.approval_id}` : `提案狀態：${result.submission.status}`
    selectedOrder.value = null
    orders.value = await api<Order[]>('/l2/impacted-orders')
  })
}

async function chooseApproval(item: Approval) {
  selectedApproval.value = item
  timeline.value = []
  const proposalId = proposalIdFromOperation(item.operation_id)
  if (!proposalId) return
  await run(async () => { selectedEvidence.value = await api<Record<string, unknown>>(`/proposals/${encodeURIComponent(proposalId)}`) })
}

async function decide(outcome: 'approve' | 'reject') {
  const proposalId = proposalIdFromOperation(selectedApproval.value?.operation_id)
  if (!proposalId) return
  await run(async () => {
    const result = await api<{ status: string; message: string }>(`/l3/proposals/${encodeURIComponent(proposalId)}/decision`, {
      method: 'POST', body: JSON.stringify({ outcome, reason: rejectionReason.value }),
    })
    notice.value = result.message || `處理結果：${result.status}`
    timeline.value = await api<typeof timeline.value>(`/l3/proposals/${encodeURIComponent(proposalId)}/timeline`)
    selectedApproval.value = null
    selectedEvidence.value = null
    approvals.value = (await api<Approval[]>('/l3/queue')).filter(item => proposalIdFromOperation(item.operation_id))
  })
}
</script>

<template>
  <div class="shell" :class="{ 'shell--entry': !user, 'shell--workspace': !!user }">
    <header v-if="user" class="masthead">
      <div class="workspace-brand"><span class="workspace-brand-mark" aria-hidden="true"><span></span></span><div><small>SUPPLY CHAIN INTELLIGENCE</small><h1>ERP / RISK</h1></div></div>
      <div class="identity"><span class="identity-status"><i aria-hidden="true"></i> 工作台已連線</span><span>{{ user.name }} · {{ user.role }}</span><button @click="signOut">登出</button></div>
    </header>

    <main v-if="!user" class="entry">
      <header class="entry-header">
        <div class="entry-brand">
          <span class="entry-brand-mark" aria-hidden="true"><span></span></span>
          <span><strong>ERP / RISK</strong><small>SUPPLY CHAIN INTELLIGENCE</small></span>
        </div>
        <span class="entry-header-note"><i aria-hidden="true"></i> 決策情報平台</span>
      </header>

      <div class="entry-body">
        <section class="entry-story" aria-labelledby="entry-title">
          <div class="entry-copy">
            <p class="entry-eyebrow"><span></span> SUPPLY CHAIN CONTROL CENTER <b>／ 01</b></p>
            <h1 id="entry-title">風險發生之前，<br><em>先看見全局。</em></h1>
            <p class="entry-lead">從全球供應情報到採購決策證據，讓每一次應對都有脈絡、有人把關。</p>
          </div>

          <div class="entry-orbit" aria-hidden="true">
            <svg class="entry-globe" viewBox="0 0 640 640" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <radialGradient id="globeFill" cx="0" cy="0" r="1" gradientTransform="translate(245 207) rotate(57) scale(450)">
                  <stop stop-color="#24475A"/><stop offset=".48" stop-color="#102B3C"/><stop offset="1" stop-color="#071622"/>
                </radialGradient>
                <linearGradient id="routeGlow" x1="139" y1="398" x2="535" y2="245" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#E56B33" stop-opacity=".2"/><stop offset=".54" stop-color="#FF9B55"/><stop offset="1" stop-color="#F77B3D" stop-opacity=".3"/>
                </linearGradient>
                <clipPath id="globeClip"><circle cx="320" cy="320" r="238"/></clipPath>
                <filter id="pointGlow" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="7"/></filter>
              </defs>
              <circle class="entry-globe-halo" cx="320" cy="320" r="277"/>
              <circle cx="320" cy="320" r="238" fill="url(#globeFill)" stroke="#4B7182" stroke-opacity=".72"/>
              <g clip-path="url(#globeClip)" stroke="#83A7B2" stroke-opacity=".16" stroke-width="1">
                <ellipse cx="320" cy="320" rx="238" ry="79"/><ellipse cx="320" cy="320" rx="238" ry="160"/>
                <ellipse cx="320" cy="320" rx="93" ry="238"/><ellipse cx="320" cy="320" rx="177" ry="238"/>
                <path d="M82 320h476M320 82v476"/>
              </g>
              <g clip-path="url(#globeClip)" fill="#2B5361" fill-opacity=".55" stroke="#6A8B94" stroke-opacity=".25" stroke-width="1.5">
                <path d="m109 194 36-19 38-5 31-22 39 4 26 23-5 28-29 14-16 31-34 8-19 27-26-12-12-30-34-15Z"/>
                <path d="m200 287 38 12 28 35-8 34-19 23-10 39-19 43-20 12-10-27 6-41-23-30 3-42 18-29Z"/>
                <path d="m315 163 29-21 48 4 32-14 52 20 28 30 25 8 18 37-23 27-42 5-22 31-34-12-22 14-19-19-40 2-25-30-34-4 9-28-16-21Z"/>
                <path d="m335 291 33 1 32 29 12 41-17 31-15 49-27 16-22-27-7-47-17-30 9-36Z"/>
                <path d="m456 417 36-10 32 15 17 25-10 25-45 1-23-20Z"/>
              </g>
              <g class="entry-routes" stroke="url(#routeGlow)" stroke-linecap="round">
                <path d="M159 292Q307 103 468 253" stroke-width="2.5"/>
                <path d="M468 253Q403 312 358 408" stroke-width="2.5"/>
                <path d="M159 292Q206 401 358 408" stroke-width="1.5" stroke-dasharray="5 8"/>
              </g>
              <g fill="#FFAD72">
                <circle cx="159" cy="292" r="16" opacity=".38" filter="url(#pointGlow)"/><circle cx="159" cy="292" r="5"/>
                <circle cx="468" cy="253" r="18" opacity=".4" filter="url(#pointGlow)"/><circle cx="468" cy="253" r="5"/>
                <circle cx="358" cy="408" r="16" opacity=".38" filter="url(#pointGlow)"/><circle cx="358" cy="408" r="5"/>
              </g>
              <g fill="#D6E5E7" font-family="Arial, sans-serif" font-size="12" letter-spacing="2">
                <text x="88" y="278">AMERICAS</text><text x="478" y="241">ASIA</text><text x="370" y="433">AFRICA</text>
              </g>
              <circle cx="320" cy="320" r="237" stroke="#9CC2C9" stroke-opacity=".18" stroke-width="6"/>
            </svg>
            <span class="entry-orbit-label">全球供應網絡 · 示意圖</span>
          </div>

          <div class="entry-capabilities" aria-label="平台功能">
            <div><span>01 / OBSERVE</span><strong>風險觀測</strong></div>
            <div><span>02 / SIMULATE</span><strong>情境推演</strong></div>
            <div><span>03 / DECIDE</span><strong>人工決策</strong></div>
          </div>
        </section>

        <section class="entry-login" aria-labelledby="login-title">
          <div class="entry-login-top"><span class="entry-login-icon" aria-hidden="true">↗</span><span>SECURE WORKSPACE</span></div>
          <div class="entry-login-copy"><span class="entry-login-kicker">WELCOME BACK</span><h2 id="login-title">登入決策工作台</h2><p>使用組織帳號，進入供應鏈風險工作區。</p></div>
          <form class="entry-login-form" @submit.prevent="signIn">
            <div class="entry-field"><label for="entry-username">帳號</label><input id="entry-username" v-model.trim="username" autocomplete="username" placeholder="輸入帳號" required></div>
            <div class="entry-field"><div class="entry-field-heading"><label for="entry-password">密碼</label><button type="button" class="entry-visibility" :aria-pressed="showPassword" @click="showPassword = !showPassword">{{ showPassword ? '隱藏密碼' : '顯示密碼' }}</button></div><input id="entry-password" v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="輸入密碼" required></div>
            <button class="entry-submit" :disabled="busy">{{ busy ? '登入中…' : '登入' }}<span aria-hidden="true">↗</span></button>
          </form>
          <div class="entry-login-foot"><span class="entry-foot-symbol" aria-hidden="true">◆</span><p>依身分啟用功能權限。關鍵採購決策仍由人員核准。</p></div>
        </section>
      </div>

      <footer class="entry-footer"><span>ERP / SUPPLY CHAIN RISK INTELLIGENCE</span><span>OBSERVE · VERIFY · DECIDE</span></footer>
    </main>

    <template v-else>
      <main class="workspace-main">
      <nav class="tabs" aria-label="功能層級">
        <button v-if="canL1" :class="{ current: active === 'l1' }" @click="active = 'l1'">L1 風險觀測</button>
        <button v-if="canL1" :class="{ current: active === 'map' }" @click="active = 'map'">供應風險地圖</button>
        <button v-if="canRiskAnalysis" :class="{ current: active === 'news' }" @click="active = 'news'">情報審查</button>
        <button v-if="canL1" :class="{ current: active === 'events' }" @click="active = 'events'">風險事件</button>
        <button v-if="canWhatIf" :class="{ current: active === 'whatif' }" @click="active = 'whatif'">What-if 分析</button>
        <button v-if="canDecisionRead" :class="{ current: active === 'decisions' }" @click="active = 'decisions'">決策紀錄</button>
        <button v-if="canL2" :class="{ current: active === 'l2' }" @click="active = 'l2'">L2 替代採購提案</button>
        <button v-if="canL3" :class="{ current: active === 'l3' }" @click="active = 'l3'">L3 人工核准</button>
      </nav>

      <section class="workspace-hero" aria-labelledby="workspace-hero-title">
        <div class="workspace-hero-copy">
          <p class="workspace-hero-kicker">SUPPLY CHAIN / RISK MONITORING &nbsp; — &nbsp; {{ workspacePage.index }}</p>
          <h2 id="workspace-hero-title">{{ workspacePage.title }}</h2>
          <p class="workspace-hero-description">{{ workspacePage.description }}</p>
          <p class="workspace-hero-meta"><b>ERP / RISK</b><span aria-hidden="true">·</span> 資料與操作依登入權限顯示</p>
        </div>
        <figure class="workspace-photo"><img src="/images/singapore-port.jpg" alt="港口貨櫃與物流現場"><figcaption>PORT / SINGAPORE<br>PHOTO: <a href="https://unsplash.com/photos/assorted-shipping-containers-in-dock-Q4bmoSPJM18" target="_blank" rel="noopener noreferrer">CHUTTERSNAP / UNSPLASH</a></figcaption></figure>
      </section>

      <section v-if="active === 'l1' && canL1" class="panel overview-panel">
        <div class="section-head"><div><small>RISK OVERVIEW / 即時資料</small><h2>供應鏈風險</h2><p class="overview-intro">將已確認事件與待審情報分開檢視，快速判斷下一步。</p></div><button @click="run(refresh)">重新整理 <span aria-hidden="true">↗</span></button></div>
        <div class="metrics"><div><strong>{{ points.length }}</strong><span>供應據點</span></div><div><strong>{{ highRiskPoints }}</strong><span>高風險據點</span></div><div><strong>{{ alerts?.candidate_count ?? '—' }}</strong><span>待確認情報</span></div><div><strong>{{ alerts?.confirmed_count ?? '—' }}</strong><span>已確認事件</span></div></div>
        <p v-if="alerts" class="overview-updated"><span aria-hidden="true"></span> 資料更新於 {{ alerts.generated_at }}</p>
        <div class="editorial-section-head"><div><small>01 / GLOBAL EXPOSURE</small><h3>全球曝險地圖</h3><p>點選據點查看風險分數與判讀原因。</p></div><button type="button" @click="active = 'map'">查看完整地圖 ↗</button></div>
        <div class="editorial-map-layout">
          <div class="geo-map" role="group" aria-label="供應據點經緯度圖">
            <span class="editorial-map-count">供應商所在區域 · {{ points.length }} 個據點</span>
            <button v-for="point in points" :key="point.region_key" class="geo-point" :class="{ selected: selectedPoint?.region_key === point.region_key }" :style="pointStyle(point)" :title="`${point.display_name}：${point.risk_pct}%`" :aria-label="`${point.display_name}，風險 ${point.risk_pct}%`" @click="choosePoint(point)"></button>
            <span class="editorial-map-credit">NATURAL EARTH / 110M · 經緯度示意</span>
          </div>
          <aside class="editorial-map-detail">
            <template v-if="selectedPoint">
              <small>SELECTED REGION</small><h3>{{ selectedPoint.display_name }}</h3>
              <p class="editorial-map-state" :class="selectedPoint.risk_pct >= 70 ? 'high' : selectedPoint.risk_pct >= 45 ? 'watch' : 'low'">{{ selectedPoint.risk_pct >= 70 ? '高風險' : selectedPoint.risk_pct >= 45 ? '需關注' : '正常監控' }}</p>
              <strong class="editorial-map-score">{{ selectedPoint.risk_pct }}<span> / 100 風險指數</span></strong>
              <dl><div><dt>關聯事件</dt><dd>{{ selectedPoint.event_count }} 件</dd></div><div v-if="exposure"><dt>正式供應商</dt><dd>{{ exposure.official_supplier_count }} 家</dd></div><div v-if="exposure"><dt>未結採購單</dt><dd>{{ exposure.open_po_count }} 張</dd></div></dl>
              <p class="editorial-map-reason">{{ selectedPoint.risk_reason }}</p>
              <small v-if="selectedPoint.updated_at" class="editorial-map-updated">據點更新：{{ selectedPoint.updated_at }}</small>
            </template>
            <p v-else class="empty">目前沒有可定位的供應商據點。</p>
          </aside>
        </div>
        <div class="editorial-section-head editorial-section-head--signals"><div><small>02 / SIGNALS &amp; EVIDENCE</small><h3>近期訊號</h3><p>已確認事件與待審情報分開列示，並保留原始來源。</p></div></div>
        <div class="overview-grid">
          <section class="overview-stream" aria-labelledby="confirmed-title">
            <div class="overview-stream-head"><span class="overview-stream-number">01</span><div><small>CONFIRMED EVENTS</small><h3 id="confirmed-title">已確認事件</h3></div><b>{{ alerts?.confirmed_count ?? 0 }} 件</b></div>
            <p v-if="!alerts?.confirmed.length" class="empty">目前沒有已確認事件。</p>
            <ul v-else class="rows"><li v-for="(item, index) in alerts.confirmed" :key="item.id ?? index"><div><b>{{ item.event_type || item.title || '事件' }}</b><span>{{ item.country }} {{ item.region }} · {{ item.severity || '未評級' }} · {{ item.ack_status || '未讀' }}</span><small v-if="item.news_id">來源：{{ item.news_source || '未標示' }} <a v-if="safeNewsUrl(item.news_url)" :href="safeNewsUrl(item.news_url) || undefined" target="_blank" rel="noopener noreferrer">閱讀原文</a></small></div></li></ul>
          </section>
          <section class="overview-stream overview-stream--intel" aria-labelledby="candidate-title">
            <div class="overview-stream-head"><span class="overview-stream-number">02</span><div><small>INTELLIGENCE QUEUE</small><h3 id="candidate-title">AI 待確認情報</h3></div><b>{{ alerts?.candidate_count ?? 0 }} 則</b></div>
            <p v-if="!alerts?.candidates.length" class="empty">目前沒有待確認情報。</p>
            <ul v-else class="rows"><li v-for="(item, index) in alerts.candidates" :key="item.news_id ?? index"><div><b>{{ item.title || '情報' }}</b><span>{{ item.country }} {{ item.region }} · {{ item.severity || '未評級' }}</span><small>來源：{{ item.news_source || '未標示' }} · {{ item.observed_at || '時間未知' }} <a v-if="safeNewsUrl(item.url)" :href="safeNewsUrl(item.url) || undefined" target="_blank" rel="noopener noreferrer">閱讀原文</a></small></div></li></ul>
          </section>
        </div>
        <details v-if="summary" class="overview-summary"><summary>最近一次 AI 風險摘要</summary><pre>{{ summary }}</pre></details>
      </section>

      <section v-if="active === 'map' && canL1" class="panel">
        <div class="section-head"><div><small>供應商據點</small><h2>供應風險地圖</h2></div><button @click="run(refresh)">重新整理</button></div>
        <p class="muted">依據事件、地區係數與採購集中度計算；點選據點查看原因與曝險。</p>
        <div class="metrics"><div><strong>{{ points.length }}</strong><span>供應據點</span></div><div><strong>{{ highRiskPoints }}</strong><span>高風險據點（≥70%）</span></div><div><strong>{{ points.reduce((sum, point) => sum + point.event_count, 0) }}</strong><span>據點關聯事件數</span></div></div>
        <div class="map-layout">
          <div class="map-stage"><div class="map-stage-head"><div><small>GLOBAL EXPOSURE</small><h3>供應據點分布</h3></div><span>經緯度視圖</span></div>
            <div class="geo-map" role="group" aria-label="供應據點經緯度圖"><span class="geo-label north">北緯 90°</span><span class="geo-label south">南緯 90°</span><span class="geo-label west">西經 180°</span><span class="geo-label east">東經 180°</span>
              <button v-for="point in points" :key="point.region_key" class="geo-point" :style="pointStyle(point)" :title="`${point.display_name}：${point.risk_pct}%`" :aria-label="`${point.display_name}，風險 ${point.risk_pct}%`" @click="choosePoint(point)"></button>
            </div>
            <p v-if="!points.length" class="empty">目前沒有可定位的供應商據點。</p>
            <div class="map-legend" aria-label="風險色彩說明"><span><i class="low" aria-hidden="true"></i>低於 45%</span><span><i class="medium" aria-hidden="true"></i>45–69%</span><span><i class="high" aria-hidden="true"></i>70% 以上</span></div>
          </div>
          <aside class="map-locations"><div class="map-stage-head"><div><small>LOCATION INDEX</small><h3>據點清單</h3></div><span>{{ points.length }} 處</span></div>
            <p v-if="!points.length" class="empty">新增可定位的供應商後，據點會出現在這裡。</p>
            <ul v-else class="rows"><li v-for="point in points" :key="point.region_key"><div><b>{{ point.display_name }}</b><span>風險 {{ point.risk_pct }}% · {{ point.risk_reason }}</span></div><button @click="choosePoint(point)">查看</button></li></ul>
          </aside>
        </div>
        <div v-if="selectedPoint" class="evidence"><h3>{{ selectedPoint.display_name }}</h3><p>{{ selectedPoint.risk_reason }}</p><p v-if="selectedPoint.ai_summary">AI 摘要：{{ selectedPoint.ai_summary }}</p><p v-if="exposure">正式供應商 {{ exposure.official_supplier_count }} 家；未結採購單 {{ exposure.open_po_count }} 張；金額 {{ exposure.open_po_amount.toLocaleString() }}</p><button v-if="canDecisionWrite && selectedPoint.risk_pct >= 70" @click="recordMapAlert">建立可追溯預警</button></div>
      </section>

      <section v-if="active === 'news' && canRiskAnalysis" class="panel">
        <div class="section-head"><div><small>原始新聞 → AI 判讀 → 人工確認</small><h2>供應鏈情報審查</h2></div><button @click="run(refresh)">重新讀取</button></div>
        <p class="muted">系統依正式供應商所在國家抓取新聞。AI 判讀只是候選情報；只有人工確認後才會建立風險事件。</p>
        <form v-if="canRiskWrite" class="news-toolbar" @submit.prevent="refreshNews">
          <label>抓取期間<select v-model.number="newsDays"><option :value="7">最近 7 天</option><option :value="30">最近 30 天</option><option :value="90">最近 90 天</option></select></label>
          <button class="primary" :disabled="busy">{{ busy ? '抓取與分析中…' : '抓取並分析新聞' }}</button>
        </form>
        <div v-if="newsRefreshResult" class="evidence">
          <h3>最近一次更新 · {{ refreshStatusLabel(newsRefreshResult.status) }}</h3>
          <p>國家：{{ newsRefreshResult.countries.join('、') }}</p>
          <p>掃描 {{ newsRefreshResult.fetched_count }}、新增 {{ newsRefreshResult.saved_count }}、重複 {{ newsRefreshResult.duplicate_count }}、分析成功 {{ newsRefreshResult.analyzed_count }}、分析失敗 {{ newsRefreshResult.failed_count }}、擷取失敗 {{ newsRefreshResult.fetch_failed_count }}、待分析 {{ newsRefreshResult.remaining_analysis_count }}。</p>
        </div>
        <label class="news-filter">檢視狀態<select v-model="newsFilter"><option value="review">待人工確認</option><option value="failed">待分析／分析失敗</option><option value="confirmed">已確認</option><option value="dismissed">已略過</option><option value="all">全部最近情報</option></select></label>
        <p v-if="!filteredNews.length" class="empty">此狀態目前沒有新聞；可切換「全部最近情報」查看原始資料。</p>
        <article v-for="item in filteredNews" :key="item.id" class="news-card">
          <div class="news-card-head"><h3>{{ item.title || '未命名新聞' }}</h3><span>{{ item.event_retracted ? '事件已撤銷' : item.review_status === 'confirmed' || item.event_id ? '已確認' : item.review_status === 'dismissed' ? '已略過' : item.analysis_status === 'succeeded' ? '待確認' : item.analysis_status === 'failed' ? '分析失敗' : '待分析' }}</span></div>
          <p class="muted">{{ item.source || '來源未標示' }} · 發布 {{ item.published_at || '未知' }} · 擷取 {{ item.fetched_at || '未知' }}</p>
          <p v-if="item.summary" class="answer">{{ item.summary }}</p>
          <p v-if="item.analysis_status === 'succeeded'"><b>AI 判讀：</b>{{ item.analysis_summary || '無摘要' }}<br><b>地區：</b>{{ item.analysis_country || '未辨識' }} {{ item.analysis_region || '' }} · <b>類型：</b>{{ item.category || '未分類' }} · <b>預估延遲：</b>{{ item.estimated_delay ?? '未知' }} 天 · <b>相關：</b>{{ item.is_relevant === 1 ? '是' : '否' }}</p>
          <p v-else class="muted">分析狀態：{{ item.analysis_status }}<span v-if="item.analysis_error"> · 原因代碼：{{ item.analysis_error }}</span></p>
          <p v-if="item.reviewed_by" class="muted">審查：{{ item.reviewed_by }} · {{ item.reviewed_at }}<span v-if="item.review_note"> · {{ item.review_note }}</span></p>
          <div v-if="item.reviewed_by" class="news-history"><button :disabled="busy" @click="loadNewsHistory(item.id)">審查歷程</button><ul v-if="newsHistories[item.id]" class="rows"><li v-for="entry in newsHistories[item.id]" :key="entry.action_id"><b>{{ entry.action === 'confirm' ? '確認' : '略過' }} · {{ entry.actor }}</b><span>{{ entry.recorded_at }} · {{ entry.note || '無備註' }}</span></li><li v-if="!newsHistories[item.id]?.length" class="muted">此筆為舊版審查，沒有逐次歷程。</li></ul></div>
          <p v-if="item.event_id" class="muted">已連結風險事件 #{{ item.event_id }}{{ item.event_retracted ? '（已撤銷）' : '' }}</p>
          <a v-if="safeNewsUrl(item.url)" :href="safeNewsUrl(item.url) || undefined" target="_blank" rel="noopener noreferrer">閱讀原文</a>
          <div v-if="canRiskWrite && !item.event_id && item.review_status !== 'confirmed'" class="news-review">
            <label>審查備註（略過時必填）<textarea v-model.trim="newsNotes[item.id]" maxlength="1000" rows="2"></textarea></label>
            <div class="actions"><button :disabled="busy" @click="reviewNews(item, 'dismiss')">略過並記錄原因</button><button v-if="item.analysis_status === 'succeeded' && item.is_relevant === 1 && item.estimated_delay != null" class="primary" :disabled="busy" @click="reviewNews(item, 'confirm')">確認並建立事件</button></div>
          </div>
        </article>
      </section>

      <section v-if="active === 'events' && canL1" class="panel">
        <div class="section-head"><div><small>經確認的供應鏈風險</small><h2>風險事件</h2></div><button @click="run(refresh)">重新整理</button></div>
        <form v-if="canRiskWrite" class="proposal-form" @submit.prevent="addEvent"><h3>登錄事件</h3><div class="field-grid"><label>事件類型<select v-model="newEvent.event_type" required><option value="" disabled>請選擇</option><option v-for="kind in ['戰爭','氣候','罷工','政策','交通','其他','地震','天候','政治','疫情']" :key="kind" :value="kind">{{ kind }}</option></select></label><label>國家<input v-model.trim="newEvent.country" maxlength="100"></label><label>地區<input v-model.trim="newEvent.region" required maxlength="100"></label><label>預估影響天數<input v-model.number="newEvent.impact_days" type="number" min="0" max="365" required></label></div><label>描述<textarea v-model.trim="newEvent.description" required maxlength="2000" rows="3"></textarea></label><button class="primary" :disabled="busy">儲存事件</button></form>
        <p v-if="!events.length" class="empty">目前沒有已登錄事件。</p>
        <ul v-else class="rows"><li v-for="event in events" :key="event.id" class="risk-event-row"><div><b>{{ event.event_type }} · {{ event.country }} {{ event.region }}</b><span>影響 {{ event.impact_days }} 天 · {{ event.created_at }}</span><small>{{ event.description }}</small><small v-if="event.news_id">來源：{{ event.news_source || '未標示' }} · 發布 {{ event.news_published_at || '未知' }} · 擷取 {{ event.news_fetched_at || '未知' }} · {{ event.news_title || '新聞原文' }} <a v-if="safeNewsUrl(event.news_url)" :href="safeNewsUrl(event.news_url) || undefined" target="_blank" rel="noopener noreferrer">閱讀原文</a></small></div><button v-if="canRiskWrite" @click="openRetractionId = event.id">撤銷</button><form v-if="canRiskWrite && openRetractionId === event.id" class="retract-form" @submit.prevent="retractEvent(event.id)"><p class="muted">撤銷後事件退出事件風險計算；其他人工風險設定與已執行採購不會自動回滾。</p><label>撤銷原因<textarea v-model.trim="retractionReasons[event.id]" minlength="5" maxlength="1000" required rows="2"></textarea></label><div class="actions"><button type="button" @click="openRetractionId = null">取消</button><button class="primary" :disabled="busy">確認撤銷</button></div></form></li></ul>
        <details v-if="retractedEvents.length" class="retracted-events"><summary>已撤銷事件（{{ retractedEvents.length }}）</summary><ul class="rows"><li v-for="event in retractedEvents" :key="event.id"><div><b>{{ event.event_type }} · {{ event.country }} {{ event.region }}</b><span>原影響 {{ event.impact_days }} 天 · {{ event.created_at }}</span><small>撤銷：{{ event.retracted_by }} · {{ event.retracted_at }} · {{ event.reason }}</small><small v-if="event.news_id">來源：{{ event.news_source || '未標示' }} · {{ event.news_title || '新聞原文' }} <a v-if="safeNewsUrl(event.news_url)" :href="safeNewsUrl(event.news_url) || undefined" target="_blank" rel="noopener noreferrer">閱讀原文</a></small></div></li></ul></details>
      </section>

      <section v-if="active === 'whatif' && canWhatIf" class="panel"><div class="section-head"><div><small>ERP 資料輔助分析</small><h2>What-if 情境模擬</h2></div></div><p class="muted">分析會讀取目前供應商、未結採購單與庫存資料，並將本次使用的 ERP 資料快照與 AI 回覆一起保存，供有權限的人員覆核。</p><form class="proposal-form" @submit.prevent="runWhatIf"><label>情境問題<textarea v-model.trim="question" required minlength="5" maxlength="1000" rows="4" placeholder="例如：若某供應地區運輸中斷兩週，哪些採購單可能延遲？"></textarea></label><button class="primary" :disabled="busy">{{ busy ? '分析中…' : '執行情境分析' }}</button></form><div v-if="whatIfAnswer" class="evidence"><h3>分析結果</h3><p class="answer">{{ whatIfAnswer }}</p></div></section>

      <section v-if="active === 'decisions' && canDecisionRead" class="panel"><div class="section-head"><div><small>AI 建議與人工結果</small><h2>決策紀錄</h2></div><button @click="run(refresh)">重新整理</button></div><p v-if="!decisions.length" class="empty">目前沒有決策紀錄。</p><ul v-else class="rows"><li v-for="record in decisions" :key="record.decision_id"><div><b>{{ record.evidence_snapshot.affected_entity }}</b><span>{{ record.status }} · 風險 {{ record.evidence_snapshot.risk_score }}% · {{ record.created_at }}</span></div><button @click="selectedRiskDecision = record">查看證據</button></li></ul></section>

      <section v-if="selectedRiskDecision && (active === 'decisions' || active === 'whatif' || active === 'map')" class="panel decision-detail"><div class="section-head"><h2>決策證據 · {{ selectedRiskDecision.decision_id }}</h2><button @click="selectedRiskDecision = null">關閉</button></div><p><b>建議：</b>{{ selectedRiskDecision.ai_output.recommendation }} · <b>狀態：</b>{{ selectedRiskDecision.status }} · <b>設定模型：</b>{{ selectedRiskDecision.model_name }}</p><p class="answer">{{ selectedRiskDecision.ai_output.reasoning }}</p><p class="muted">限制：{{ selectedRiskDecision.ai_output.limitations }}</p><p class="muted">資料時間：{{ selectedRiskDecision.evidence_snapshot.data_as_of }} · 快照 SHA-256：{{ selectedRiskDecision.snapshot_digest }}</p><div v-if="selectedRiskDecision.erp_context_digest && canRiskAnalysis" class="evidence"><h3>本次分析的 ERP 資料</h3><p class="muted">原始資料 SHA-256：{{ selectedRiskDecision.erp_context_digest }}</p><button v-if="!erpEvidence || erpEvidence.decision_id !== selectedRiskDecision.decision_id" :disabled="busy" @click="loadErpEvidence">檢視當時資料</button><template v-else><p>擷取時間：{{ erpEvidence.captured_at }}</p><p>供應商 {{ erpEvidence.erp_context.suppliers.length }} 筆 · 未結採購單 {{ erpEvidence.erp_context.open_purchase_orders.length }} 筆 · 庫存 {{ erpEvidence.erp_context.inventory.length }} 筆</p><details v-for="source in erpSources" :key="source.key" class="erp-source"><summary>{{ source.label }}</summary><pre>{{ JSON.stringify(erpEvidence.erp_context[source.key], null, 2) }}</pre></details></template></div><div v-if="canDecisionWrite && selectedRiskDecision.status === 'proposed'" class="proposal-form"><label>理由（拒絕或要求補證據時必填）<textarea v-model.trim="riskDecisionReason" rows="2"></textarea></label><div class="actions"><button @click="decideRisk('needs_more_evidence')">要求補證據</button><button @click="decideRisk('rejected')">拒絕建議</button><button class="primary" @click="decideRisk('adopted')">採納建議</button></div></div><form v-if="canDecisionWrite && selectedRiskDecision.status === 'adopted'" class="proposal-form" @submit.prevent="addFeedback"><h3>結果回饋</h3><label>結果<select v-model="feedbackOutcome"><option value="effective">有效</option><option value="ineffective">無效</option><option value="inconclusive">尚無定論</option></select></label><label>實際採取動作<textarea v-model.trim="feedbackAction" required rows="2"></textarea></label><label>結果依據<textarea v-model.trim="feedbackEvidence" required rows="2"></textarea></label><button :disabled="busy">儲存回饋</button></form><ul v-if="selectedRiskDecision.feedback.length" class="rows"><li v-for="(item, index) in selectedRiskDecision.feedback" :key="index"><b>{{ item.outcome }}</b><span>{{ item.action_taken }} · {{ item.outcome_evidence }}</span></li></ul></section>

      <section v-if="active === 'l2' && canL2" class="panel">
        <div class="section-head"><div><small>需人工確認</small><h2>受影響採購單</h2></div><button @click="run(refresh)">重新整理</button></div>
        <p class="muted">L2 建立提案並送審；核准前不會建立替代採購單。</p>
        <p v-if="!orders.length" class="empty">目前沒有標記延遲或備援建議的採購明細。</p>
        <ul v-else class="rows"><li v-for="order in orders" :key="order.source_po_item_id"><div><b>{{ order.po_id }} · {{ order.product_name || order.product_id }}</b><span>{{ order.supplier_name }} · 數量 {{ order.qty }} · 延遲 {{ order.estimated_delay_days ?? '未知' }} 天</span><small v-if="order.proposal">最近提案：{{ order.proposal.status }}</small></div><button @click="chooseOrder(order)">查看備援來源</button></li></ul>
        <form v-if="selectedOrder" class="proposal-form" @submit.prevent="submitProposal"><h3>替代採購提案：{{ selectedOrder.po_id }}</h3>
          <p v-if="!alternatives.length" class="empty">沒有可供應此品項的正式備援供應商。</p>
          <template v-else><label>備援供應商<select v-model="selectedSupplierProductId"><option v-for="item in alternatives" :key="item.supplier_product_id" :value="item.supplier_product_id">{{ item.name }} · NT$ {{ item.price }}</option></select></label>
          <label>提案理由<textarea v-model="reason" maxlength="1000" required rows="3"></textarea></label><button class="primary" :disabled="busy">送交 L3 核准</button></template>
        </form>
      </section>

      <section v-if="active === 'l3' && canL3" class="panel">
        <div class="section-head"><div><small>人工審查</small><h2>待審核採購提案</h2></div><button @click="run(refresh)">重新整理</button></div>
        <p v-if="!approvals.length" class="empty">目前沒有待審核的替代採購提案。</p>
        <ul v-else class="rows"><li v-for="item in approvals" :key="item.approval_id"><div><b>{{ item.operation_id }}</b><span>申請人：{{ item.requester_username }} · {{ item.status }}</span></div><button @click="chooseApproval(item)">審查</button></li></ul>
        <div v-if="selectedApproval && selectedEvidence" class="evidence"><h3>提案證據</h3><dl><template v-for="key in ['affected_po_id','product_id','original_supplier_id','alternative_supplier_id','qty','unit_price','reason','proposal_digest']" :key="key"><dt>{{ key }}</dt><dd>{{ selectedEvidence[key] }}</dd></template></dl>
          <label>拒絕原因<textarea v-model="rejectionReason" rows="2"></textarea></label><div class="actions"><button :disabled="busy" @click="decide('reject')">拒絕</button><button class="primary" :disabled="busy" @click="decide('approve')">核准並執行</button></div>
        </div>
        <div v-if="timeline.length" class="evidence"><h3>最近一次審核歷程</h3><ul class="rows"><li v-for="item in timeline" :key="`${item.kind}-${item.time}`"><b>{{ item.kind === 'execution_completed' ? '執行完成' : item.kind === 'approval_rejected' ? '已拒絕' : item.kind }}</b><span>{{ item.summary }}</span><small v-if="item.receipt_id">收據：{{ item.receipt_id }}</small></li></ul></div>
      </section>
      <section v-if="(active === 'l1' && !canL1) || (active === 'l2' && !canL2) || (active === 'l3' && !canL3)" class="panel"><p>目前帳號沒有此功能的權限。</p></section>
      </main>
    </template>

    <div v-if="error" class="message error" role="alert">{{ error }}</div>
    <div v-if="notice" class="message success" role="status">{{ notice }}</div>
  </div>
</template>
