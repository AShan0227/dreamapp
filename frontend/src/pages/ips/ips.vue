<template>
  <view class="page">
    <view class="header">
      <text class="header-title">Dream Mythology</text>
      <text class="header-subtitle">Your recurring dream characters & worlds</text>
    </view>

    <scroll-view class="content" scroll-y>
      <view v-if="ips.length === 0 && !loading" class="empty">
        <text class="empty-icon">&#x2728;</text>
        <text class="empty-title">No recurring elements yet</text>
        <text class="empty-desc">Record more dreams to discover your personal mythology</text>
        <view class="btn btn-primary" @tap="onDetect">
          <text class="btn-text">Scan for Patterns</text>
        </view>
      </view>

      <view v-for="ip in ips" :key="ip.id" class="ip-card">
        <view class="ip-header">
          <text class="ip-type-badge">{{ ip.type }}</text>
          <text class="ip-count">{{ ip.appearances }}x</text>
        </view>
        <text class="ip-name">{{ ip.name }}</text>
        <text class="ip-mythology" v-if="ip.mythology">{{ ip.mythology }}</text>
        <view class="ip-dates" v-if="ip.first_seen">
          <text class="ip-date">First: {{ formatDate(ip.first_seen) }}</text>
          <text class="ip-date">Last: {{ formatDate(ip.last_seen) }}</text>
        </view>
      </view>

      <view v-if="ips.length > 0" class="detect-section">
        <view class="btn btn-secondary" @tap="onDetect">
          <text class="btn-text">Rescan for New Patterns</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listIPs, detectIPs } from '../../api/dream'

const ips = ref<any[]>([])
const loading = ref(false)

onShow(async () => {
  loading.value = true
  try {
    ips.value = await listIPs('default')
  } catch (err) { console.error(err) }
  loading.value = false
})

async function onDetect() {
  uni.showLoading({ title: 'Scanning dreams...' })
  try {
    await detectIPs('default')
    ips.value = await listIPs('default')
    uni.hideLoading()
    uni.showToast({ title: `Found ${ips.value.length} IPs`, icon: 'success' })
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Scan failed', icon: 'none' })
  }
}

function formatDate(d: string) {
  return d ? new Date(d).toLocaleDateString() : ''
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); }
.header { padding: 100rpx 40rpx 20rpx; background: linear-gradient(180deg, var(--dream-bg-card-hover) 0%, var(--dream-bg-primary) 100%); }
.header-title { font-size: 44rpx; font-weight: 700; color: var(--dream-text-primary); display: block; }
.header-subtitle { font-size: 26rpx; color: var(--dream-text-muted); margin-top: 8rpx; display: block; }
.content { padding: 20rpx 30rpx; height: calc(100vh - 250rpx); }
.empty { display: flex; flex-direction: column; align-items: center; padding: 80rpx 40rpx; gap: 16rpx; }
.empty-icon { font-size: 100rpx; }
.empty-title { font-size: 34rpx; color: var(--dream-text-primary); font-weight: 600; }
.empty-desc { font-size: 26rpx; color: var(--dream-text-muted); text-align: center; margin-bottom: 20rpx; }
.btn { padding: 24rpx 40rpx; border-radius: 16rpx; text-align: center; }
.btn-primary { background: linear-gradient(135deg, var(--dream-primary-600), var(--dream-primary-800)); }
.btn-secondary { background: var(--dream-bg-input); border: 1px solid #3b3b5c; }
.btn-text { color: var(--dream-text-primary); font-size: 28rpx; font-weight: 600; }
.ip-card { background: var(--dream-bg-card); border-radius: 20rpx; padding: 24rpx; margin-bottom: 20rpx; border-left: 4rpx solid var(--dream-primary-500); }
.ip-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.ip-type-badge { background: var(--dream-primary-900); color: var(--dream-primary-200); font-size: 20rpx; padding: 4rpx 14rpx; border-radius: 8rpx; text-transform: uppercase; }
.ip-count { font-size: 24rpx; color: var(--dream-primary-500); font-weight: 700; }
.ip-name { font-size: 32rpx; color: var(--dream-text-primary); font-weight: 600; display: block; margin-bottom: 12rpx; }
.ip-mythology { font-size: 26rpx; color: var(--dream-text-primary); line-height: 1.6; display: block; margin-bottom: 12rpx; font-style: italic; }
.ip-dates { display: flex; gap: 20rpx; }
.ip-date { font-size: 22rpx; color: var(--dream-text-muted); }
.detect-section { padding: 20rpx 0; }
</style>
