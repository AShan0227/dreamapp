<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Bookmarks</text>
      <view class="back" />
    </view>

    <view v-if="bookmarks.length === 0" class="empty">
      <text class="empty-icon">🔖</text>
      <text class="empty-title">No bookmarks yet</text>
      <text class="empty-hint">Save dreams from the plaza or your archive.</text>
    </view>

    <view v-for="b in bookmarks" :key="b.bookmark_id" class="card" @tap="goDream(b.dream_id)">
      <view v-if="b.video_url" class="video-wrap">
        <video :src="b.video_url" class="card-video" :controls="false" :autoplay="false" :muted="true" object-fit="cover" />
      </view>
      <view class="card-body">
        <text class="card-title">{{ b.title || 'Untitled' }}</text>
        <text class="card-folder">{{ b.folder }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listBookmarks } from '@/api/dream'

const bookmarks = ref<any[]>([])

onMounted(async () => {
  try { bookmarks.value = await listBookmarks() || [] } catch {}
})

function goDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-3); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }

.card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); overflow: hidden; }
.video-wrap { aspect-ratio: 16/9; background: black; }
.card-video { width: 100%; height: 100%; }
.card-body { padding: var(--dream-space-3); display: flex; justify-content: space-between; align-items: center; }
.card-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 500; }
.card-folder { color: var(--dream-text-muted); font-size: var(--dream-text-xs); padding: 2rpx 8rpx; background: var(--dream-bg-input); border-radius: var(--dream-radius-sm); }

.empty { padding: 100rpx 40rpx; text-align: center; }
.empty-icon { font-size: 80rpx; display: block; }
.empty-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); display: block; margin: 16rpx 0 8rpx; }
.empty-hint { color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
</style>
