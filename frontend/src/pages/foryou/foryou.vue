<template>
  <view class="page dc-screen">
    <DreamAtmosphere variant="solaris" :star-count="40" />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">for you</text>
      <view class="back" />
    </view>

    <view class="hero">
      <text class="hero-eyebrow dc-eyebrow">curated tonight</text>
      <text class="hero-title dc-display">梦境精选</text>
      <text class="hero-sub dc-narrative">基于你的梦境气质,算法挑出今夜最相关的</text>
    </view>

    <view v-if="trending.length" class="trending-row">
      <text class="trending-label dc-eyebrow">trending</text>
      <scroll-view scroll-x class="trending-scroll">
        <view class="trending-list">
          <view v-for="t in trending" :key="t.tag" class="tag-pill" @tap="goTag(t.tag)">
            <text class="tag-name">#{{ t.tag }}</text>
            <text class="tag-count">{{ t.count }}</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <view v-if="dreams.length === 0" class="empty">
      <text class="empty-icon">✨</text>
      <text class="empty-title dc-display">No matches yet</text>
      <text class="empty-hint dc-narrative">Record a few more dreams to teach the feed your taste.</text>
    </view>

    <view v-for="d in dreams" :key="d.dream_id" class="card" @tap="goDream(d.dream_id)">
      <view v-if="d.video_url" class="video-wrap">
        <video :src="d.video_url" class="card-video" :controls="false" :autoplay="false" :muted="true" object-fit="cover" />
        <view class="card-grain dc-grain"></view>
        <view class="card-caption-gradient"></view>
        <view class="card-caption">
          <text class="card-title-overlay dc-display">{{ d.title || 'Untitled' }}</text>
          <text class="card-score-overlay">match · {{ d.score }}</text>
        </view>
      </view>
      <view v-else class="card-body">
        <text class="card-title dc-display">{{ d.title || 'Untitled' }}</text>
        <text class="card-score">match {{ d.score }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { forYouFeed, trendingTags } from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const dreams = ref<any[]>([])
const trending = ref<any[]>([])

onMounted(async () => {
  try { dreams.value = await forYouFeed(30) || [] } catch {}
  try { trending.value = await trendingTags(24, 12) || [] } catch {}
})

function goDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function goTag(tag: string) { uni.navigateTo({ url: `/pages/hashtag/hashtag?tag=${encodeURIComponent(tag)}` }) }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; padding: 32rpx; padding-top: calc(60rpx + env(safe-area-inset-top, 0)); position: relative; z-index: 1; }
.header, .hero, .trending-row, .empty, .card { position: relative; z-index: 2; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.back {
  width: 64rpx; height: 64rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: 36rpx; color: var(--dc-solaris-pearl);
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 50%;
}
.title { display: block; }

.hero {
  text-align: center;
  padding: 24rpx 0 40rpx;
  display: flex; flex-direction: column; align-items: center; gap: 8rpx;
}
.hero-eyebrow { display: block; }
.hero-title { font-size: 60rpx; line-height: 1.1; display: block; margin: 8rpx 0; }
.hero-sub { font-size: 24rpx; color: var(--dream-text-secondary); display: block; max-width: 520rpx; }

.trending-row { margin-bottom: 32rpx; }
.trending-label { display: block; margin-bottom: 14rpx; opacity: 0.85; }
.trending-scroll { white-space: nowrap; }
.trending-list { display: inline-flex; gap: 12rpx; padding: 4rpx 0; }
.tag-pill {
  display: inline-flex; align-items: center; gap: 8rpx;
  padding: 12rpx 20rpx;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.18) 0%, rgba(236, 72, 153, 0.1) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 9999rpx;
  flex-shrink: 0;
}
.tag-name {
  font-family: var(--dc-font-display);
  color: var(--dc-solaris-pearl);
  font-size: 24rpx;
  letter-spacing: 0.04em;
}
.tag-count {
  color: var(--dc-aurora-lavender);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.15em;
  opacity: 0.8;
}

.card {
  margin-bottom: 24rpx;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 16rpx 40rpx rgba(0, 0, 0, 0.4), 0 0 0 1rpx rgba(196, 181, 253, 0.1);
}
.video-wrap {
  position: relative;
  aspect-ratio: 16/9;
  background: var(--dc-grad-moonrise);
  overflow: hidden;
}
.card-video { width: 100%; height: 100%; }
.card-grain { position: absolute; inset: 0; z-index: 2; opacity: 0.06; mix-blend-mode: overlay; }
.card-caption-gradient {
  position: absolute; left: 0; right: 0; bottom: 0; height: 200rpx;
  background: linear-gradient(180deg, transparent 0%, rgba(3,2,16,0.9) 100%);
  z-index: 3; pointer-events: none;
}
.card-caption {
  position: absolute; left: 0; right: 0; bottom: 0;
  z-index: 4;
  padding: 20rpx 28rpx;
  display: flex; flex-direction: column; gap: 4rpx;
}
.card-title-overlay {
  font-size: 32rpx; line-height: 1.2;
  background: none; -webkit-background-clip: unset; background-clip: unset;
  color: var(--dc-solaris-pearl);
  text-shadow: 0 2rpx 12rpx rgba(0,0,0,0.6);
  display: block;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.card-score-overlay {
  font-family: var(--dc-font-caption);
  font-size: 18rpx; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  display: block; margin-top: 4rpx;
}
.card-body {
  padding: 24rpx 28rpx;
  display: flex; justify-content: space-between; align-items: center;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
}
.card-title { color: var(--dc-solaris-pearl); font-size: 30rpx; }
.card-score {
  color: var(--dc-aurora-lavender);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.empty { padding: 120rpx 40rpx; text-align: center; }
.empty-icon { font-size: 80rpx; display: block; opacity: 0.7; margin-bottom: 16rpx; }
.empty-title { font-size: 36rpx; display: block; margin-bottom: 12rpx; }
.empty-hint {
  color: var(--dream-text-muted);
  font-size: 24rpx;
  font-family: var(--dc-font-narrative);
  font-style: italic;
}
</style>
