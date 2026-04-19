<template>
  <view class="orb-container" :class="{ 'orb-active': isActive, 'orb-listening': isListening, 'orb-thinking': isThinking }">
    <!-- Glow layers -->
    <view class="orb-glow-outer"></view>
    <view class="orb-glow-mid"></view>

    <!-- Main orb -->
    <view class="orb-body">
      <view class="orb-surface">
        <!-- Animated gradient blobs inside the orb -->
        <view class="blob blob-1"></view>
        <view class="blob blob-2"></view>
        <view class="blob blob-3"></view>
        <view class="blob blob-4"></view>
      </view>
      <!-- Shine highlight -->
      <view class="orb-highlight"></view>
    </view>

    <!-- Ripple rings when active -->
    <view class="ripple ripple-1" v-if="isActive"></view>
    <view class="ripple ripple-2" v-if="isActive"></view>
    <view class="ripple ripple-3" v-if="isActive"></view>

    <!-- Floating particles -->
    <view class="particle" v-for="i in 8" :key="i" :class="'p-' + i"></view>
  </view>
</template>

<script setup lang="ts">
defineProps<{
  isActive?: boolean    // AI is responding
  isListening?: boolean // Recording voice
  isThinking?: boolean  // Processing
}>()
</script>

<style scoped>
.orb-container {
  position: relative;
  width: 90vw;
  height: 90vw;
  max-width: 700rpx;
  max-height: 700rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* === Glow layers === */
.orb-glow-outer {
  position: absolute;
  width: 100vw;
  height: 100vw;
  max-width: 800rpx;
  max-height: 800rpx;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, rgba(45, 212, 191, 0.05) 40%, transparent 70%);
  animation: glow-breathe 4s ease-in-out infinite, blob-morph 12s ease-in-out infinite reverse;
}

.orb-glow-mid {
  position: absolute;
  width: 95vw;
  height: 95vw;
  max-width: 760rpx;
  max-height: 760rpx;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 60%);
  animation: glow-breathe 4s ease-in-out infinite 0.5s;
}

@keyframes glow-breathe {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.15); opacity: 1; }
}

/* === Main orb body — organic blob morph === */
.orb-body {
  position: relative;
  width: 75vw;
  height: 75vw;
  max-width: 600rpx;
  max-height: 600rpx;
  border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%;
  overflow: hidden;
  box-shadow:
    0 0 80rpx rgba(139, 92, 246, 0.4),
    0 0 160rpx rgba(139, 92, 246, 0.2),
    0 0 240rpx rgba(139, 92, 246, 0.1),
    inset 0 0 60rpx rgba(139, 92, 246, 0.25);
  animation: orb-float 6s ease-in-out infinite, blob-morph 8s ease-in-out infinite;
}

@keyframes orb-float {
  0%, 100% { transform: translateY(0) scale(1); }
  33% { transform: translateY(-12rpx) scale(1.03); }
  66% { transform: translateY(6rpx) scale(0.97); }
}

@keyframes blob-morph {
  0%, 100% { border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%; }
  14% { border-radius: 40% 60% 70% 30% / 40% 70% 30% 60%; }
  28% { border-radius: 50% 50% 40% 60% / 35% 65% 45% 55%; }
  42% { border-radius: 70% 30% 50% 50% / 55% 45% 60% 40%; }
  56% { border-radius: 35% 65% 60% 40% / 70% 30% 40% 60%; }
  70% { border-radius: 55% 45% 35% 65% / 45% 55% 65% 35%; }
  84% { border-radius: 45% 55% 55% 45% / 60% 40% 35% 65%; }
}

/* === Surface with animated blobs === */
.orb-surface {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, #2d1b69, #1a0a3e, #0d0d2a);
  overflow: hidden;
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(30rpx);
  mix-blend-mode: screen;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
}

.blob-1 {
  width: 55%;
  height: 55%;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.8), transparent);
  top: 10%;
  left: 10%;
  animation: blob-move-1 8s infinite;
}

.blob-2 {
  width: 45%;
  height: 45%;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.6), transparent);
  bottom: 10%;
  right: 10%;
  animation: blob-move-2 10s infinite;
}

.blob-3 {
  width: 40%;
  height: 40%;
  background: radial-gradient(circle, rgba(129, 140, 248, 0.7), transparent);
  top: 40%;
  left: 50%;
  animation: blob-move-3 7s infinite;
}

.blob-4 {
  width: 35%;
  height: 35%;
  background: radial-gradient(circle, rgba(245, 158, 11, 0.5), transparent);
  top: 20%;
  right: 20%;
  animation: blob-move-4 9s infinite;
}

@keyframes blob-move-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(40rpx, 20rpx) scale(1.2); }
  50% { transform: translate(20rpx, 60rpx) scale(0.8); }
  75% { transform: translate(-20rpx, 30rpx) scale(1.1); }
}

