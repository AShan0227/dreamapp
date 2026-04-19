// API base URL — env-driven so each platform/build can target its own backend.
// Resolution order:
//   1. import.meta.env.VITE_API_BASE_URL (vite-injected at build/dev time)
//   2. window-injected runtime override (`window.__DREAM_API_BASE__`)
//   3. H5 dev sniff: localhost:5173 → http://localhost:8000
//   4. H5 prod: same-origin (relative)
//   5. Native (mp/app): hardcoded fallback. Should always be set via env.
function _resolveApiHost(): string {
  // 1. Vite env at build time
  // @ts-ignore — vite virtual
  const fromEnv = (import.meta as any)?.env?.VITE_API_BASE_URL
  if (fromEnv) return String(fromEnv).replace(/\/$/, '')

  // 2. Runtime override (set this in index.html before app boots)
  // #ifdef H5
  const fromWindow = (typeof window !== 'undefined' && (window as any).__DREAM_API_BASE__)
  if (fromWindow) return String(fromWindow).replace(/\/$/, '')

  // 3. Dev server sniff
  if (typeof window !== 'undefined' && window.location?.port === '5173') {
    return 'http://localhost:8000'
  }
  // 4. Prod H5 — relative; nginx proxies /api → backend
  return ''
  // #endif

  // 5. Native fallback. Replace before shipping mp-weixin / app builds.
  // #ifndef H5
  return 'http://localhost:8000'
  // #endif
}

const API_HOST = _resolveApiHost()
const BASE_URL = `${API_HOST}/api/dreams`

/** Expose the resolved host for one-off non-uni-request callers
 *  (e.g. `uni.uploadFile`, `<video :src>`). NEVER hardcode the host elsewhere.
 */
export function getApiHost(): string { return API_HOST }

// --- Auth token storage ---
const TOKEN_KEY = 'dream_token'

