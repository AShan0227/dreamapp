<template>
  <view class="page dc-screen">
    <!-- Cinematic backdrop chosen from the report's dream_aesthetic field -->
    <DreamAtmosphere :variant="atmosphereVariant" :star-count="100" :rays="true" pollen />

    <!-- Header — minimal, just back + share -->
    <view class="header">
      <view class="back-btn" @tap="onBack">
        <text class="back-icon">←</text>
      </view>
      <text class="header-title dc-eyebrow">{{ slug ? 'a wrapped' : 'your wrapped' }}</text>
      <view class="back-btn" @tap="onShare" v-if="report?.share_slug">
        <text class="back-icon">↗</text>
      </view>
      <view class="back-btn" v-else />
    </view>

    <!-- Loading -->
    <view v-if="loading" class="state-msg">
      <text class="state-text dc-narrative">Composing your year in dreams…</text>
    </view>

    <!-- Error -->
    <view v-else-if="error" class="state-msg">
      <text class="state-text dc-narrative">{{ error }}</text>
    </view>

    <!-- Empty -->
    <view v-else-if="report?.empty" class="state-msg">
      <view class="dc-moon empty-moon dc-breathe"></view>
      <text class="empty-eyebrow dc-eyebrow">no dreams yet · {{ report.period }}</text>
      <text class="empty-title dc-display">Wrapped wakes up<br/>after your first dream.</text>
    </view>

    <!-- Wrapped reel — 5 frames -->
    <scroll-view v-else-if="report" class="reel" scroll-y>
      <!-- FRAME 1 — hero number -->
      <view class="frame frame-hero">
        <text class="period-label dc-eyebrow">{{ formatPeriod(report.period) }}</text>
        <text class="hero-num dc-display">{{ report.headline_number }}</text>
        <text class="hero-label dc-narrative">
          {{ isZh ? report.headline_label_zh : report.headline_label_en }}
        </text>
        <view class="hero-stat-row">
          <view class="hero-stat">
            <text class="hero-stat-num">{{ report.streak_peak ?? 0 }}</text>
            <text class="hero-stat-label dc-eyebrow">streak peak</text>
          </view>
          <view class="hero-stat-divider"></view>
          <view class="hero-stat">
            <text class="hero-stat-num">{{ Math.round((report.nightmare_rate ?? 0) * 100) }}%</text>
            <text class="hero-stat-label dc-eyebrow">nightmares</text>
          </view>
          <view class="hero-stat-divider"></view>
          <view class="hero-stat">
            <text class="hero-stat-num">{{ report.dream_aesthetic || '—' }}</text>
            <text class="hero-stat-label dc-eyebrow">aesthetic</text>
          </view>
        </view>
      </view>

      <view class="dc-divider"></view>

      <!-- FRAME 2 — top symbols -->
      <view class="frame">
        <text class="frame-eyebrow dc-eyebrow">your symbols</text>
        <text class="frame-title dc-display">things that kept showing up</text>
        <view class="bar-list">
          <view
            v-for="(s, i) in (report.top_symbols || [])"
            :key="s.name"
            class="bar-row"
          >
            <text class="bar-rank">{{ String(i + 1).padStart(2, '0') }}</text>
            <view class="bar-label">{{ s.name }}</view>
            <view class="bar-track">
              <view class="bar-fill" :style="{ width: barPct(s.count, maxSymbol) + '%' }"></view>
            </view>
            <text class="bar-count">{{ s.count }}</text>
          </view>
          <text v-if="!report.top_symbols?.length" class="frame-empty">no recurring symbols yet</text>
        </view>
      </view>

      <view class="dc-divider"></view>

      <!-- FRAME 3 — top emotions -->
      <view class="frame">
        <text class="frame-eyebrow dc-eyebrow">your weather</text>
        <text class="frame-title dc-display">how the dreams felt</text>
        <view class="emo-grid">
          <view
            v-for="(e, i) in (report.top_emotions || [])"
            :key="e.name"
            class="emo-pill"
            :class="'emo-' + i"
          >
            <text class="emo-name">{{ e.name }}</text>
            <text class="emo-pct">{{ Math.round(e.count / report.total_dreams * 100) }}%</text>
          </view>
          <text v-if="!report.top_emotions?.length" class="frame-empty">no emotion tags yet</text>
        </view>
      </view>

      <view class="dc-divider"></view>

      <!-- FRAME 4 — most intense -->
      <view class="frame frame-spotlight" v-if="report.most_intense_dream_title">
        <text class="frame-eyebrow dc-eyebrow">the loudest one</text>
        <text class="spotlight-title dc-display">{{ report.most_intense_dream_title }}</text>
        <text class="spotlight-sub dc-narrative">
          the dream this {{ periodWord }} that registered the strongest emotional charge
        </text>
      </view>

      <view class="dc-divider" v-if="report.most_intense_dream_title"></view>

      <!-- FRAME 5 — closing + share -->
      <view class="frame frame-close">
        <view class="dc-moon close-moon dc-breathe"></view>
        <text class="close-eyebrow dc-eyebrow">a year of dreaming</text>
        <text class="close-line dc-narrative" v-if="report.first_dream_title">
          you started with “{{ report.first_dream_title }}”
        </text>
        <text class="close-line dc-narrative">
          {{ isZh ? '梦把你带回了真实的自己' : 'your dreams kept finding their way back to you' }}
        </text>

        <view class="dc-portal share-portal" @tap="onShare" v-if="report.share_slug && !slug">
          <text class="portal-text">分享你的 Wrapped</text>
        </view>
        <view class="hero-ghost" @tap="onCopyLink" v-if="report.share_slug">
          <text class="ghost-text">{{ copied ? '链接已复制 ✓' : '复制公开链接' }}</text>
        </view>
      </view>

      <view class="reel-footer">
        <text class="reel-credit dc-eyebrow">made with dreamapp</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import DreamAtmosphere from '../../components/DreamAtmosphere.vue'
