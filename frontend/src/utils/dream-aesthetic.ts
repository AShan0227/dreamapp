// Dream emotion / nightmare → cinematic aesthetic mapper.
// Returns the variant for DreamAtmosphere + a film-still gradient class
// for dream cards. Single source of truth for "this dream's mood = this look".
//
// Mapping logic:
//   - nightmare flag wins → mulholland (velvet-red dread)
//   - lucid / control / power → inception (geometric blue + amber)
//   - joy / nostalgia / warmth → spirited (lantern amber)
//   - longing / love / coming-of-age → shinkai (gold-violet twilight)
//   - sad / grief / quiet / reflective → solaris (deep teal water)
//   - default / unclassified → moonrise (purple aurora)

import type { Dream } from '../api/dream'

export type AtmosphereVariant =
  | 'moonrise'
  | 'inception'
  | 'spirited'
  | 'shinkai'
  | 'mulholland'
  | 'solaris'

const KEYWORDS: Record<AtmosphereVariant, string[]> = {
  mulholland: [
    'fear', 'terror', 'horror', 'dread', 'nightmare', 'panic', 'chase', 'chased',
    '恐惧', '恐怖', '惊', '害怕', '吓', '噩梦', '焦虑', '紧张',
  ],
  inception: [
    'lucid', 'control', 'power', 'fly', 'flying', 'flight', 'building',
    '清醒', '飞', '飞翔', '掌控', '权力', '高楼',
  ],
  spirited: [
    'joy', 'happy', 'warm', 'home', 'family', 'childhood', 'food', 'celebration',
    '快乐', '开心', '温暖', '家', '童年', '童', '团圆', '怀旧', '老房子',
  ],
  shinkai: [
    'love', 'longing', 'romance', 'crush', 'youth', 'school', 'summer', 'sunset',
    'first', 'dawn', 'twilight', 'star',
    '喜欢', '爱', '思念', '想念', '初恋', '前任', '青春', '夏天', '黄昏', '星空',
  ],
  solaris: [
    'sad', 'sadness', 'grief', 'loss', 'water', 'rain', 'ocean', 'sea', 'flood',
    'reflect', 'memory', 'quiet', 'still',
    '悲', '伤', '哭', '泪', '失去', '水', '雨', '海', '湖', '安静', '回忆',
  ],
  moonrise: [
    // catch-all default — no specific keywords
  ],
}

export function variantForDream(dream?: Pick<Dream, 'emotion_tags' | 'symbol_tags' | 'nightmare_flag'> | null): AtmosphereVariant {
  if (!dream) return 'moonrise'
  if ((dream as any).nightmare_flag) return 'mulholland'

  const haystack = [
    ...(dream.emotion_tags || []),
    ...(dream.symbol_tags || []),
  ].join(' ').toLowerCase()

  if (!haystack) return 'moonrise'

  // Score each variant by keyword hits, pick the highest-scoring
  let bestVariant: AtmosphereVariant = 'moonrise'
  let bestScore = 0
  for (const [variant, words] of Object.entries(KEYWORDS) as [AtmosphereVariant, string[]][]) {
    let score = 0
    for (const w of words) {
      if (haystack.includes(w)) score += 1
    }
    if (score > bestScore) {
      bestScore = score
      bestVariant = variant
    }
  }
  return bestVariant
}

/** CSS class for the dream-card film-still gradient. */
export function gradientClassForDream(dream?: Pick<Dream, 'emotion_tags' | 'symbol_tags' | 'nightmare_flag'> | null): string {
  const v = variantForDream(dream)
  return `grad-${v}`
}

/** Human-readable name of the aesthetic — show as a small caption next to dream. */
export function aestheticLabel(v: AtmosphereVariant): string {
  return {
    mulholland: 'Mulholland',
    inception: 'Inception',
    spirited: 'Spirited',
    shinkai: 'Shinkai',
    solaris: 'Solaris',
    moonrise: 'Moonrise',
  }[v]
}
