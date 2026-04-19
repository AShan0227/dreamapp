<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">#{{ tag }}</text>
      <view class="action" @tap="onToggleFollow">
        <text class="action-text">{{ isFollowing ? 'Following' : 'Follow' }}</text>
      </view>
    </view>

    <view v-if="dreams.length === 0" class="empty">
      <text class="empty-icon">#️⃣</text>
      <text class="empty-title">No dreams under #{{ tag }} yet</text>
    </view>

    <view v-for="d in dreams" :key="d.dream_id" class="card" @tap="goDream(d.dream_id)">
      <view v-if="d.video_url" class="video-wrap">
        <video :src="d.video_url" class="card-video" :controls="false" :autoplay="false" :muted="true" object-fit="cover" />
      </view>
      <view class="card-body">
        <text class="card-title">{{ d.title || 'Untitled' }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { tagDreams, followHashtag, unfollowHashtag, myFollowedTags } from '@/api/dream'

const tag = ref('')
const dreams = ref<any[]>([])
const isFollowing = ref(false)

onLoad(async (q: any) => {
  tag.value = (q?.tag || '').toLowerCase().replace(/^#/, '')
  if (!tag.value) return
  await load()
  try { isFollowing.value = (await myFollowedTags() || []).includes(tag.value) } catch {}
})

async function load() {
  try { dreams.value = await tagDreams(tag.value, 50) || [] } catch {}
}

async function onToggleFollow() {
  try {
    if (isFollowing.value) await unfollowHashtag(tag.value); else await followHashtag(tag.value)
    isFollowing.value = !isFollowing.value
    uni.showToast({ title: isFollowing.value ? 'Following' : 'Unfollowed', icon: 'none' })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

function goDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-3); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.action { background: rgba(139,92,246,0.15); padding: 8rpx 18rpx; border-radius: 9999rpx; }
.action-text { color: var(--dream-text-accent); font-size: var(--dream-text-sm); font-weight: 500; }

.card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); overflow: hidden; }
.video-wrap { aspect-ratio: 16/9; background: black; }
.card-video { width: 100%; height: 100%; }
.card-body { padding: var(--dream-space-3); }
.card-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 500; }

.empty { padding: 100rpx 40rpx; text-align: center; }
.empty-icon { font-size: 80rpx; display: block; }
.empty-title { color: var(--dream-text-secondary); font-size: var(--dream-text-md); display: block; margin-top: 16rpx; }
</style>