export function getAuthToken(): string {
  try {
    return uni.getStorageSync(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setAuthToken(token: string): void {
  try { uni.setStorageSync(TOKEN_KEY, token || '') } catch {}
}

export function clearAuthToken(): void {
  try { uni.removeStorageSync(TOKEN_KEY) } catch {}
}

// --- Types ---

interface DreamChatResponse {
  dream_id: string
  ai_message: string
  is_complete: boolean
  round_number: number
}

interface Dream {
  id: string
  created_at: string
  status: string
  title: string | null
  video_url: string | null
  video_urls?: string[]
  video_style: string
  interpretation: any | null
  emotion_tags: string[]
  symbol_tags: string[]
  character_tags: string[]
  chat_history: { role: string; content: string }[]
  dream_script: any | null
  is_public?: boolean
  nightmare_flag?: boolean
  emotion_valence?: number
}

interface VideoStatus {
  status: string
  video_url: string | null
  video_urls?: string[]
  total_shots?: number
  completed_shots?: number
}

// --- Request helpers ---

// Global error toast — shown for 5xx and network failures unless the
// caller passes ``options.silent: true``. 4xx errors are surfaced via
// the rejected promise (callers usually have specific UX for those).
function _showGlobalError(message: string) {
  try {
    uni.showToast({ title: message, icon: 'none', duration: 2500 })
  } catch { /* uni unavailable in non-uni context */ }
}

function req<T>(url: string, options: any = {}): Promise<T> {
  // Auto-inject Authorization header from stored token. Caller can override
  // by passing their own header.Authorization (used by login flows that
  // haven't yet stored the token).
  const token = getAuthToken()
  const baseHeader: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) baseHeader['Authorization'] = `Bearer ${token}`

  const silent: boolean = !!options.silent
  const merged = {
    url,
    header: { ...baseHeader, ...(options.header || {}) },
    ...options,
  }
  delete (merged as any).silent

  return new Promise((resolve, reject) => {
    uni.request({
      ...merged,
      success: (res: any) => {
        if (res.statusCode === 401) {
          // Token rejected — clear, redirect to auth page, surface typed error
          clearAuthToken()
          // Don't redirect if we're already on the auth page or this IS a login attempt
          try {
            const pages = (uni.getCurrentPages?.() || []) as any[]
            const route = pages[pages.length - 1]?.route || ''
            const isAuthPage = route.includes('pages/auth/')
            const isAuthCall = url.includes('/users/login/') || url.includes('/users/register')
            if (!isAuthPage && !isAuthCall) {
              uni.redirectTo({ url: '/pages/auth/auth' })
            }
          } catch { /* ignore */ }
          const err: any = new Error('Unauthorized')
          err.code = 401
          err.body = res.data
          reject(err)
          return
        }
        if (res.statusCode === 429) {
          // Quota or rate limit — caller-handled UX (e.g. Record screen
          // shows a quota modal), so don't double-toast.
          const err: any = new Error('Too many requests')
          err.code = 429
          err.body = res.data
          reject(err)
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T)
        } else {
          if (res.statusCode >= 500 && !silent) {
            _showGlobalError('Server error — please try again')
          }
          const err: any = new Error(`API ${res.statusCode}`)
          err.code = res.statusCode
          err.body = res.data
          reject(err)
        }
      },
      fail: (err: any) => {
        if (!silent) _showGlobalError('Network error — check your connection')
        reject(err)
      },
    })
  })
}

function dreamsApi<T>(path: string, options: any = {}): Promise<T> {
  return req<T>(`${BASE_URL}${path}`, options)
}

function api<T>(path: string, options: any = {}): Promise<T> {
  return req<T>(`${API_HOST}${path}`, options)
}

// --- Dreams API ---

export const startDream = (initial_input: string, style = 'surreal') =>
  dreamsApi<DreamChatResponse>('/start', { method: 'POST', data: { initial_input, style } })

export const chatDream = (dream_id: string, message: string) =>
  dreamsApi<DreamChatResponse>('/chat', { method: 'POST', data: { dream_id, message } })

export const generateVideo = (dream_id: string) =>
  dreamsApi(`/${dream_id}/generate`, { method: 'POST' })

export const checkVideoStatus = (dream_id: string) =>
  dreamsApi<VideoStatus>(`/${dream_id}/video-status`)

export const rewriteNightmare = (dream_id: string) =>
  dreamsApi(`/${dream_id}/rewrite`, { method: 'POST' })

export const interpretDream = (dream_id: string) =>
  dreamsApi(`/${dream_id}/interpret`, { method: 'POST' })

export const listDreams = (skip = 0, limit = 20) =>
  dreamsApi<Dream[]>(`/?skip=${skip}&limit=${limit}`)

export const getDream = (dream_id: string) =>
  dreamsApi<Dream>(`/${dream_id}`)

export const extractEntities = (dream_id: string) =>
  dreamsApi(`/${dream_id}/extract-entities`, { method: 'POST' })

// --- Entity & Correlation API ---
// All scoped to the authenticated user via Bearer token (no user_id query).

export const listEntities = (min_count = 2) =>
  api<any[]>(`/api/entities/entities?min_count=${min_count}`)

export const listCorrelations = () =>
  api<any[]>(`/api/entities/correlations`)

export const getEntityTimeline = (entity: string) =>
  api<any[]>(`/api/entities/timeline?entity=${encodeURIComponent(entity)}`)

export const triggerCorrelation = () =>
  api(`/api/entities/correlate`, { method: 'POST' })

// --- Health API ---

export const getHealthCurrent = (days = 30) =>
  api<any>(`/api/health/current?days=${days}`)

export const getHealthAnomalies = () =>
  api<any>(`/api/health/anomalies`)

export const generateHealthReport = (period = 'monthly') =>
  api(`/api/health/generate-report?period=${period}`, { method: 'POST' })

// --- Incubation API ---

export const startIncubation = (intention: string) =>
  api(`/api/incubation/start`, { method: 'POST', data: { intention } })

export const getIncubation = (session_id: string) =>
  api(`/api/incubation/${session_id}`)

export const linkDreamToIncubation = (session_id: string, dream_id: string) =>
  api(`/api/incubation/${session_id}/link-dream?dream_id=${dream_id}`, { method: 'POST' })

export const listIncubations = () =>
  api<any[]>(`/api/incubation/`)

// --- Dream IP API ---

export const listIPs = () =>
  api<any[]>(`/api/ips/`)

export const getIP = (ip_id: string) =>
  api(`/api/ips/${ip_id}`)

export const detectIPs = () =>
  api(`/api/ips/detect`, { method: 'POST' })

// --- Plaza API ---

export const browsePlaza = (skip = 0, limit = 20) =>
  api<any[]>(`/api/plaza/dreams?skip=${skip}&limit=${limit}`)

export const getTrending = () =>
  api(`/api/plaza/trending`)

export const getSimilarDreams = (dream_id: string) =>
  api<any[]>(`/api/plaza/dreams/${dream_id}/similar`)

export const publishDream = (dream_id: string) =>
  api(`/api/plaza/dreams/${dream_id}/publish`, { method: 'POST' })

export const unpublishDream = (dream_id: string) =>
  api(`/api/plaza/dreams/${dream_id}/unpublish`, { method: 'POST' })

export const searchDreams = (q: string, limit = 10) =>
  api<any[]>(`/api/plaza/search?q=${encodeURIComponent(q)}&limit=${limit}`)

export const searchKnowledge = (q: string, source?: string, limit = 5) => {
  const sp = source ? `&source=${encodeURIComponent(source)}` : ''
  return api<any[]>(`/api/plaza/knowledge-search?q=${encodeURIComponent(q)}&limit=${limit}${sp}`)
}

export const knowledgeStats = () =>
  api(`/api/plaza/knowledge/stats`)

export const knowledgeTop = (by: 'use_count' | 'success' | 'failure' | 'confidence' = 'use_count', limit = 10) =>
  api<any[]>(`/api/plaza/knowledge/top?by=${by}&limit=${limit}`)

export const knowledgeQuarantined = (limit = 50) =>
  api<any[]>(`/api/plaza/knowledge/quarantined?limit=${limit}`)

export const knowledgeRestore = (id: string) =>
  api(`/api/plaza/knowledge/${id}/restore`, { method: 'POST' })

export const knowledgeRunSleepCycle = (skip_merge = false) =>
  api(`/api/plaza/knowledge/sleep-cycle?skip_merge=${skip_merge}`, { method: 'POST' })

export const knowledgeSchedulerStatus = () =>
  api(`/api/plaza/knowledge/scheduler`)

// Research dashboard
export const researchSymbolFrequency = (limit = 30) =>
  api<any[]>(`/api/plaza/research/symbol-frequency?limit=${limit}`)

export const researchEmotionDistribution = () =>
  api(`/api/plaza/research/emotion-distribution`)

export const researchCulturalBreakdown = () =>
  api<any[]>(`/api/plaza/research/cultural-breakdown`)

export const researchPapersCited = () =>
  api(`/api/plaza/research/papers-cited`)

export function researchExportUrl(kind: 'symbols' | 'emotions' | 'papers' | 'cultural') {
  // CSV download — let the browser do it via direct link
  return `/api/plaza/research/export.csv?kind=${kind}`
}

// --- Attribution / Feedback ---

export const getCitations = (dream_id: string) =>
  api<any>(`/api/dreams/${dream_id}/citations`)

export const submitFeedback = (dream_id: string, aspect: string, helpful: boolean) =>
  api(`/api/dreams/${dream_id}/feedback`, {
    method: 'POST',
    data: { aspect, helpful },
  })

// --- User API ---

export const registerUser = async (nickname = 'Dreamer') => {
  const u: any = await api(`/api/users/register`, { method: 'POST', data: { nickname } })
  if (u?.token) setAuthToken(u.token)
  return u
}

export const registerEmail = async (email: string, password: string, nickname?: string) => {
  const u: any = await api(`/api/users/register/email`, {
    method: 'POST',
    data: { email, password, nickname: nickname || 'Dreamer' },
  })
  if (u?.token) setAuthToken(u.token)
  return u
}

export const loginEmail = async (email: string, password: string) => {
  const u: any = await api(`/api/users/login/email`, {
    method: 'POST',
    data: { email, password },
  })
  if (u?.token) setAuthToken(u.token)
  return u
}

export const requestPhoneOtp = (phone: string) =>
  api(`/api/users/login/phone/request`, { method: 'POST', data: { phone } })

export const verifyPhoneOtp = async (phone: string, code: string, nickname?: string) => {
  const u: any = await api(`/api/users/login/phone/verify`, {
    method: 'POST',
    data: { phone, code, nickname },
  })
  if (u?.token) setAuthToken(u.token)
  return u
}

export const requestPasswordReset = (email: string) =>
  api(`/api/users/password/reset/request`, { method: 'POST', data: { email } })

export const confirmPasswordReset = async (email: string, code: string, new_password: string) => {
  const u: any = await api(`/api/users/password/reset/confirm`, {
    method: 'POST',
    data: { email, code, new_password },
  })
  if (u?.token) setAuthToken(u.token)
  return u
}

export const bindEmail = (email: string, password: string) =>
  api(`/api/users/me/bind/email`, { method: 'POST', data: { email, password } })

export const bindPhone = (phone: string, code: string) =>
  api(`/api/users/me/bind/phone`, { method: 'POST', data: { phone, code } })

export const changePassword = (new_password: string, old_password?: string) =>
  api(`/api/users/me/password`, { method: 'POST', data: { new_password, old_password } })

export const getMe = () =>
  api(`/api/users/me`)

export const getMyQuota = () =>
  api(`/api/users/me/quota`)

export const logout = () => {
  clearAuthToken()
  return Promise.resolve(true)
}

/**
 * Ensure a user is logged in. If a token already exists and works, returns
 * the cached user. Otherwise creates an anonymous user as a fallback so
 * legacy flows (the Record screen with no auth UI) keep working.
 */
export const ensureLoggedIn = async () => {
  if (getAuthToken()) {
    try { return await getMe() } catch { /* token expired/bad — fall through */ }
  }
  return await registerUser()
}

// --- Agent API ---

export const createAgent = (data: any) =>
  api(`/api/agents/create`, { method: 'POST', data })

export const listAgents = () =>
  api<any[]>(`/api/agents/`)

export const runAgent = (agent_id: string) =>
  api(`/api/agents/${agent_id}/run`, { method: 'POST' })

export const getAgentRuns = (agent_id: string) =>
  api<any[]>(`/api/agents/${agent_id}/runs`)

export const browseStore = () =>
  api<any[]>(`/api/store/agents`)

export const installAgent = (agent_id: string) =>
  api(`/api/store/agents/${agent_id}/install`, { method: 'POST' })

// --- Vibe Coder API ---

export const customizeLayout = (prompt: string) =>
  api(`/api/vibe/customize?prompt=${encodeURIComponent(prompt)}`, { method: 'POST' })

export const getLayout = () =>
  api(`/api/vibe/layout`)

// --- Dream mutations (delete + edit) ---

export const deleteDream = (dream_id: string) =>
  dreamsApi(`/${dream_id}`, { method: 'DELETE' })

export const updateDream = (dream_id: string, payload: { title?: string; video_style?: string }) =>
  dreamsApi(`/${dream_id}`, { method: 'PATCH', data: payload })

// --- Wave F: Cross-temporal correlation (§8.3) ---

export const refreshTemporalPatterns = () =>
  api(`/api/temporal/refresh`, { method: 'POST' })

export const listTemporalPatterns = (kind?: string) =>
  api<any[]>(`/api/temporal/patterns${kind ? `?kind=${kind}` : ''}`)

// --- Wave F: Deja Reve (§8.4) ---

export const dejaReveSearch = (waking_event: string) =>
  api<any[]>(`/api/deja-reve/search`, { method: 'POST', data: { waking_event } })

export const dejaReveConfirm = (dream_id: string, waking_event: string, similarity?: number) =>
  api(`/api/deja-reve/confirm`, { method: 'POST', data: { dream_id, waking_event, similarity } })

export const dejaReveList = () =>
  api<any[]>(`/api/deja-reve/`)

// --- Wave F: Dream Matching (§6.2) ---

export const matchingSimilarCount = (dream_id: string, window_hours = 48) =>
  api(`/api/matching/dream/${dream_id}/similar-count?window_hours=${window_hours}`)

export const matchingCompatibleUsers = (limit = 10) =>
  api<any[]>(`/api/matching/users?limit=${limit}`)

// --- Wave F: Customization (§7.1) ---

export const createCustomization = (
  source_dream_id: string,
  kinds: string[],
  parameters: Record<string, any>,
  user_completion_text?: string,
) =>
  api(`/api/customize/`, {
    method: 'POST',
    data: { source_dream_id, kinds, parameters, user_completion_text },
  })

export const getCustomization = (id: string) =>
  api(`/api/customize/${id}`)

export const listCustomizations = () =>
  api<any[]>(`/api/customize/`)

// --- Wave F: Remix (§7.2) ---

export const remixSplice = (dream_id_a: string, dream_id_b: string, user_prompt = '') =>
  api(`/api/remix/splice`, { method: 'POST', data: { dream_id_a, dream_id_b, user_prompt } })

export const remixOther = (source_dream_id: string, user_prompt: string) =>
  api(`/api/remix/other`, { method: 'POST', data: { source_dream_id, user_prompt } })

export const remixChain = (
  payload: { previous_remix_id?: string; previous_dream_id?: string; user_prompt?: string },
) =>
  api(`/api/remix/chain`, { method: 'POST', data: payload })

export const remixDialogue = (dream_id_a: string, dream_id_b: string) =>
  api(`/api/remix/dialogue`, { method: 'POST', data: { dream_id_a, dream_id_b } })

export const listMyRemixes = () =>
  api<any[]>(`/api/remix/`)

export const remixChainWalk = (root_id: string) =>
  api<any[]>(`/api/remix/chain/${root_id}`)

// --- Wave F: Co-Dreaming (§6.3) ---

export const codreamCreate = (title: string, theme: string, max_participants = 4) =>
  api(`/api/codream/`, { method: 'POST', data: { title, theme, max_participants } })

export const codreamJoin = (invite_code: string) =>
  api(`/api/codream/join`, { method: 'POST', data: { invite_code } })

export const codreamSubmit = (session_id: string, dream_id: string) =>
  api(`/api/codream/submit`, { method: 'POST', data: { session_id, dream_id } })

export const codreamRender = (session_id: string) =>
  api(`/api/codream/${session_id}/render`, { method: 'POST' })

export const codreamGet = (session_id: string) =>
  api(`/api/codream/${session_id}`)

export const codreamListMine = () =>
  api<any[]>(`/api/codream/`)

// --- Wave F: Vibe Coder v2 ---

export const vibeCustomize = (prompt: string) =>
  api(`/api/vibe/customize?prompt=${encodeURIComponent(prompt)}`, { method: 'POST' })

export const vibeGetLayout = () =>
  api(`/api/vibe/layout`)

// --- Wave H: Engagement / Social ---

export const postComment = (dream_id: string, body: string, parent_id?: string) =>
  api(`/api/dreams/${dream_id}/comments`, { method: 'POST', data: { body, parent_id } })

export const listComments = (dream_id: string) =>
  api<any[]>(`/api/dreams/${dream_id}/comments`)

export const toggleReaction = (dream_id: string, kind: string) =>
  api(`/api/dreams/${dream_id}/reactions`, { method: 'POST', data: { kind } })

export const getReactions = (dream_id: string) =>
  api<Record<string, number>>(`/api/dreams/${dream_id}/reactions`)

export const followUser = (followee_id: string) =>
  api(`/api/follows/${followee_id}`, { method: 'POST' })

export const unfollowUser = (followee_id: string) =>
  api(`/api/follows/${followee_id}`, { method: 'DELETE' })

export const followCounts = () =>
  api(`/api/follows/counts`)

export const followingFeed = (limit = 30) =>
  api<any[]>(`/api/feed/following?limit=${limit}`)

export const picksToday = () =>
  api<any[]>(`/api/picks/today`)

export const refreshPicks = () =>
  api(`/api/picks/refresh`, { method: 'POST' })

export const listChallenges = () =>
  api<any[]>(`/api/challenges/`)

export const submitChallenge = (challenge_id: string, dream_id: string) =>
  api(`/api/challenges/submit`, { method: 'POST', data: { challenge_id, dream_id } })

export const challengeLeaderboard = (challenge_id: string, limit = 30) =>
  api<any[]>(`/api/challenges/${challenge_id}/leaderboard?limit=${limit}`)

export const myReferralCode = () =>
  api<{ code: string; use_count: number }>(`/api/referrals/me`)

export const redeemReferral = (code: string) =>
  api(`/api/referrals/redeem`, { method: 'POST', data: { code } })

export const recordSleep = (payload: any) =>
  api(`/api/sleep/`, { method: 'POST', data: payload })

export const listSleep = (days = 30) =>
  api<any[]>(`/api/sleep/?days=${days}`)

export const listTherapists = (specialty?: string, language?: string) => {
  const qs = [
    specialty ? `specialty=${encodeURIComponent(specialty)}` : '',
    language ? `language=${encodeURIComponent(language)}` : '',
  ].filter(Boolean).join('&')
  return api<any[]>(`/api/therapists/${qs ? '?' + qs : ''}`)
}

export const suggestedTherapists = (limit = 5) =>
  api<any[]>(`/api/therapists/suggest?limit=${limit}`)

export const requestBooking = (
  therapist_id: string,
  scheduled_for: string,
  duration_minutes = 50,
  shared_dream_ids: string[] = [],
  notes = '',
) =>
  api(`/api/bookings/`, {
    method: 'POST',
    data: { therapist_id, scheduled_for, duration_minutes, shared_dream_ids, notes },
  })

export const listMyBookings = (asTherapist = false) =>
  api<any[]>(`/api/bookings/?as_therapist=${asTherapist}`)

export const mySubscription = () =>
  api(`/api/subscription/me`)

export const listPlans = () =>
  api<any[]>(`/api/subscription/plans`)

export const cancelSubscription = () =>
  api(`/api/subscription/cancel`, { method: 'POST' })

export const createPayment = (
  purpose: string, provider: 'wechat' | 'alipay' | 'stripe',
  purpose_ref?: string, amount_cents?: number,
) =>
  api(`/api/payments/create`, {
    method: 'POST',
    data: { purpose, provider, purpose_ref, amount_cents },
  })

export const sandboxCompletePayment = (out_trade_no: string) =>
  api(`/api/payments/sandbox-complete?out_trade_no=${encodeURIComponent(out_trade_no)}`, { method: 'POST' })

export const coinBalance = () =>
  api<{ balance: number }>(`/api/coins/balance`)

export const coinHistory = (limit = 50) =>
  api<any[]>(`/api/coins/history?limit=${limit}`)

export const giftCoins = (to_user_id: string, amount: number, note?: string) =>
  api(`/api/coins/gift`, { method: 'POST', data: { to_user_id, amount, note } })

export const shareCard = (dream_id: string) =>
  api(`/api/share/${dream_id}`)

export const listAPIKeys = () =>
  api<any[]>(`/api/api-keys/`)

export const issueAPIKey = (name: string, scopes: string[] = ['knowledge:read'], monthly_quota = 10000) =>
  api(`/api/api-keys/`, { method: 'POST', data: { name, scopes, monthly_quota } })

export const revokeAPIKey = (id: string) =>
  api(`/api/api-keys/${id}`, { method: 'DELETE' })

// Public lobby for codream
export const codreamLobby = () =>
  api<any[]>(`/api/codream/lobby`)

// --- Wave I: Threads-style social ---

export const getProfile = (handle_or_id: string) =>
  api<any>(`/api/profile/${encodeURIComponent(handle_or_id)}`)

export const updateMyProfile = (payload: any) =>
  api(`/api/profile/me`, { method: 'PATCH', data: payload })

export const pinDreams = (dream_ids: string[]) =>
  api(`/api/profile/me/pin`, { method: 'POST', data: { dream_ids } })

export const listNotifications = (unread_only = false, limit = 50) =>
  api<any[]>(`/api/notifications/?unread_only=${unread_only}&limit=${limit}`)

export const unreadCount = () =>
  api<{ count: number }>(`/api/notifications/unread-count`)

export const markRead = (notification_ids?: string[]) =>
  api(`/api/notifications/mark-read`, { method: 'POST', data: { notification_ids } })

export const followHashtag = (tag: string) =>
  api(`/api/hashtags/${encodeURIComponent(tag)}/follow`, { method: 'POST' })

export const unfollowHashtag = (tag: string) =>
  api(`/api/hashtags/${encodeURIComponent(tag)}/follow`, { method: 'DELETE' })

export const myFollowedTags = () =>
  api<string[]>(`/api/hashtags/me`)

export const tagDreams = (tag: string, limit = 30) =>
  api<any[]>(`/api/hashtags/${encodeURIComponent(tag)}?limit=${limit}`)

export const trendingTags = (hours = 24, limit = 20) =>
  api<any[]>(`/api/hashtags/trending/?hours=${hours}&limit=${limit}`)

export const forYouFeed = (limit = 30) =>
  api<any[]>(`/api/feed/for-you?limit=${limit}`)

export const bookmarkDream = (dream_id: string, folder = 'default') =>
  api(`/api/dreams/${dream_id}/bookmark?folder=${encodeURIComponent(folder)}`, { method: 'POST' })

export const unbookmarkDream = (dream_id: string) =>
  api(`/api/dreams/${dream_id}/bookmark`, { method: 'DELETE' })

export const listBookmarks = (folder?: string) =>
  api<any[]>(`/api/bookmarks/${folder ? '?folder=' + encodeURIComponent(folder) : ''}`)

export const createPoll = (dream_id: string, question: string, options: string[], closes_in_hours = 72) =>
  api(`/api/polls/`, { method: 'POST', data: { dream_id, question, options, closes_in_hours } })

export const votePoll = (poll_id: string, option_id: string) =>
  api(`/api/polls/${poll_id}/vote`, { method: 'POST', data: { option_id } })

export const pollResults = (poll_id: string) =>
  api(`/api/polls/${poll_id}`)

export const muteUser = (user_id: string) =>
  api(`/api/users/${user_id}/mute`, { method: 'POST' })

export const blockUser = (user_id: string) =>
  api(`/api/users/${user_id}/block`, { method: 'POST' })

export const reportContent = (target_kind: string, target_id: string, reason: string, detail = '') =>
  api(`/api/reports/`, { method: 'POST', data: { target_kind, target_id, reason, detail } })

export const sendDM = (recipient_id: string, body: string) =>
  api(`/api/dm/send`, { method: 'POST', data: { recipient_id, body } })

export const listDMThreads = () =>
  api<any[]>(`/api/dm/threads`)

export const listDMMessages = (thread_id: string, limit = 100) =>
  api<any[]>(`/api/dm/threads/${thread_id}/messages?limit=${limit}`)

export const quoteDream = (quoted_dream_id: string, body = '', repost_only = false) =>
  api(`/api/quotes/`, { method: 'POST', data: { quoted_dream_id, body, repost_only } })

export const listQuotes = (dream_id: string) =>
  api<any[]>(`/api/dreams/${dream_id}/quotes`)

export const commentsTree = (dream_id: string) =>
  api<any[]>(`/api/dreams/${dream_id}/comments-tree`)

export const createSeries = (title: string, description = '', dream_ids: string[] = [], is_public = false) =>
  api(`/api/series/`, { method: 'POST', data: { title, description, dream_ids, is_public } })

export const updateSeries = (series_id: string, payload: any) =>
  api(`/api/series/${series_id}`, { method: 'PATCH', data: payload })

export const listMySeries = () =>
  api<any[]>(`/api/series/`)

// --- Video polling ---

export function waitForVideo(dream_id: string, onProgress?: (status: string) => void): Promise<VideoStatus> {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const poll = () => {
      if (++attempts > 60) { reject(new Error('Timeout')); return }
      checkVideoStatus(dream_id)
        .then((res) => {
          onProgress?.(res.status)
          if (res.status === 'completed') resolve(res)
          else if (res.status === 'failed') reject(new Error('Failed'))
          else setTimeout(poll, 5000)
        })
        .catch(() => { if (attempts < 60) setTimeout(poll, 5000); else reject(new Error('Network error')) })
    }
    poll()
  })
}

