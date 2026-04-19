/**
 * URL safety helpers for binding user-influenced URLs into
 * `<video :src>`, `<image :src>`, etc.
 *
 * Why: even though UniApp's `<text>` escapes interpolated content, an
 * attacker who controls a stored URL (e.g. a published dream's video_url
 * if the backend ever leaks an attacker-controlled value) can trivially
 * trigger XSS via `javascript:` or `data:text/html` schemes.
 *
 * Whitelist scheme model — only http(s) and same-origin relative paths.
 */

const ALLOWED_SCHEMES = ['http:', 'https:']

/** Returns the original URL if safe, else an empty string. */
export function safeMediaUrl(url: unknown): string {
  if (typeof url !== 'string' || !url) return ''
  const trimmed = url.trim()
  if (!trimmed) return ''
  // Same-origin relative paths are always safe
  if (trimmed.startsWith('/')) return trimmed
  // Try parsing as absolute — reject anything not in the scheme allowlist
  try {
    const u = new URL(trimmed)
    if (!ALLOWED_SCHEMES.includes(u.protocol)) return ''
    return trimmed
  } catch {
    // Not a valid URL — refuse to bind
    return ''
  }
}

/** Truncate user-supplied text for display. Belt-and-braces over server cap. */
export function safeTitle(s: unknown, max = 200): string {
  if (typeof s !== 'string') return ''
  return s.length > max ? s.slice(0, max) + '…' : s
}
