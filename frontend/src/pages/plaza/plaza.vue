<template>
  <view class="page dc-screen">
    <DreamAtmosphere variant="solaris" :star-count="50" />

    <view class="page-header">
      <text class="page-eyebrow dc-eyebrow">other dreamers</text>
      <text class="page-title dc-display">The Plaza</text>
      <text class="page-subtitle dc-narrative">a screening room of strangers' dreams</text>
    </view>

    <!-- Search bar — toggles between dream search and knowledge search -->
    <view class="search-section">
      <view class="search-bar">
        <input
          class="search-input"
          v-model="searchQuery"
          :placeholder="searchMode === 'dreams' ? '搜索他人的梦…' : '搜索梦境知识库 (符号、原型、TCM…)'"
          @confirm="runSearch"
        />
        <view class="search-btn" @tap="runSearch">
          <text class="search-btn-text">Go</text>
        </view>
      </view>
      <view class="mode-tabs">
        <text
          class="mode-tab"
          :class="{ active: searchMode === 'dreams' }"
          @tap="switchMode('dreams')"
        >Dreams</text>
        <text
          class="mode-tab"
          :class="{ active: searchMode === 'knowledge' }"
          @tap="switchMode('knowledge')"
        >Knowledge</text>
      </view>
    </view>

    <!-- Knowledge search results -->
    <view class="knowledge-results" v-if="searchMode === 'knowledge' && knowledgeResults.length">
      <view v-for="k in knowledgeResults" :key="k.name + k.source" class="knowledge-card glass-card">
        <view class="kcard-head">
          <text class="kcard-name">{{ k.name }}</text>
          <text class="kcard-tier" :class="'tier-' + (k.tier || 'L1')">{{ k.tier || 'L1' }}</text>
        </view>
        <text class="kcard-source">{{ k.source }}</text>
        <text class="kcard-content">{{ k.content }}</text>
        <view class="kcard-meta">
          <text class="kcard-stat">conf {{ (k.confidence * 100).toFixed(0) }}%</text>
          <text class="kcard-stat">used {{ k.use_count || 0 }}×</text>
        </view>
      </view>
    </view>

    <!-- Trending (hide during knowledge search) -->
    <view class="trending-section" v-if="searchMode === 'dreams' && trending.top_symbols?.length && !searchQuery">
      <text class="section-title-dream dc-eyebrow">tonight's trending</text>
      <scroll-view class="trend-scroll" scroll-x>
        <view class="trend-list">
          <view v-for="s in trending.top_symbols" :key="s.name" class="trend-chip" @tap="toggleFilter(s.name)">
            <text class="trend-name">{{ s.name }}</text>
            <text class="trend-count">{{ s.count }}</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- Feed -->
    <scroll-view class="feed" scroll-y @scrolltolower="loadMore" v-if="searchMode === 'dreams'">
      <view v-for="dream in dreams" :key="dream.id" class="dream-card" @tap="goTo(dream.id)">
        <view class="card-visual">
          <video v-if="dream.video_url" :src="dream.video_url" class="card-video" :controls="false" :autoplay="false" :muted="true" object-fit="cover" />
          <view v-else class="card-gradient" :class="getGradient(dream)"></view>
          <view class="card-grain dc-grain"></view>
          <view class="share-btn" @tap.stop="onShare(dream)"><text class="share-icon">&#x2197;</text></view>
          <view class="card-caption-gradient"></view>
          <view class="card-caption">
            <text class="card-title dc-display">{{ dream.title || 'Untitled' }}</text>
            <view class="card-meta">
              <text class="card-date">{{ formatDate(dream.created_at) }}</text>
              <text class="card-aesthetic">· {{ getAesthetic(dream) }}</text>
            </view>
          </view>
        </view>
        <view class="card-chips" v-if="dream.emotion_tags?.length">
          <text v-for="t in (dream.emotion_tags || []).slice(0, 3)" :key="t" class="chip-dream chip-emotion">{{ t }}</text>
        </view>
      </view>

      <view class="empty-dream" v-if="!loading && dreams.length === 0">
        <text class="empty-icon-dream">&#x1F30C;</text>
        <text class="empty-title-text dc-display">No public dreams yet</text>
        <text class="empty-desc-text dc-narrative">Be the first to project yours.</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { browsePlaza, getTrending, searchDreams, searchKnowledge } from '../../api/dream'
import DreamAtmosphere from '../../components/DreamAtmosphere.vue'
import { gradientClassForDream, variantForDream, aestheticLabel } from '../../utils/dream-aesthetic'

function getGradient(d: any) { return gradientClassForDream(d) }
function getAesthetic(d: any) { return aestheticLabel(variantForDream(d)) }