export type { Dream, DreamChatResponse, VideoStatus }


// =============================================================================
//  Wave M — Streak + daily prompt
// =============================================================================

export interface StreakSummary {
  current: number
  longest: number
  status: 'inactive' | 'continue_today' | 'done_today' | 'broken'
  last_streak_date: string | null
  next_milestone: number | null
  next_milestone_reward: number
}

export interface DailyPrompt {
  date: string
  locale: string
  prompt: string
  category: string
  source: 'pool' | 'seeded'
}

/** Read-only summary for UI (current/longest/next-milestone). */
export function getMyStreak(): Promise<StreakSummary> {
  return req<StreakSummary>(`${API_HOST}/api/streak/me`)
}

/** Today's "tonight try to dream of X" — locale-aware fallback if no row seeded. */
export function getTodayPrompt(locale: string = 'zh-CN'): Promise<DailyPrompt> {
  return req<DailyPrompt>(`${API_HOST}/api/streak/today-prompt?locale=${encodeURIComponent(locale)}`)
}


// =============================================================================
//  Wave N — Dream Wrapped (year/quarter/month in dreams)
// =============================================================================

export interface WrappedReport {
  period: string
  start: string
  end: string
  empty: boolean
  total_dreams: number
  nightmare_count?: number
  nightmare_rate?: number
  top_symbols?: { name: string; count: number }[]
  top_emotions?: { name: string; count: number }[]
  top_characters?: { name: string; count: number }[]
  emotion_arc?: { month: string; valence: number; count: number }[]
  first_dream_title?: string
  most_intense_dream_title?: string
  dream_aesthetic?: string
  streak_peak?: number
  headline_number: number
  headline_label_zh?: string
  headline_label_en?: string
  share_slug?: string
  cached?: boolean
}

