<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Dream Challenges</text>
      <view class="back" />
    </view>

    <text class="subtitle">Same prompt, many dreamers. Submit, get votes, climb the leaderboard.</text>

    <view v-if="challenges.length === 0" class="empty">
      <text class="empty-icon">🎯</text>
      <text class="empty-title">No active challenges</text>
      <text class="empty-hint">Check back this week.</text>
    </view>

    <view v-for="ch in challenges" :key="ch.id" class="ch-card">
      <view class="ch-head">
        <text class="ch-title">{{ ch.title }}</text>
        <text class="ch-count">{{ ch.submission_count || 0 }} entries</text>
      </view>
      <text class="ch-keyword">#{{ ch.keyword }}</text>
      <text class="ch-prompt">{{ ch.prompt }}</text>
      <view class="ch-actions">
        <view class="btn btn-secondary flex1" @tap="goLeaderboard(ch.id)">
          <text class="btn-text">Leaderboard</text>
        </view>
        <view class="btn btn-primary flex1" @tap="onJoin(ch)">
          <text class="btn-text">Submit a dream</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listChallenges, listDreams, submitChallenge } from '@/api/dream'

const challenges = ref<any[]>([])

onMounted(async () => {
  try { challenges.value = await listChallenges() || [] } catch {}
})

async function onJoin(ch: any) {
  let dreams: any[] = []
  try { dreams = (await listDreams(0, 30)).filter((d: any) => d.dream_script) } catch {}
  if (dreams.length === 0) {
    uni.showToast({ title: 'Record a dream first', icon: 'none' }); return
  }
  const labels = dreams.map((d: any) => d.title || 'Untitled')
  uni.showActionSheet({
    itemList: labels,
    success: async (res) => {
      try {
        await submitChallenge(ch.id, dreams[res.tapIndex].id)
        uni.showToast({ title: 'Submitted!', icon: 'success' })
      } catch (e: any) {
        uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
      }
    },
  })
}

function goLeaderboard(id: string) {
  uni.navigateTo({ url: `/pages/challenges/challenges?board=${id}` })
}
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.ch-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: 6rpx; }
.ch-head { display: flex; justify-content: space-between; align-items: center; }
.ch-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 600; }
.ch-count { color: var(--dream-text-muted); font-size: var(--dream-text-xs); }
.ch-keyword { color: var(--dream-text-accent); font-size: var(--dream-text-sm); font-family: var(--dream-font-mono); }
.ch-prompt { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); line-height: 1.5; margin: 6rpx 0 var(--dream-space-2); }

.ch-actions { display: flex; gap: var(--dream-space-2); }
.flex1 { flex: 1; }
.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-2); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-secondary { background: var(--dream-bg-card); border: 1rpx solid var(--dream-border-default); }
.btn-text { color: white; font-size: var(--dream-text-sm); font-weight: 500; }

.empty { padding: 100rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8rpx; }
.empty-icon { font-size: 80rpx; }
.empty-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); }
.empty-hint { color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
</style>
