<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">{{ p?.handle ? '@' + p.handle : (p?.nickname || 'Profile') }}</text>
      <view class="back" />
    </view>

    <view v-if="p" class="profile-card">
      <view class="avatar">{{ (p.nickname || 'D').charAt(0) }}</view>
      <view class="ident">
        <view class="name-row">
          <text class="nickname">{{ p.nickname }}</text>
          <text v-if="p.is_verified" class="verified">✓</text>
        </view>
        <text v-if="p.handle" class="handle">@{{ p.handle }}</text>
        <text v-if="p.bio" class="bio">{{ p.bio }}</text>
      </view>

      <view class="stats">
        <view class="stat">
          <text class="stat-num">{{ p.public_dream_count || 0 }}</text>
          <text class="stat-label">dreams</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ p.follower_count || 0 }}</text>
          <text class="stat-label">followers</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ p.following_count || 0 }}</text>
          <text class="stat-label">following</text>
        </view>
      </view>

      <view v-if="!p.is_self" class="action-row">
        <view class="btn btn-primary flex1" @tap="onToggleFollow">
          <text class="btn-text">{{ p.is_following ? 'Following' : 'Follow' }}</text>
        </view>
        <view class="btn btn-secondary flex1" @tap="onMessage">
          <text class="btn-text">Message</text>
        </view>
        <view class="btn btn-icon" @tap="onMore"><text>···</text></view>
      </view>
      <view v-else class="action-row">
        <view class="btn btn-secondary flex1" @tap="onEdit">
          <text class="btn-text">Edit profile</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getProfile, followUser, unfollowUser, muteUser, blockUser } from '@/api/dream'

const p = ref<any>(null)
let targetId = ''

onLoad(async (q: any) => {
  targetId = q?.id || q?.handle || ''
  if (targetId) await load()
})

async function load() {
  try { p.value = await getProfile(targetId) } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Not found', icon: 'none' })
  }
}

async function onToggleFollow() {
  if (!p.value) return
  try {
    if (p.value.is_following) await unfollowUser(p.value.id)
    else await followUser(p.value.id)
    await load()
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

function onMessage() {
  if (!p.value) return
  uni.navigateTo({ url: `/pages/dm/dm?to=${p.value.id}` })
}

function onMore() {
  uni.showActionSheet({
    itemList: ['Mute', 'Block', 'Report'],
    success: async (res) => {
      if (!p.value) return
      try {
        if (res.tapIndex === 0) await muteUser(p.value.id)
        else if (res.tapIndex === 1) await blockUser(p.value.id)
        else if (res.tapIndex === 2) uni.showToast({ title: 'Report opened', icon: 'none' })
        uni.showToast({ title: 'Done', icon: 'none' })
      } catch (e: any) {
        uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
      }
    },
  })
}

function onEdit() { uni.navigateTo({ url: '/pages/profile/profile' }) }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-3); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }

.profile-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); display: flex; flex-direction: column; gap: var(--dream-space-3); align-items: stretch; }
.avatar { width: 120rpx; height: 120rpx; border-radius: 50%; background: var(--dream-gradient-aurora); display: flex; align-items: center; justify-content: center; color: white; font-size: 48rpx; font-weight: 700; align-self: center; }
.ident { display: flex; flex-direction: column; gap: 6rpx; align-items: center; text-align: center; }
.name-row { display: flex; gap: 8rpx; align-items: center; }
.nickname { color: var(--dream-text-primary); font-size: var(--dream-text-lg); font-weight: 600; }
.verified { color: #3b82f6; font-size: var(--dream-text-base); background: rgba(59,130,246,0.15); border-radius: 50%; width: 36rpx; height: 36rpx; display: flex; align-items: center; justify-content: center; }
.handle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); font-family: var(--dream-font-mono); }
.bio { color: var(--dream-text-secondary); font-size: var(--dream-text-base); line-height: 1.5; max-width: 100%; padding: 8rpx 0; }

.stats { display: flex; justify-content: space-around; padding: var(--dream-space-3) 0; border-top: 1rpx solid var(--dream-border-subtle); border-bottom: 1rpx solid var(--dream-border-subtle); }
.stat { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.stat-num { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 700; }
.stat-label { color: var(--dream-text-muted); font-size: var(--dream-text-xs); }

.action-row { display: flex; gap: var(--dream-space-2); }
.flex1 { flex: 1; }
.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-2) var(--dream-space-3); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-secondary { background: var(--dream-bg-card); border: 1rpx solid var(--dream-border-default); }
.btn-icon { background: var(--dream-bg-card); border: 1rpx solid var(--dream-border-default); width: 60rpx; }
.btn-text { color: white; font-size: var(--dream-text-sm); font-weight: 500; }
</style>