/** Period: "2026" | "2026-Q2" | "month-2026-04" */
export function getMyWrapped(period: string): Promise<WrappedReport> {
  return req<WrappedReport>(
    `${API_HOST}/api/wrapped/me?period=${encodeURIComponent(period)}`,
  )
}

export function refreshMyWrapped(period: string): Promise<WrappedReport> {
  return req<WrappedReport>(
    `${API_HOST}/api/wrapped/me/refresh?period=${encodeURIComponent(period)}`,
    { method: 'POST' },
  )
}

/** Anonymous public Wrapped lookup — no auth needed. */
export function getPublicWrapped(slug: string): Promise<WrappedReport> {
  return req<WrappedReport>(
    `${API_HOST}/api/wrapped/slug/${encodeURIComponent(slug)}`,
  )
}


// =============================================================================
//  Wave O — Dream Duet / Remix
// =============================================================================

export type RemixKind = 'duet' | 'cover' | 'continuation'

export interface DuetStartResponse {
  dream_id: string
  source_dream_id: string
  kind: RemixKind
  ai_message: string
  round_number: number
  is_complete: boolean
}

export interface RemixListItem {
  dream_id: string
  title: string | null
  kind: RemixKind
  video_url: string | null
  created_at: string | null
}

/** Start a new dream seeded by another user's public dream. */
export function startDuet(
  source_dream_id: string,
  kind: RemixKind = 'duet',
  options: { style?: string; note?: string } = {},
): Promise<DuetStartResponse> {
  return req<DuetStartResponse>(`${API_HOST}/api/duet/start`, {
    method: 'POST',
    data: { source_dream_id, kind, ...options },
  })
}

