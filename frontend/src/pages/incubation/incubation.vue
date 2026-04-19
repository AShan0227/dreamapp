<template>
  <view class="page">
    <view class="header">
      <text class="header-title">Active Dreaming</text>
      <text class="header-subtitle">Set an intention before sleep</text>
    </view>

    <scroll-view class="content" scroll-y>
      <!-- Input -->
      <view class="intention-section" v-if="!session">
        <text class="section-label">What do you want to dream about tonight?</text>
        <textarea
          class="intention-input"
          v-model="intention"
          placeholder="I want to dream about..."
          :auto-height="true"
          :maxlength="500"
        />
        <view class="btn btn-primary" @tap="onStart" :class="{ disabled: !intention.trim() || loading }">
          <text class="btn-text">Generate Pre-Sleep Guide</text>
        </view>
      </view>

      <!-- Recommendations -->
      <view v-if="session" class="recommendations">
        <text class="reco-title">Your Pre-Sleep Guide</text>
        <text class="reco-intention">"{{ session.intention }}"</text>

        <!-- Visual -->
        <view class="reco-card" v-if="session.recommendations?.images">
          <text class="reco-card-title">Visualize</text>
          <text v-for="(img, i) in session.recommendations.images" :key="i" class="reco-item">{{ img }}</text>
        </view>

        <!-- Sound -->
        <view class="reco-card" v-if="session.recommendations?.sounds">
          <text class="reco-card-title">Soundscape</text>
          <text class="reco-item">{{ session.recommendations.sounds }}</text>
        </view>

        <!-- Meditation -->
        <view class="reco-card" v-if="session.recommendations?.meditation">
          <text class="reco-card-title">Meditation Seed</text>
          <text class="reco-item meditation">{{ session.recommendations.meditation }}</text>
        </view>

        <!-- Scent -->
        <view class="reco-card" v-if="session.recommendations?.scent">
          <text class="reco-card-title">Aromatherapy</text>
          <text class="reco-item">{{ session.recommendations.scent }}</text>
        </view>

        <view class="action-row">
          <view class="btn btn-secondary" @tap="onReset">
            <text class="btn-text">New Intention</text>
          </view>
        </view>
      </view>

      <!-- Past sessions -->
      <view class="section" v-if="pastSessions.length > 0">
        <text class="section-label">Past Sessions</text>
        <view v-for="s in pastSessions" :key="s.session_id" class="past-card">
          <text class="past-intention">"{{ s.intention }}"</text>
          <view class="past-row">
            <text class="past-status">{{ s.status }}</text>
            <text class="past-match" v-if="s.outcome_match != null">Match: {{ (s.outcome_match * 100).toFixed(0) }}%</text>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { startIncubation, listIncubations } from '../../api/dream'

const intention = ref('')
const session = ref<any>(null)
const pastSessions = ref<any[]>([])
const loading = ref(false)

onShow(async () => {
  try {
    pastSessions.value = await listIncubations('default')
  } catch (err) { console.error(err) }
})

async function onStart() {
  if (!intention.value.trim() || loading.value) return
  loading.value = true
  uni.showLoading({ title: 'Generating guide...' })
  try {
    session.value = await startIncubation(intention.value, 'default')
    uni.hideLoading()
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Failed', icon: 'none' })
  }
  loading.value = false
}

function onReset() {
  session.value = null
  intention.value = ''
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); }
.header { padding: 100rpx 40rpx 20rpx; background: linear-gradient(180deg, var(--dream-bg-card-hover) 0%, var(--dream-bg-primary) 100%); }
.header-title { font-size: 44rpx; font-weight: 700; color: var(--dream-text-primary); display: block; }
.header-subtitle { font-size: 26rpx; color: var(--dream-text-muted); margin-top: 8rpx; display: block; }
.content { padding: 20rpx 30rpx; height: calc(100vh - 250rpx); }
.intention-section { margin-bottom: 30rpx; }
.section-label { font-size: 28rpx; color: var(--dream-text-primary); display: block; margin-bottom: 16rpx; }
.intention-input { width: 100%; background: var(--dream-bg-input); border-radius: 16rpx; padding: 24rpx; color: var(--dream-text-primary); font-size: 30rpx; min-height: 120rpx; margin-bottom: 20rpx; }
.btn { padding: 28rpx; border-radius: 16rpx; text-align: center; }
.btn-primary { background: linear-gradient(135deg, var(--dream-primary-600), var(--dream-primary-800)); }
.btn-secondary { background: var(--dream-bg-input); border: 1px solid #3b3b5c; }
.btn-text { color: var(--dream-text-primary); font-size: 28rpx; font-weight: 600; }
.disabled { opacity: 0.4; }
.recommendations { margin-bottom: 30rpx; }
.reco-title { font-size: 32rpx; font-weight: 700; color: var(--dream-primary-500); display: block; margin-bottom: 12rpx; }
.reco-intention { font-size: 28rpx; color: var(--dream-primary-200); font-style: italic; display: block; margin-bottom: 24rpx; }
.reco-card { background: var(--dream-bg-card); border-radius: 16rpx; padding: 24rpx; margin-bottom: 16rpx; }
.reco-card-title { font-size: 26rpx; font-weight: 600; color: var(--dream-primary-500); display: block; margin-bottom: 12rpx; }
.reco-item { font-size: 26rpx; color: var(--dream-text-primary); line-height: 1.6; display: block; margin-bottom: 8rpx; }
.meditation { font-style: italic; color: var(--dream-primary-200); }
.action-row { display: flex; gap: 16rpx; margin-top: 20rpx; }
.section { margin-top: 30rpx; }
.past-card { background: var(--dream-bg-card); border-radius: 12rpx; padding: 16rpx 20rpx; margin-bottom: 10rpx; }
.past-intention { font-size: 26rpx; color: var(--dream-text-primary); display: block; }
.past-row { display: flex; justify-content: space-between; margin-top: 8rpx; }
.past-status { font-size: 22rpx; color: var(--dream-text-muted); }
.past-match { font-size: 22rpx; color: var(--dream-primary-500); }
</style>
