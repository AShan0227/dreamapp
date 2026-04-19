// Fire-and-forget analytics tracker. All calls silently swallow errors —
// analytics must never affect the user experience.

import { getApiHost, getAuthToken } from './dream'

const ALLOWED_EVENTS = new Set([
  'session_started', 'page_viewed', 'cta_clicked',
  'onboarding_step', 'share_button_clicked',
  'subscription_viewed', 'paywall_shown',
  'record_started', 'record_finished',
  'dream_shared_external',
  'app_opened', 'app_backgrounded',
])

let sessionId: string | null = null
function getSessionId(): string {
  if (!sessionId) {
    try {
      sessionId = uni.getStorageSync('_an_session_id') || null
    } catch {}
    if (!sessionId) {
      sessionId = 's_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
      try { uni.setStorageSync('_an_session_id', sessionId) } catch {}
    }
  }
  return sessionId as string
}

export function trackEvent(event: string, props?: Record<string, any>): void {
  if (!ALLOWED_EVENTS.has(event)) return
  const body = { event, props: props || {}, session_id: getSessionId() }
  const host = getApiHost()
  const token = getAuthToken()
  try {
    uni.request({
      url: `${host}/api/analytics/track`,
      method: 'POST',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      data: body,
      timeout: 4000,
    })
  } catch {}
}

export function trackSessionStart(): void {
  trackEvent('session_started', { ts: Date.now() })
}

export function trackPageView(path: string): void {
  trackEvent('page_viewed', { path })
}
