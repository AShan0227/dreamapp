<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Co-Dream Lobby</text>
      <view class="back" />
    </view>

    <text class="subtitle">Public co-dream sessions — anyone can join. Tonight's themes 👇</text>

    <view v-if="lobbies.length === 0" class="empty">
      <text class="empty-icon">🌌</text>
      <text class="empty-title">No public sessions yet</text>
      <text class="empty-hint">Create one — make it public so others can join.</text>
      <view class="btn btn-primary" @tap="goCreate"><text class="btn-text">Open a public session</text></view>
    </view>

    <view v-for="s in lobbies" :key="s.id" class="lobby-card" @tap="goSession(s)">
      <view class="lobby-head">
        <text class="lobby-title">{{ s.title }}</text>
        <text class="lobby-count">{{ s.current_participants }}/{{ s.max_participants }}</text>
      </view>
      <text class="lobby-theme">{{ s.theme }}</text>
      <view class="lobby-meta">
        <text class="invite-code">{{ s.invite_code }}</text>
        <text class="lobby-status" :class="'st-' + s.status">{{ s.status }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { codreamLobby } from '@/api/dream'

const lobbies = ref<any[]>([])

onMounted(async () => {
  try { lobbies.value = await codreamLobby() || [] } catch {}
})

function goSession(s: any) {
  uni.navigateTo({ url: `/pages/codream/codream?id=${s.id}` })
}
function goCreate() { uni.navigateTo({ url: '/pages/codream/codream' }) }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.lobby-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.lobby-head { display: flex; justify-content: space-between; align-items: center; }
.lobby-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 500; }
.lobby-count { color: var(--dream-primary-300); font-size: var(--dream-text-sm); font-variant-numeric: tabular-nums; }
.lobby-theme { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); display: block; margin: 6rpx 0; line-height: 1.4; }
.lobby-meta { display: flex; gap: var(--dream-space-2); margin-top: var(--dream-space-2); }
.invite-code { color: var(--dream-text-accent); font-size: var(--dream-text-sm); font-family: var(--dream-font-mono); }
.lobby-status { font-size: 18rpx; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.st-open { background: rgba(20,184,166,0.15); color: #5eead4; }
.st-recording { background: rgba(245,158,11,0.15); color: #fbbf24; }

.empty { padding: 100rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8rpx; }
.empty-icon { font-size: 80rpx; }
.empty-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); }
.empty-hint { color: var(--dream-text-muted); font-size: var(--dream-text-sm); margin-bottom: var(--dream-space-3); }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-2) var(--dream-space-4); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }
</style>
