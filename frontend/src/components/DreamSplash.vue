<template>
  <!-- Cinematic splash.
       Plays ~2.6s on first app open per session (stored in sessionStorage).
       Three frames, cross-fading:
         0–0.9s: black void, a single breathing dot expanding
         0.9–1.8s: dot becomes moon + "DreamApp" serif title fades in
         1.8–2.6s: tagline "梦 · 被看见" then fades to reveal the app
       Dismissible by tap anytime after 0.5s.
  -->
  <view v-if="visible" class="splash" :class="{ 'splash-fade-out': leaving }" @tap="onTap">
    <view class="splash-stage">
      <!-- Dot → Moon -->
      <view class="splash-moon" :class="phaseClass"></view>

      <!-- Title -->
      <view class="splash-title-wrap" :class="{ 'tw-in': phase >= 2, 'tw-out': phase >= 3 }">
        <text class="splash-eyebrow dc-eyebrow">a cinema of dreams</text>
        <text class="splash-title dc-display">DreamApp</text>
      </view>

      <!-- Tagline -->
      <view class="splash-tag" :class="{ 'tg-in': phase >= 3 }">
        <text class="splash-tag-zh">梦 · 被看见 · 被看到</text>
      </view>

      <!-- Skip hint — appears at 0.8s -->
      <text v-if="phase >= 1" class="splash-skip dc-eyebrow">tap to enter</text>
    </view>

    <!-- Film grain overlay for the whole splash -->
    <view class="dc-grain dc-grain-strong"></view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

const visible = ref(true)
const leaving = ref(false)
const phase = ref(0) // 0:void, 1:dot, 2:title, 3:tagline, 4:fadeout

const phaseClass = computed(() => `phase-${phase.value}`)

let timers: any[] = []

function startSequence() {
  // Only show once per session
  try {
    if (uni.getStorageSync('_splash_seen')) {
      visible.value = false
      return
    }
    uni.setStorageSync('_splash_seen', '1')
  } catch {}

  timers.push(setTimeout(() => { phase.value = 1 }, 200))   // dot appears
  timers.push(setTimeout(() => { phase.value = 2 }, 900))   // title fades in
  timers.push(setTimeout(() => { phase.value = 3 }, 1800))  // tagline
  timers.push(setTimeout(() => dismiss(), 2800))            // auto-fade
}

function dismiss() {
  if (leaving.value) return
  leaving.value = true
  timers.push(setTimeout(() => { visible.value = false }, 650))
}

function onTap() {
  // Allow skip after 500ms so we don't dismiss on reflex
  if (phase.value >= 1) dismiss()
}

onMounted(() => {
  startSequence()
})

import { onUnmounted } from 'vue'
onUnmounted(() => { timers.forEach(t => clearTimeout(t)) })
</script>

<style scoped>
.splash {
  position: fixed;
  inset: 0;
  z-index: 999;
  background:
    radial-gradient(ellipse at center, #0a0820 0%, #030210 70%, #000000 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 650ms ease, transform 650ms cubic-bezier(0.45, 0, 0.55, 1);
  overflow: hidden;
}
.splash-fade-out {
  opacity: 0;
  transform: scale(1.08);
  pointer-events: none;
}

.splash-stage {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32rpx;
}

/* Moon/dot — grows from 4rpx point to 180rpx orb */
.splash-moon {
  width: 4rpx;
  height: 4rpx;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 0 20rpx rgba(255, 255, 255, 0.8);
  transition: all 900ms cubic-bezier(0.65, 0, 0.35, 1);
  flex-shrink: 0;
}
.splash-moon.phase-0 {
  width: 4rpx; height: 4rpx;
  box-shadow: 0 0 8rpx rgba(255, 255, 255, 0.4);
}
.splash-moon.phase-1,
.splash-moon.phase-2,
.splash-moon.phase-3,
.splash-moon.phase-4 {
  width: 200rpx; height: 200rpx;
  background: radial-gradient(circle at 35% 35%, #f8f4ff 0%, #e0d6ff 35%, #a78bfa 75%, #6d28d9 100%);
  box-shadow:
    0 0 60rpx rgba(248, 244, 255, 0.45),
    0 0 140rpx rgba(196, 181, 253, 0.25),
    inset -24rpx -12rpx 48rpx rgba(76, 29, 149, 0.45);
  animation: splash-moon-breathe 3200ms ease-in-out infinite;
}
@keyframes splash-moon-breathe {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.04); }
}

.splash-title-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10rpx;
  opacity: 0;
  transform: translateY(16rpx);
  transition: opacity 700ms ease, transform 700ms ease;
}
.splash-title-wrap.tw-in {
  opacity: 1;
  transform: translateY(0);
}
.splash-title-wrap.tw-out {
  transition: opacity 900ms ease;
}
.splash-eyebrow {
  opacity: 0.7;
}
.splash-title {
  font-size: 92rpx;
  line-height: 1;
  letter-spacing: 0.04em;
}

/* Tagline — appears last, stays until dismissal */
.splash-tag {
  opacity: 0;
  transition: opacity 800ms ease;
  margin-top: 12rpx;
}
.splash-tag.tg-in { opacity: 0.75; }
.splash-tag-zh {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 28rpx;
  color: var(--dc-aurora-lavender);
  letter-spacing: 0.2em;
}

/* Skip hint */
.splash-skip {
  position: absolute;
  bottom: 120rpx;
  left: 50%;
  transform: translateX(-50%);
  opacity: 0.5;
  animation: splash-skip-pulse 2.4s ease-in-out infinite;
}
@keyframes splash-skip-pulse {
  0%, 100% { opacity: 0.35; }
  50%      { opacity: 0.75; }
}
</style>
