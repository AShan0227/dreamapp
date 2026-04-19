<template>
  <view class="page">
    <view class="header">
      <text class="header-title">Dream Health</text>
      <view class="score-circle" v-if="health.health_score != null">
        <text class="score-number">{{ Math.round(health.health_score) }}</text>
        <text class="score-label">Health Score</text>
      </view>
    </view>

    <scroll-view class="content" scroll-y>
      <!-- Stats -->
      <view class="stats-row" v-if="health.total_dreams">
        <view class="stat-card">
          <text class="stat-value">{{ health.total_dreams }}</text>
          <text class="stat-label">Dreams</text>
        </view>
        <view class="stat-card">
          <text class="stat-value">{{ health.nightmare_count || 0 }}</text>
          <text class="stat-label">Nightmares</text>
        </view>
        <view class="stat-card">
          <text class="stat-value">{{ ((health.nightmare_frequency || 0) * 100).toFixed(0) }}%</text>
          <text class="stat-label">Nightmare Rate</text>
        </view>
      </view>

      <!-- Anomalies -->
      <view class="section" v-if="health.anomalies?.length">
        <text class="section-title">Anomalies Detected</text>
        <view v-for="a in health.anomalies" :key="a.type" class="anomaly-card">
          <text class="anomaly-severity" :class="'severity-' + a.severity">{{ a.severity }}</text>
          <text class="anomaly-desc">{{ a.description }}</text>
        </view>
      </view>

      <!-- Dominant Emotions -->
      <view class="section" v-if="health.dominant_emotions?.length">
        <text class="section-title">Dominant Emotions</text>
        <view class="emotion-bars">
          <view v-for="e in health.dominant_emotions" :key="e.emotion" class="emotion-bar-row">
            <text class="emotion-name">{{ e.emotion }}</text>
            <view class="emotion-bar-bg">
              <view class="emotion-bar-fill" :style="{ width: e.pct + '%' }"></view>
            </view>
            <text class="emotion-pct">{{ e.pct }}%</text>
          </view>
        </view>
      </view>

      <!-- Recurring Symbols -->
      <view class="section" v-if="health.recurring_symbols?.length">
        <text class="section-title">Recurring Symbols</text>
        <view class="tag-cloud">
          <text v-for="s in health.recurring_symbols" :key="s.symbol" class="cloud-tag">{{ s.symbol }} ({{ s.count }})</text>
        </view>
      </view>

      <!-- Empty State -->
      <view class="empty" v-if="!health.total_dreams && !loading">
        <text class="empty-text">Record some dreams to see your health dashboard</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getHealthCurrent } from '../../api/dream'

const health = ref<any>({})
const loading = ref(false)

onShow(async () => {
  loading.value = true
  try {
    // user_id is now derived from the Bearer token by the backend
    health.value = await getHealthCurrent(30)
  } catch (err) {
    console.error(err)
  }
  loading.value = false
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); }
.header { padding: 100rpx 40rpx 30rpx; background: linear-gradient(180deg, var(--dream-bg-card-hover) 0%, var(--dream-bg-primary) 100%); display: flex; justify-content: space-between; align-items: center; }
.header-title { font-size: 44rpx; font-weight: 700; color: var(--dream-text-primary); }
.score-circle { width: 120rpx; height: 120rpx; border-radius: 50%; border: 4rpx solid var(--dream-primary-500); display: flex; flex-direction: column; align-items: center; justify-content: center; }
.score-number { font-size: 36rpx; font-weight: 800; color: var(--dream-primary-500); }
.score-label { font-size: 18rpx; color: var(--dream-text-muted); }
.content { padding: 20rpx 30rpx; height: calc(100vh - 250rpx); }
.stats-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.stat-card { flex: 1; background: var(--dream-bg-card); border-radius: 16rpx; padding: 24rpx; text-align: center; }
.stat-value { font-size: 36rpx; font-weight: 700; color: var(--dream-text-primary); display: block; }
.stat-label { font-size: 22rpx; color: var(--dream-text-muted); display: block; margin-top: 8rpx; }
.section { margin-bottom: 24rpx; }
.section-title { font-size: 28rpx; font-weight: 600; color: var(--dream-primary-500); display: block; margin-bottom: 16rpx; }
.anomaly-card { background: #1a0a2e; border-radius: 12rpx; padding: 16rpx 20rpx; margin-bottom: 10rpx; display: flex; gap: 12rpx; align-items: center; }
.anomaly-severity { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; font-weight: 600; }
.severity-high { background: rgba(239,68,68,0.3); color: #ef4444; }
.severity-medium { background: rgba(234,179,8,0.3); color: #eab308; }
.anomaly-desc { font-size: 26rpx; color: var(--dream-text-primary); flex: 1; }
.emotion-bars { display: flex; flex-direction: column; gap: 12rpx; }
.emotion-bar-row { display: flex; align-items: center; gap: 12rpx; }
.emotion-name { width: 120rpx; font-size: 24rpx; color: var(--dream-text-primary); }
.emotion-bar-bg { flex: 1; height: 16rpx; background: var(--dream-bg-input); border-radius: 8rpx; overflow: hidden; }
.emotion-bar-fill { height: 100%; background: linear-gradient(90deg, var(--dream-primary-600), var(--dream-primary-800)); border-radius: 8rpx; }
.emotion-pct { width: 60rpx; font-size: 22rpx; color: var(--dream-text-muted); text-align: right; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 10rpx; }
.cloud-tag { background: var(--dream-bg-input); color: var(--dream-primary-200); font-size: 22rpx; padding: 8rpx 16rpx; border-radius: 10rpx; }
.empty { padding: 80rpx; text-align: center; }
.empty-text { color: var(--dream-text-muted); font-size: 28rpx; }
</style>