@keyframes blob-move-2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(-30rpx, -40rpx) scale(1.3); }
  50% { transform: translate(-50rpx, -10rpx) scale(0.9); }
  75% { transform: translate(-10rpx, -30rpx) scale(1.1); }
}

@keyframes blob-move-3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-40rpx, 30rpx) scale(1.4); }
  66% { transform: translate(20rpx, -20rpx) scale(0.7); }
}

@keyframes blob-move-4 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.4; }
  50% { transform: translate(-30rpx, 40rpx) scale(1.5); opacity: 0.8; }
}

/* === Highlight === */
.orb-highlight {
  position: absolute;
  width: 60rpx;
  height: 40rpx;
  top: 20%;
  left: 25%;
  background: radial-gradient(ellipse, rgba(255, 255, 255, 0.3), transparent);
  border-radius: 50%;
  transform: rotate(-30deg);
}

/* === Ripple rings === */
.ripple {
  position: absolute;
  border-radius: 50%;
  border: 2rpx solid rgba(139, 92, 246, 0.3);
  animation: ripple-expand 3s ease-out infinite;
}

.ripple-1 { width: 200rpx; height: 200rpx; animation-delay: 0s; }
.ripple-2 { width: 200rpx; height: 200rpx; animation-delay: 1s; }
.ripple-3 { width: 200rpx; height: 200rpx; animation-delay: 2s; }

@keyframes ripple-expand {
  0% { transform: scale(1); opacity: 0.6; }
  100% { transform: scale(2); opacity: 0; }
}

/* === Floating particles === */
.particle {
  position: absolute;
  width: 6rpx;
  height: 6rpx;
  border-radius: 50%;
  background: rgba(139, 92, 246, 0.6);
  animation: particle-float 5s ease-in-out infinite;
}

.p-1 { top: 5%; left: 20%; animation-delay: 0s; animation-duration: 4s; }
.p-2 { top: 80%; left: 15%; animation-delay: 0.5s; animation-duration: 5s; background: rgba(45, 212, 191, 0.5); }
.p-3 { top: 30%; right: 5%; animation-delay: 1s; animation-duration: 6s; }
.p-4 { bottom: 10%; right: 20%; animation-delay: 1.5s; animation-duration: 4.5s; background: rgba(129, 140, 248, 0.5); }
.p-5 { top: 10%; right: 30%; animation-delay: 2s; animation-duration: 5.5s; width: 4rpx; height: 4rpx; }
.p-6 { bottom: 25%; left: 5%; animation-delay: 2.5s; animation-duration: 4s; background: rgba(245, 158, 11, 0.4); width: 8rpx; height: 8rpx; }
.p-7 { top: 50%; left: 0%; animation-delay: 3s; animation-duration: 6.5s; width: 4rpx; height: 4rpx; }
.p-8 { top: 65%; right: 0%; animation-delay: 0.8s; animation-duration: 5s; background: rgba(45, 212, 191, 0.4); }

@keyframes particle-float {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.3; }
  25% { transform: translate(20rpx, -30rpx) scale(1.5); opacity: 0.8; }
  50% { transform: translate(-10rpx, -50rpx) scale(0.8); opacity: 0.5; }
  75% { transform: translate(15rpx, -20rpx) scale(1.2); opacity: 0.7; }
}

/* === State modifiers === */

/* Active: AI responding — orb pulses faster, blobs move quicker */
.orb-active .orb-body {
  animation-duration: 2s;
  box-shadow:
    0 0 80rpx rgba(139, 92, 246, 0.5),
    0 0 160rpx rgba(139, 92, 246, 0.25),
    inset 0 0 60rpx rgba(139, 92, 246, 0.3);
}

.orb-active .blob-1 { animation-duration: 3s; }
.orb-active .blob-2 { animation-duration: 4s; }
.orb-active .blob-3 { animation-duration: 2.5s; }
.orb-active .blob-4 { animation-duration: 3.5s; }

.orb-active .orb-glow-outer {
  animation-duration: 2s;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.25) 0%, transparent 70%);
}

/* Listening: voice recording — orb turns teal, breathes deeper */
.orb-listening .orb-body {
  box-shadow:
    0 0 80rpx rgba(45, 212, 191, 0.4),
    0 0 160rpx rgba(45, 212, 191, 0.2),
    inset 0 0 60rpx rgba(45, 212, 191, 0.3);
}

.orb-listening .orb-surface {
  background: linear-gradient(135deg, #0d4040, #0a2d3d, #0d1a2a);
}

.orb-listening .blob-1 { background: radial-gradient(circle, rgba(45, 212, 191, 0.8), transparent); }
.orb-listening .blob-2 { background: radial-gradient(circle, rgba(20, 184, 166, 0.7), transparent); }
.orb-listening .orb-glow-outer { background: radial-gradient(circle, rgba(45, 212, 191, 0.2) 0%, transparent 70%); }

/* Thinking: processing — orb spins slowly */
.orb-thinking .orb-surface {
  animation: orb-spin 4s linear infinite;
}

@keyframes orb-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