import {
  getMyWrapped, getPublicWrapped, type WrappedReport,
  getApiHost,
} from '../../api/dream'

const report = ref<WrappedReport | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const slug = ref<string>('')      // populated when viewing a public Wrapped
const period = ref<string>('')
const copied = ref(false)

const isZh = computed(() => {
  try { return ((uni as any).getSystemInfoSync?.()?.language || 'zh').startsWith('zh') } catch { return true }
})

const periodWord = computed(() => {
  const p = report.value?.period || ''
  if (p.startsWith('month-')) return isZh.value ? '月' : 'month'
  if (p.includes('-Q')) return isZh.value ? '季度' : 'quarter'
  return isZh.value ? '年' : 'year'
})

const atmosphereVariant = computed(() => {
  const a = (report.value?.dream_aesthetic || '').toLowerCase()
  if (a.includes('mulholland')) return 'mulholland' as const
  if (a.includes('shinkai')) return 'shinkai' as const
  if (a.includes('spirited')) return 'spirited' as const
  if (a.includes('inception')) return 'inception' as const
  if (a.includes('solaris')) return 'solaris' as const
  return 'moonrise' as const
})

const maxSymbol = computed(() => {
  const tops = report.value?.top_symbols || []
  return tops[0]?.count || 1
})

function barPct(c: number, max: number): number {
  return Math.max(8, Math.round((c / max) * 100))
}

function formatPeriod(p: string): string {
  if (p.startsWith('month-')) {
    const ym = p.replace('month-', '')
    return isZh.value ? `${ym} 月` : ym
  }
  if (p.includes('-Q')) return p.replace('-Q', ' Q')
  return p
}

onLoad((opts: any) => {
  slug.value = opts?.slug || ''
  period.value = opts?.period || String(new Date().getFullYear())
  load()
})