const dreams = ref<any[]>([])
const trending = ref<any>({})
const loading = ref(false)
const searchQuery = ref('')
const searchMode = ref<'dreams' | 'knowledge'>('dreams')
const knowledgeResults = ref<any[]>([])
let page = 0

onMounted(async () => {
  await Promise.all([loadDreams(), loadTrending()])
})

async function loadDreams() {
  loading.value = true
  try { const r = await browsePlaza(page * 20, 20); if (page === 0) dreams.value = r; else dreams.value.push(...r) }
  catch (e) { console.error(e) }
  loading.value = false
}

async function loadTrending() {
  try { trending.value = await getTrending() } catch {}
}

function loadMore() { page++; loadDreams() }
function toggleFilter(s: string) { page = 0; searchQuery.value = s; runSearch() }
function goTo(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }

function switchMode(mode: 'dreams' | 'knowledge') {
  searchMode.value = mode
  if (searchQuery.value) runSearch()
}

async function runSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    if (searchMode.value === 'dreams') { page = 0; await loadDreams() }
    else knowledgeResults.value = []
    return
  }
  loading.value = true
  try {
    if (searchMode.value === 'dreams') {
      const r = await searchDreams(q, 20)
      dreams.value = r || []
    } else {
      const r = await searchKnowledge(q, undefined, 10)
      knowledgeResults.value = Array.isArray(r) ? r : []
    }
  } catch (e) { console.error(e) }
  loading.value = false
}

function formatDate(d: string) {
  const hrs = (Date.now() - new Date(d).getTime()) / 3600000
  if (hrs < 1) return 'Now'; if (hrs < 24) return `${Math.floor(hrs)}h`; if (hrs < 48) return 'Yesterday'
  return `${new Date(d).getMonth()+1}/${new Date(d).getDate()}`
}

function onShare(dream: any) {
  uni.setClipboardData({ data: `Dream: ${dream.title}`, success: () => uni.showToast({ title: 'Copied!', icon: 'success' }) })
}
</script>

<style scoped>
.page { min-height: 100vh; padding-bottom: 120rpx; position: relative; z-index: 1; }
.page-header, .search-section, .trending-section, .feed, .knowledge-results { position: relative; z-index: 2; }
.page-header { padding: 80rpx 32rpx 24rpx; display: flex; flex-direction: column; gap: 6rpx; }
.page-eyebrow { display: block; }
.page-title { font-size: 56rpx; line-height: 1.1; display: block; margin-top: 4rpx; }
.page-subtitle { font-size: 26rpx; color: var(--dream-text-secondary); display: block; margin-top: 6rpx; }

/* ===== Search + tabs ============================================== */
.search-section { padding: 16rpx 32rpx 8rpx; }
.search-bar {
  display: flex;
  align-items: center;
  padding: 8rpx 8rpx 8rpx 24rpx;
  gap: 12rpx;
  background: rgba(20, 10, 54, 0.55);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  border-radius: 9999rpx;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.search-input {
  flex: 1;
  color: var(--dc-solaris-pearl);
  font-size: 26rpx;
  padding: 16rpx 8rpx;
  background: transparent;
}
.search-btn {
  padding: 14rpx 28rpx;
  background: var(--dc-grad-aurora);
  border-radius: 9999rpx;
  box-shadow: 0 0 16rpx rgba(139, 92, 246, 0.35);
}
.search-btn-text { color: white; font-family: var(--dc-font-display); font-size: 24rpx; letter-spacing: 0.1em; }
.mode-tabs { display: flex; gap: 12rpx; margin-top: 16rpx; padding-left: 4rpx; }
.mode-tab {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  padding: 8rpx 20rpx;
  border-radius: 9999rpx;
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.08);
}
.mode-tab.active {
  color: var(--dc-solaris-pearl);
  background: rgba(139, 92, 246, 0.2);
  border-color: rgba(196, 181, 253, 0.4);
}

/* ===== Trending ==================================================== */
.trending-section { padding: 24rpx 32rpx 8rpx; }
.section-title-dream { display: block; margin-bottom: 16rpx; opacity: 0.85; }
.trend-scroll { white-space: nowrap; }
.trend-list { display: inline-flex; gap: 12rpx; padding: 4rpx 0 12rpx; }
.trend-chip {
  display: inline-flex;
  align-items: center;
  gap: 8rpx;
  padding: 12rpx 20rpx;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.18) 0%, rgba(236, 72, 153, 0.1) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 9999rpx;
  backdrop-filter: blur(10rpx);
  -webkit-backdrop-filter: blur(10rpx);
}
.trend-name {
  font-family: var(--dc-font-display);
  font-size: 26rpx;
  color: var(--dc-solaris-pearl);
  letter-spacing: 0.04em;
}
.trend-count {
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  color: var(--dc-aurora-lavender);
  letter-spacing: 0.15em;
  opacity: 0.8;
}

