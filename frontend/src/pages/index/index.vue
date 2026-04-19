<template>
  <view class="page dc-screen">
    <!-- First-session cinematic splash (2.6s, skip with tap) -->
    <DreamSplash />

    <!-- Cinematic atmosphere — shown always, softer when user has content -->
    <DreamAtmosphere
      :variant="dreams.length === 0 ? 'moonrise' : 'solaris'"
      :star-count="dreams.length === 0 ? 80 : 40"
      :pollen="dreams.length === 0"
      :rays="dreams.length === 0"
    />

    <!-- Header — film-title style -->
    <view class="page-header">
      <view class="header-row">
        <view class="header-left">
          <text class="page-eyebrow dc-eyebrow">dreamapp</text>
          <text class="page-title dc-display">Your dreams, a cinema</text>
        </view>
        <view class="header-right">
          <view class="header-score" v-if="dreams.length > 0">
            <text class="score-num">{{ dreams.length }}</text>
            <text class="score-label">dreams</text>
          </view>
          <view class="profile-btn" @tap="goTo('/pages/profile/profile')">
            <text class="profile-icon">&#x2699;</text>
          </view>
        </view>
      </view>
    </view>

    <!-- Quick Actions -->
    <scroll-view class="quick-scroll" scroll-x v-if="dreams.length > 0">
      <view class="quick-row">
        <view class="quick-card glass-card" @tap="goTo('/pages/health/health')">
          <text class="quick-icon">&#x1F4CA;</text>
          <text class="quick-name">Health</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/temporal/temporal')">
          <text class="quick-icon">&#x1F501;</text>
          <text class="quick-name">Patterns</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/dejareve/dejareve')">
          <text class="quick-icon">&#x1F310;</text>
          <text class="quick-name">Deja Reve</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/social/social')">
          <text class="quick-icon">&#x1F465;</text>
          <text class="quick-name">Match</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/codream/codream')">
          <text class="quick-icon">&#x1F91D;</text>
          <text class="quick-name">Co-Dream</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/customize/customize')">
          <text class="quick-icon">&#x1F3A8;</text>
          <text class="quick-name">Customize</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/remix/remix')">
          <text class="quick-icon">&#x267B;</text>
          <text class="quick-name">Remix</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/incubation/incubation')">
          <text class="quick-icon">&#x1F319;</text>
          <text class="quick-name">Incubate</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/ips/ips')">
          <text class="quick-icon">&#x2728;</text>
          <text class="quick-name">Mythology</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/agents/agents')">
          <text class="quick-icon">&#x1F916;</text>
          <text class="quick-name">Agents</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/agent-store/agent-store')">
          <text class="quick-icon">&#x1F6CD;</text>
          <text class="quick-name">Store</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/vibe/vibe')">
          <text class="quick-icon">&#x1F9EC;</text>
          <text class="quick-name">Vibe</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/subscription/subscription')">
          <text class="quick-icon">&#x1F451;</text>
          <text class="quick-name">Subscribe</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/wallet/wallet')">
          <text class="quick-icon">&#x1F4B0;</text>
          <text class="quick-name">Wallet</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/therapists/therapists')">
          <text class="quick-icon">&#x1F9D1;&#x200D;&#x2695;&#xFE0F;</text>
          <text class="quick-name">Therapists</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/challenges/challenges')">
          <text class="quick-icon">&#x1F3AF;</text>
          <text class="quick-name">Challenges</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/lobby/lobby')">
          <text class="quick-icon">&#x1F30C;</text>
          <text class="quick-name">Lobby</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/sleep/sleep')">
          <text class="quick-icon">&#x1F4A4;</text>
          <text class="quick-name">Sleep</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/foryou/foryou')">
          <text class="quick-icon">&#x2728;</text>
          <text class="quick-name">For You</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/inbox/inbox')">
          <text class="quick-icon">&#x1F514;</text>
          <text class="quick-name">Activity</text>
          <text v-if="inboxUnread > 0" class="unread-badge">{{ inboxUnread > 99 ? '99+' : inboxUnread }}</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/dm/dm')">
          <text class="quick-icon">&#x2709;</text>
          <text class="quick-name">Messages</text>
        </view>
        <view class="quick-card glass-card" @tap="goTo('/pages/bookmarks/bookmarks')">
          <text class="quick-icon">&#x1F516;</text>
          <text class="quick-name">Saved</text>
        </view>
      </view>
    </scroll-view>

    <!-- Loading -->
    <view class="dream-list" v-if="loading">
      <view class="skeleton-card" v-for="i in 3" :key="i">
        <view class="skeleton skel-visual"></view>
        <view class="skel-body">
          <view class="skeleton skel-title"></view>
          <view class="skeleton skel-sub"></view>
        </view>
      </view>
    </view>

    <!-- Error -->
    <view class="empty-dream" v-else-if="loadError">
      <text class="empty-icon-dream">&#x26A0;</text>
      <text class="empty-title-text">Connection failed</text>
      <text class="empty-desc-text">Backend not reachable</text>
      <view class="btn-dream btn-primary-dream" @tap="reload">
        <text>Retry</text>
      </view>
    </view>

    <!-- Empty / First-time onboarding — cinematic hero -->
    <view class="onboarding-hero" v-else-if="dreams.length === 0">
      <!-- Big breathing moon as the focal point -->
      <view class="hero-moon-wrap">
        <view class="dc-moon hero-moon-orb dc-breathe"></view>
      </view>

      <text class="hero-eyebrow dc-eyebrow">tonight · a film begins</text>
      <text class="hero-title dc-display">把你的梦<br/>变成一部电影</text>
      <text class="hero-sub dc-narrative">记录 · 解读 · 可视化</text>

      <!-- Three acts, like a film reel -->
      <view class="hero-acts">
        <view class="hero-act">
          <text class="act-label dc-eyebrow">Act I</text>
          <text class="act-title">说出来</text>
          <text class="act-desc dc-narrative">对着它讲你的梦,AI 会温柔地追问细节</text>
        </view>
        <view class="hero-act">
          <text class="act-label dc-eyebrow">Act II</text>
          <text class="act-title">被看见</text>
          <text class="act-desc dc-narrative">荣格、弗洛伊德、当代脑科学一起来读</text>
        </view>
        <view class="hero-act">
          <text class="act-label dc-eyebrow">Act III</text>
          <text class="act-title">被看到</text>
          <text class="act-desc dc-narrative">电影级 AI 生成,你的梦真的放映出来</text>
        </view>
      </view>

      <view class="hero-ctas">
        <view class="dc-portal hero-portal" @tap="goRecord">
          <text class="portal-text">记录第一个梦</text>
        </view>
        <view class="hero-ghost" @tap="trySampleDream">
          <text class="ghost-text">先看一个样例 →</text>
        </view>
      </view>

      <text class="hero-legal">
        端到端私密 · 涉及危机话题自动转诊 · 不卖你的梦
      </text>
    </view>

    <!-- Dream Cards — film-still composition -->
    <scroll-view class="dream-list" scroll-y v-else>
      <view class="list-section-label dc-eyebrow">tonight's reel · {{ dreams.length }} dreams</view>
      <view
        v-for="(dream, idx) in dreams"
        :key="dream.id"
        class="dream-card"
        @tap="goToDream(dream.id)"
      >
        <!-- Reel index (like film-canister label) -->
        <text class="reel-index dc-font-caption">№ {{ String(dreams.length - idx).padStart(3, '0') }}</text>

        <!-- Visual — full-bleed -->
        <view class="card-visual">
          <video
            v-if="dream.video_url"
            :src="dream.video_url"
            class="card-video"
            :controls="false"
            :autoplay="false"
            :muted="true"
            object-fit="cover"
          />
          <view v-else class="card-gradient" :class="getGradient(dream)">
            <view class="card-status-dot dot-pulse" :class="'dot-' + dream.status"></view>
          </view>
          <!-- Film grain overlay -->
          <view class="card-grain dc-grain"></view>
          <!-- Badge -->
          <view class="card-badge" :class="'badge-' + dream.status">
            <text>{{ getStatusText(dream.status) }}</text>
          </view>
          <!-- Gradient caption bar -->
          <view class="card-caption-gradient"></view>
          <view class="card-caption">
            <text class="card-title dc-display">{{ dream.title || 'Untitled' }}</text>
            <view class="card-meta">
              <text class="card-date">{{ formatDate(dream.created_at) }}</text>
              <text class="card-aesthetic">· {{ getAesthetic(dream) }}</text>
            </view>
          </view>
        </view>

        <!-- Chips strip below -->
        <view class="card-chips" v-if="dream.emotion_tags?.length || dream.symbol_tags?.length">
          <text v-for="tag in dream.emotion_tags?.slice(0, 2)" :key="'e' + tag" class="chip-dream chip-emotion">{{ tag }}</text>
          <text v-for="tag in dream.symbol_tags?.slice(0, 3)" :key="'s' + tag" class="chip-dream">{{ tag }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- FAB — a glowing portal button (hidden on empty state, portal CTA covers it) -->
    <view class="fab-dream dc-breathe" v-if="dreams.length > 0" @tap="goRecord">
      <view class="fab-glow"></view>
      <text class="fab-icon">+</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'
import DreamSplash from '@/components/DreamSplash.vue'
import { listDreams, unreadCount, type Dream } from '../../api/dream'

const dreams = ref<Dream[]>([])
const inboxUnread = ref(0)
const loading = ref(false)
const loadError = ref(false)

onShow(() => { reload() })

async function reload() {
  loading.value = true
  loadError.value = false
  try {
    dreams.value = await listDreams()
  } catch {
    loadError.value = true
  }
  loading.value = false
  // Fire-and-forget: unread inbox count for the bell badge
  try { inboxUnread.value = (await unreadCount()).count } catch {}
}

function goRecord() { uni.switchTab({ url: '/pages/record/record' }) }
function goToDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function goTo(url: string) { uni.navigateTo({ url }) }

function trySampleDream() {
  // Open record with a prefilled sample so new users can feel the full loop
  // without needing to write their own dream first.
  uni.switchTab({
    url: '/pages/record/record',
    success: () => {
      // Record page reads this from storage on mount if present
      uni.setStorageSync('sample_dream_seed',
        '我在一条没有尽头的走廊里走,天花板的灯一盏盏熄掉。' +
        '回头时发现门都不见了。有东西跟在我后面,我不敢回头看。'
      )
    },
  })
  try {
    const { trackEvent } = require('../../api/analytics')
    trackEvent('onboarding_step', { step: 'sample_dream_clicked' })
  } catch {}
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const hrs = (now.getTime() - d.getTime()) / 3600000
  if (hrs < 1) return 'Just now'
  if (hrs < 24) return `${Math.floor(hrs)}h ago`
  if (hrs < 48) return 'Yesterday'
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function getStatusText(s: string) {
  return { completed: 'Done', generating: 'Rendering', scripted: 'Ready', interviewing: 'Recording', failed: 'Failed' }[s] || s
}

import { gradientClassForDream, variantForDream, aestheticLabel } from '../../utils/dream-aesthetic'
function getGradient(d: Dream) {
  return gradientClassForDream(d)
}
function getAesthetic(d: Dream) {
  return aestheticLabel(variantForDream(d))
}
</script>

<style scoped>
.page {
  position: relative;
  min-height: 100vh;
  padding-bottom: 200rpx;
  z-index: 1;
}

/* ===== Header ========================================================= */
.page-header { position: relative; z-index: 2; padding: 60rpx 40rpx 24rpx; }
.header-row { display: flex; justify-content: space-between; align-items: flex-end; }
.header-left { display: flex; flex-direction: column; gap: 6rpx; }
.page-eyebrow { display: block; }
.page-title {
  font-size: 42rpx;
  line-height: 1.15;
  display: block;
  max-width: 500rpx;
}
.header-right { display: flex; align-items: center; gap: 16rpx; }
.header-score {
  display: flex; flex-direction: column; align-items: center;
  padding: 12rpx 20rpx;
  background: rgba(20, 10, 54, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 16rpx;
}
.score-num {
  font-family: var(--dc-font-display);
  font-size: 44rpx;
  font-weight: 500;
  color: var(--dc-solaris-pearl);
  line-height: 1;
}
.score-label {
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  margin-top: 4rpx;
}
.profile-btn {
  width: 72rpx;
  height: 72rpx;
  border-radius: 50%;
  background: rgba(139,92,246,0.12);
  border: 1rpx solid rgba(196,181,253,0.25);
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
}
.profile-icon { color: var(--dc-solaris-pearl); font-size: 34rpx; }

/* ===== Quick Actions scroll ========================================== */
.quick-scroll { position: relative; z-index: 2; white-space: nowrap; padding: 16rpx 40rpx 24rpx; }
.quick-row { display: inline-flex; gap: 18rpx; }
.quick-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18rpx 16rpx;
  gap: 8rpx;
  width: 140rpx;
  flex-shrink: 0;
  border-radius: 22rpx;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.65) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.12);
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
  transition: transform 200ms ease, border-color 200ms ease;
}
.quick-card:active {
  transform: scale(0.96);
  border-color: rgba(167, 139, 250, 0.4);
}
.quick-icon {
  font-size: 44rpx;
  filter: drop-shadow(0 0 12rpx rgba(196, 181, 253, 0.3));
}
.quick-name {
  font-size: 22rpx;
  letter-spacing: 0.06em;
  color: var(--dream-text-secondary);
  font-family: var(--dc-font-caption);
  text-transform: uppercase;
}
.unread-badge {
  position: absolute;
  top: 8rpx; right: 8rpx;
  background: linear-gradient(135deg, #ec4899, #f43f5e);
  color: white;
  font-size: 18rpx;
  font-weight: 700;
  padding: 2rpx 10rpx;
  border-radius: 9999rpx;
  min-width: 28rpx;
  text-align: center;
  line-height: 1.4;
  box-shadow: 0 0 12rpx rgba(236, 72, 153, 0.5);
}

/* ===== Dream list + film-still cards ================================= */
.dream-list {
  position: relative;
  z-index: 2;
  padding: 0 32rpx;
  height: calc(100vh - 380rpx);
}
.list-section-label {
  display: block;
  padding: 16rpx 8rpx 24rpx;
}

.dream-card {
  position: relative;
  margin-bottom: 40rpx;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 16rpx 48rpx rgba(0, 0, 0, 0.5), 0 0 0 1rpx rgba(196, 181, 253, 0.08);
  transition: transform 300ms ease, box-shadow 300ms ease;
}
.dream-card:active {
  transform: translateY(2rpx);
  box-shadow: 0 8rpx 24rpx rgba(0, 0, 0, 0.6), 0 0 0 1rpx rgba(167, 139, 250, 0.25);
}

.reel-index {
  position: absolute;
  top: 20rpx; left: 24rpx;
  z-index: 4;
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.25em;
  color: rgba(248, 244, 255, 0.7);
  text-shadow: 0 0 8rpx rgba(0, 0, 0, 0.9);
  text-transform: uppercase;
}

.card-visual {
  width: 100%;
  height: 460rpx;
  position: relative;
  overflow: hidden;
}
.card-video { width: 100%; height: 100%; }
.card-gradient {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.card-gradient::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 50% 40% at 40% 30%, rgba(255,255,255,0.08), transparent 70%),
    radial-gradient(ellipse 60% 50% at 70% 80%, rgba(139,92,246,0.12), transparent 70%);
}

