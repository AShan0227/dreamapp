<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Dream Matching</text>
      <view class="back" />
    </view>

    <text class="subtitle">Compatible dreamers — based on shared symbols, themes, and emotions across your archive.</text>

    <view v-if="loading && users.length === 0">
      <view v-for="i in 3" :key="i" class="skel" />
    </view>

    <view v-else-if="users.length === 0" class="empty-state">
      <text class="empty-icon">&#x1F30C;</text>
      <text class="empty-title">No matches yet</text>
      <text class="empty-hint">Record at least 2-3 dreams to build a dream signature, then come back.</text>
    </view>

    <view v-for="u in users" :key="u.match_id" class="match-card">
      <view class="match-head">
        <view class="avatar">{{ (u.nickname || 'D').charAt(0) }}</view>
        <view class="match-info">
          <text class="match-name">{{ u.nickname || 'Anonymous Dreamer' }}</text>
          <text class="match-sim">{{ (u.similarity * 100).toFixed(0) }}% dream compatibility</text>
        </view>
      </view>
      <view class="theme-row">
        <text v-for="t in u.shared_themes.slice(0,5)" :key="t" class="tag">{{ t }}</text>
      </view>
      <text class="match-count">{{ u.shared_count }} shared themes</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { matchingCompatibleUsers } from '@/api/dream'

const users = ref<any[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try { users.value = await matchingCompatibleUsers(15) || [] } catch {}
  loading.value = false
})

function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.match-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.match-head { display: flex; gap: var(--dream-space-3); margin-bottom: var(--dream-space-3); align-items: center; }
.avatar { width: 80rpx; height: 80rpx; border-radius: 50%; background: var(--dream-gradient-aurora); display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; font-size: var(--dream-text-md); }
.match-info { flex: 1; }
.match-name { font-size: var(--dream-text-md); color: var(--dream-text-primary); display: block; }
.match-sim { font-size: var(--dream-text-sm); color: var(--dream-primary-300); display: block; margin-top: 4rpx; }
.theme-row { display: flex; gap: 6rpx; flex-wrap: wrap; margin-bottom: var(--dream-space-2); }
.tag { font-size: 18rpx; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); background: rgba(139,92,246,0.15); color: #c4b5fd; }
.match-count { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }

.empty-state { padding: 100rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: var(--dream-space-2); }
.empty-icon { font-size: 80rpx; color: var(--dream-text-muted); }
.empty-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); }
.empty-hint { font-size: var(--dream-text-sm); color: var(--dream-text-muted); line-height: 1.5; }
.skel { height: 200rpx; background: rgba(255,255,255,0.04); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); }
</style>