/* ===== Feed (film-still cards) ===================================== */
.feed { padding: 8rpx 32rpx; height: calc(100vh - 460rpx); }
.dream-card {
  position: relative;
  margin-bottom: 32rpx;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 16rpx 40rpx rgba(0, 0, 0, 0.45), 0 0 0 1rpx rgba(196, 181, 253, 0.08);
  transition: transform 250ms ease;
}
.dream-card:active { transform: translateY(2rpx); }
.card-visual { width: 100%; height: 460rpx; position: relative; overflow: hidden; }
.card-video { width: 100%; height: 100%; }
.card-gradient {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.card-grain { position: absolute; inset: 0; z-index: 2; opacity: 0.06; mix-blend-mode: overlay; }
.share-btn {
  position: absolute;
  top: 24rpx; right: 24rpx;
  z-index: 5;
  width: 64rpx; height: 64rpx;
  background: rgba(3, 2, 16, 0.55);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 9999rpx;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
}
.share-icon { color: var(--dc-solaris-pearl); font-size: 28rpx; }

.card-caption-gradient {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 220rpx;
  background: linear-gradient(180deg, transparent 0%, rgba(3, 2, 16, 0.85) 70%, rgba(3, 2, 16, 0.95) 100%);
  z-index: 3;
  pointer-events: none;
}
.card-caption {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  z-index: 4;
  padding: 24rpx 32rpx;
  display: flex; flex-direction: column; gap: 4rpx;
}
.card-title {
  font-size: 36rpx; line-height: 1.2; font-weight: 500;
  background: none; -webkit-background-clip: unset; background-clip: unset;
  color: var(--dc-solaris-pearl);
  text-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.7);
  display: block;
  max-width: 520rpx;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.card-meta { display: flex; align-items: center; gap: 8rpx; margin-top: 6rpx; }
.card-date, .card-aesthetic {
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(248, 244, 255, 0.6);
}
.card-aesthetic { color: rgba(196, 181, 253, 0.8); }

.card-chips {
  display: flex; gap: 10rpx; flex-wrap: wrap;
  padding: 16rpx 24rpx 20rpx;
  background: rgba(10, 8, 32, 0.55);
}
.chip-dream {
  font-size: 22rpx; letter-spacing: 0.05em;
  padding: 6rpx 14rpx; border-radius: 9999rpx;
  color: rgba(248, 244, 255, 0.8);
  background: rgba(139, 92, 246, 0.1);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
}
.chip-emotion {
  background: rgba(236, 72, 153, 0.08);
  border-color: rgba(236, 72, 153, 0.25);
  color: #fbcfe8;
}

/* Empty state */
.empty-dream {
  display: flex; flex-direction: column; align-items: center;
  padding: 100rpx 40rpx; text-align: center;
}
.empty-icon-dream { font-size: 96rpx; opacity: 0.6; margin-bottom: 24rpx; }
.empty-title-text { font-size: 36rpx; color: var(--dc-solaris-pearl); display: block; margin-bottom: 12rpx; }
.empty-desc-text { font-size: 26rpx; color: var(--dream-text-muted); font-style: italic; display: block; }

/* Knowledge cards */
.knowledge-results { padding: var(--dream-space-3) var(--dream-space-5); display: flex; flex-direction: column; gap: var(--dream-space-3); }
.knowledge-card { padding: var(--dream-space-4); }
.kcard-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--dream-space-2); }
.kcard-name { font-size: var(--dream-text-md); font-weight: 600; color: var(--dream-text-primary); flex: 1; }
.kcard-tier { font-size: var(--dream-text-xs); padding: 2rpx 12rpx; border-radius: var(--dream-radius-full); font-weight: 600; }
.tier-L0 { background: rgba(100,150,255,0.25); color: #9bb8ff; }
.tier-L1 { background: rgba(139,92,246,0.25); color: #c4b3ff; }
.tier-L2 { background: rgba(255,180,100,0.2); color: #ffc89b; }
.kcard-source { font-size: var(--dream-text-xs); color: var(--dream-text-muted); text-transform: uppercase; letter-spacing: 1rpx; display: block; margin-bottom: var(--dream-space-2); }
.kcard-content { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); line-height: 1.6; display: block; }
.kcard-meta { display: flex; gap: var(--dream-space-3); margin-top: var(--dream-space-3); }
.kcard-stat { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
</style>