/** Public list of remixes derived from a given dream. */
export function listRemixesOf(dream_id: string): Promise<{
  source_dream_id: string
  count: number
  remixes: RemixListItem[]
}> {
  return req(`${API_HOST}/api/duet/of/${encodeURIComponent(dream_id)}`)
}

/** Wave O — my own duet/cover/continuation remix history.
 *  (Renamed from listMyRemixes to avoid collision with the older AI-remix
 *   pipeline helper. That one queries /api/remix/, this one /api/duet/by-me.)
 */
export function listMyDuets(): Promise<RemixListItem[]> {
  return req<RemixListItem[]>(`${API_HOST}/api/duet/by-me`)
}


// =============================================================================
//  Wave K Moderation — submit a content report (distinct from the older
//  /api/reports/ helper which targeted threads.py's report endpoint.
//  This one hits the new /api/moderation/report from Wave K.)
// =============================================================================

export interface ModerationReportRequest {
  target_type: 'dream' | 'thread' | 'comment' | 'user' | 'dm'
  target_id: string
  reason: string
  detail?: string
}

export function submitModerationReport(body: ModerationReportRequest): Promise<{
  ok: boolean
  auto_hidden: boolean
  total_reports: number
}> {
  return req(`${API_HOST}/api/moderation/report`, {
    method: 'POST',
    data: body,
  })
}

export function listModerationReasons(): Promise<{ reasons: Record<string, string> }> {
  return req(`${API_HOST}/api/moderation/report/reasons`)
}