async function load() {
  loading.value = true
  error.value = null
  try {
    if (slug.value) {
      report.value = await getPublicWrapped(slug.value)
    } else {
      report.value = await getMyWrapped(period.value)
    }
  } catch (e: any) {
    error.value = e?.body?.detail || 'Could not load Wrapped.'
  }
  loading.value = false
}

function onBack() { uni.navigateBack({ delta: 1 }) }

function onShare() {
  if (!report.value?.share_slug) return
  const url = `${getApiHost() || ''}/wrapped/${report.value.share_slug}`
  uni.setClipboardData({
    data: url,
    success: () => {
      copied.value = true
      uni.showToast({ title: 'Link copied', icon: 'none' })
      setTimeout(() => { copied.value = false }, 2200)
    },
  })
}

function onCopyLink() { onShare() }
</script>

<style scoped>
.page { min-height: 100vh; padding-bottom: 80rpx; position: relative; z-index: 1; }
.header, .reel, .state-msg { position: relative; z-index: 2; }

.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 80rpx 32rpx 24rpx;
}
.back-btn {
  width: 64rpx; height: 64rpx;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
}
.back-icon { color: var(--dc-solaris-pearl); font-size: 30rpx; }
.header-title { display: block; }

/* state messages */
.state-msg {
  display: flex; flex-direction: column; align-items: center;
  padding: 200rpx 60rpx; text-align: center;
}
.state-text { color: var(--dream-text-secondary); font-size: 28rpx; }
.empty-moon { width: 160rpx; height: 160rpx; margin-bottom: 40rpx; }
.empty-eyebrow { display: block; margin-bottom: 16rpx; opacity: 0.85; }
.empty-title { font-size: 48rpx; line-height: 1.3; display: block; }

/* reel layout */
.reel { padding: 0 32rpx; height: calc(100vh - 200rpx); }
.frame {
  padding: 56rpx 32rpx;
  display: flex; flex-direction: column; gap: 16rpx;
}
.frame-eyebrow { display: block; opacity: 0.85; margin-bottom: 4rpx; }
.frame-title {
  font-size: 40rpx; line-height: 1.25;
  display: block; margin-bottom: 24rpx;
}