/* Emotion-mapped film-still gradients (see utils/dream-aesthetic.ts) */
.grad-moonrise   { background: var(--dc-grad-moonrise); }
.grad-inception  { background: var(--dc-grad-inception); }
.grad-spirited   { background: var(--dc-grad-spirited); }
.grad-shinkai    { background: var(--dc-grad-shinkai); }
.grad-mulholland { background: var(--dc-grad-mulholland); }
.grad-solaris    { background: var(--dc-grad-solaris); }
/* Legacy aliases — keep so unmodified code still renders */
.grad-default    { background: var(--dc-grad-moonrise); }
.grad-dark       { background: var(--dc-grad-mulholland); }
.grad-warm       { background: var(--dc-grad-spirited); }
.grad-cool       { background: var(--dc-grad-solaris); }

.card-grain {
  position: absolute;
  inset: 0;
  z-index: 2;
  opacity: 0.06;
  mix-blend-mode: overlay;
}

.card-badge {
  position: absolute;
  top: 20rpx; right: 24rpx;
  z-index: 4;
  padding: 6rpx 14rpx;
  border-radius: 9999rpx;
  font-size: 20rpx;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
}
.badge-completed   { background: rgba(110, 231, 183, 0.2); color: #6ee7b7; border: 1rpx solid rgba(110,231,183,0.3); }
.badge-generating  { background: rgba(249, 160, 63, 0.18); color: #f9a03f; border: 1rpx solid rgba(249,160,63,0.3); }
.badge-scripted    { background: rgba(167, 139, 250, 0.2); color: #c4b5fd; border: 1rpx solid rgba(196,181,253,0.3); }
.badge-interviewing{ background: rgba(167, 139, 250, 0.12); color: #a78bfa; border: 1rpx solid rgba(196,181,253,0.2); }
.badge-failed      { background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1rpx solid rgba(239,68,68,0.3); }

.card-status-dot {
  width: 16rpx; height: 16rpx; border-radius: 50%;
  animation: dream-dot-pulse 2s ease-in-out infinite;
}
.dot-completed    { background: #6ee7b7; box-shadow: 0 0 16rpx #6ee7b7; }
.dot-generating   { background: #f9a03f; box-shadow: 0 0 16rpx #f9a03f; }
.dot-scripted     { background: #c4b5fd; box-shadow: 0 0 16rpx #c4b5fd; }
.dot-interviewing { background: #a78bfa; box-shadow: 0 0 16rpx #a78bfa; }
@keyframes dream-dot-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.4); opacity: 0.6; }
}

/* Bottom caption with fade gradient */
.card-caption-gradient {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 220rpx;
  background: linear-gradient(180deg, transparent 0%, rgba(3, 2, 16, 0.85) 70%, rgba(3, 2, 16, 0.95) 100%);
  z-index: 3;
  pointer-events: none;
}
.card-caption {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  z-index: 4;
  padding: 24rpx 32rpx;
  display: flex; flex-direction: column; gap: 4rpx;
}
.card-title {
  font-size: 38rpx;
  line-height: 1.2;
  font-weight: 500;
  /* Override .dc-display clip — caption needs pure color */
  background: none;
  -webkit-background-clip: unset;
  background-clip: unset;
  color: var(--dc-solaris-pearl);
  text-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.6);
  display: block;
  max-width: 520rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 8rpx;
  margin-top: 6rpx;
}
.card-date,
.card-aesthetic {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(248, 244, 255, 0.6);
  display: inline-block;
}
.card-aesthetic { color: rgba(196, 181, 253, 0.85); }

.card-chips {
  display: flex;
  gap: 10rpx;
  flex-wrap: wrap;
  padding: 16rpx 24rpx 20rpx;
  background: rgba(10, 8, 32, 0.55);
}
.chip-dream {
  font-size: 22rpx;
  letter-spacing: 0.05em;
  padding: 6rpx 14rpx;
  border-radius: 9999rpx;
  color: rgba(248, 244, 255, 0.8);
  background: rgba(139, 92, 246, 0.1);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
}
.chip-emotion {
  background: rgba(236, 72, 153, 0.08);
  border-color: rgba(236, 72, 153, 0.25);
  color: #fbcfe8;
}

/* ===== Skeleton ===================================================== */
.skeleton-card {
  background: rgba(20, 10, 54, 0.5);
  border-radius: 24rpx;
  overflow: hidden;
  margin-bottom: 40rpx;
}
.skeleton {
  background: linear-gradient(90deg, rgba(139, 92, 246, 0.08) 0%, rgba(196, 181, 253, 0.14) 50%, rgba(139, 92, 246, 0.08) 100%);
  background-size: 200% 100%;
  animation: skel-shimmer 2s ease-in-out infinite;
}
@keyframes skel-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.skel-visual { width: 100%; height: 460rpx; }
.skel-body { padding: 20rpx 32rpx; }
.skel-title { width: 60%; height: 32rpx; border-radius: 8rpx; margin-bottom: 10rpx; }
.skel-sub   { width: 40%; height: 20rpx; border-radius: 8rpx; }

/* ===== Empty / Error ================================================ */
.empty-dream {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 60rpx;
  text-align: center;
}
.empty-icon-dream { font-size: 96rpx; margin-bottom: 24rpx; opacity: 0.7; }
.empty-title-text {
  font-family: var(--dc-font-display);
  font-size: 40rpx;
  color: var(--dc-solaris-pearl);
  display: block;
  margin-bottom: 12rpx;
}
.empty-desc-text {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 26rpx;
  color: var(--dream-text-muted);
  margin-bottom: 40rpx;
}

/* ===== FAB — glowing portal ======================================== */
.fab-dream {
  position: fixed;
  bottom: 80rpx;
  right: 40rpx;
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: var(--dc-grad-aurora);
  display: flex; align-items: center; justify-content: center;
  z-index: 10;
  box-shadow: var(--dc-halo-violet), inset 0 2rpx 0 rgba(255,255,255,0.2);
  position: fixed;
}
.fab-glow {
  position: absolute;
  inset: -30rpx;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.4), transparent 60%);
  animation: dc-breathe var(--dc-breath) ease-in-out infinite;
  z-index: -1;
  pointer-events: none;
}
.fab-icon { color: white; font-size: 56rpx; font-weight: 200; line-height: 1; }

/* ===== Onboarding hero (empty state) ================================ */
.onboarding-hero {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40rpx 56rpx 80rpx;
  text-align: center;
}
.hero-moon-wrap {
  margin: 16rpx 0 40rpx;
  display: flex;
  justify-content: center;
}
.hero-moon-orb {
  width: 200rpx;
  height: 200rpx;
}
.hero-eyebrow { display: block; margin-bottom: 16rpx; }
.hero-title {
  font-size: 76rpx;
  line-height: 1.15;
  letter-spacing: 0.02em;
  display: block;
  margin-bottom: 24rpx;
}
.hero-sub {
  font-size: 30rpx;
  color: var(--dream-text-secondary);
  letter-spacing: 0.2em;
  display: block;
  margin-bottom: 72rpx;
  text-transform: uppercase;
}

/* Three acts — film reel layout */
.hero-acts {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  margin-bottom: 72rpx;
}
.hero-act {
  position: relative;
  padding: 32rpx 36rpx;
  background: linear-gradient(135deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 24rpx;
  text-align: left;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  overflow: hidden;
}
.hero-act::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3rpx;
  background: linear-gradient(180deg, transparent, var(--dc-aurora-violet), transparent);
}
.act-label { display: block; margin-bottom: 10rpx; opacity: 0.9; }
.act-title {
  font-family: var(--dc-font-display);
  font-size: 40rpx;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--dc-solaris-pearl);
  display: block;
  margin-bottom: 8rpx;
}
.act-desc {
  font-size: 26rpx;
  color: var(--dream-text-secondary);
  line-height: 1.6;
  display: block;
}

/* CTA group */
.hero-ctas {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20rpx;
  width: 100%;
}
.hero-portal {
  width: 100%;
  max-width: 480rpx;
  min-width: unset;
  padding: 28rpx 48rpx;
}
.portal-text {
  color: #ffffff;
  font-family: var(--dc-font-display);
  font-size: 32rpx;
  letter-spacing: 0.1em;
  font-weight: 500;
  position: relative;
  z-index: 1;
}
.hero-ghost {
  padding: 14rpx 24rpx;
}
.ghost-text {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 26rpx;
  color: var(--dc-aurora-lavender);
  letter-spacing: 0.04em;
}

.hero-legal {
  margin-top: 56rpx;
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  color: var(--dream-text-muted);
  line-height: 1.8;
  opacity: 0.5;
  text-transform: uppercase;
}

/* Utility: line-break tolerance for Chinese titles */
.hero-title br { display: block; content: ""; margin-top: 6rpx; }
</style>