/* hero frame */
.frame-hero {
  align-items: center; text-align: center;
  padding: 80rpx 32rpx 56rpx;
}
.period-label { display: block; margin-bottom: 24rpx; opacity: 0.85; }
.hero-num {
  font-size: 220rpx; line-height: 1;
  letter-spacing: -0.02em;
  margin-bottom: 16rpx;
  background: linear-gradient(180deg, #ffffff 0%, #f9d26e 70%, #f9a03f 100%);
  -webkit-background-clip: text;
  background-clip: text;
  text-shadow: 0 0 80rpx rgba(249, 210, 110, 0.4);
}
.hero-label {
  font-size: 30rpx; color: var(--dc-solaris-pearl);
  margin-bottom: 56rpx;
}
.hero-stat-row {
  display: flex; align-items: center; gap: 24rpx;
  margin-top: 8rpx;
}
.hero-stat { display: flex; flex-direction: column; align-items: center; gap: 6rpx; flex: 1; }
.hero-stat-num {
  font-family: var(--dc-font-display);
  font-size: 36rpx; color: var(--dc-solaris-pearl);
  letter-spacing: 0.02em;
}
.hero-stat-label { display: block; opacity: 0.75; font-size: 18rpx; }
.hero-stat-divider {
  width: 1rpx; height: 48rpx;
  background: linear-gradient(180deg, transparent, rgba(196,181,253,0.4), transparent);
}

/* bar list */
.bar-list { display: flex; flex-direction: column; gap: 18rpx; }
.bar-row { display: flex; align-items: center; gap: 14rpx; }
.bar-rank {
  font-family: var(--dc-font-caption);
  font-size: 20rpx; color: var(--dc-aurora-lavender);
  letter-spacing: 0.15em; min-width: 40rpx;
}
.bar-label {
  flex-shrink: 0; min-width: 140rpx; max-width: 220rpx;
  font-family: var(--dc-font-display);
  font-size: 26rpx; color: var(--dc-solaris-pearl);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.bar-track {
  flex: 1; height: 14rpx;
  background: rgba(3, 2, 16, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.1);
  border-radius: 9999rpx;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--dc-grad-aurora);
  box-shadow: 0 0 8rpx rgba(167, 139, 250, 0.5);
  border-radius: 9999rpx;
}
.bar-count {
  font-family: var(--dc-font-caption);
  font-size: 22rpx; color: var(--dc-solaris-pearl);
  letter-spacing: 0.05em; min-width: 40rpx; text-align: right;
}

/* emotion pills */
.emo-grid { display: flex; flex-wrap: wrap; gap: 12rpx; }
.emo-pill {
  display: inline-flex; align-items: center; gap: 8rpx;
  padding: 14rpx 22rpx;
  border-radius: 9999rpx;
  background: rgba(20, 10, 54, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  backdrop-filter: blur(10rpx);
  -webkit-backdrop-filter: blur(10rpx);
}
.emo-0 { background: linear-gradient(135deg, rgba(236, 72, 153, 0.22), rgba(167, 139, 250, 0.18)); border-color: rgba(236, 72, 153, 0.35); }
.emo-1 { background: linear-gradient(135deg, rgba(167, 139, 250, 0.22), rgba(6, 182, 212, 0.15)); border-color: rgba(167, 139, 250, 0.35); }
.emo-2 { background: linear-gradient(135deg, rgba(249, 160, 63, 0.18), rgba(236, 72, 153, 0.12)); border-color: rgba(249, 160, 63, 0.35); }
.emo-name {
  font-family: var(--dc-font-display);
  font-size: 26rpx; color: var(--dc-solaris-pearl);
}
.emo-pct {
  font-family: var(--dc-font-caption);
  font-size: 20rpx; color: var(--dc-aurora-lavender);
  letter-spacing: 0.05em;
}
.frame-empty {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  color: var(--dream-text-muted); font-size: 24rpx;
}

/* spotlight */
.frame-spotlight { align-items: flex-start; }
.spotlight-title {
  font-size: 56rpx; line-height: 1.2;
  margin: 8rpx 0 16rpx;
  background: linear-gradient(180deg, #ffffff 0%, #c4b5fd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.spotlight-sub {
  font-size: 28rpx; color: var(--dream-text-secondary); line-height: 1.6;
}

/* close frame */
.frame-close {
  align-items: center; text-align: center;
  padding: 80rpx 32rpx;
}
.close-moon { width: 160rpx; height: 160rpx; margin-bottom: 32rpx; }
.close-eyebrow { display: block; margin-bottom: 16rpx; opacity: 0.85; }
.close-line {
  font-size: 30rpx; color: var(--dc-solaris-pearl);
  margin-bottom: 16rpx; line-height: 1.5;
  max-width: 540rpx;
}
.share-portal {
  margin: 40rpx 0 8rpx;
  width: 100%; max-width: 480rpx;
  padding: 26rpx 48rpx;
  min-width: unset;
}
.portal-text {
  color: #ffffff;
  font-family: var(--dc-font-display);
  font-size: 30rpx; letter-spacing: 0.1em;
  position: relative; z-index: 1;
}
.hero-ghost { padding: 14rpx 24rpx; margin-top: 8rpx; }
.ghost-text {
  font-family: var(--dc-font-narrative); font-style: italic;
  font-size: 26rpx; color: var(--dc-aurora-lavender);
  letter-spacing: 0.04em;
}

.reel-footer { padding: 32rpx 0 64rpx; text-align: center; }
.reel-credit {
  display: block; opacity: 0.4; font-size: 18rpx; letter-spacing: 0.4em;
}
</style>
