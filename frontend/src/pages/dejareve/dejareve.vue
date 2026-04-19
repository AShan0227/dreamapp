<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Deja Reve</text>
      <view class="back" />
    </view>

    <text class="subtitle">"I think I dreamed about this." Search your dream archive by waking-life event.</text>

    <view class="search-card">
      <textarea
        class="search-input"
        v-model="query"
        :auto-height="true"
        placeholder="Describe what just happened — even one or two sentences."
        maxlength="2000"
      />
      <view class="btn btn-primary" @tap="onSearch" :class="{ 'btn-disabled': !query.trim() || searching }">
        <text class="btn-text">{{ searching ? 'Searching…' : 'Find matching dreams' }}</text>
      </view>
    </view>

    <text v-if="results.length" class="section-label">Most similar dreams</text>
    <view v-for="r in results" :key="r.dream_id" class="result-card">
      <view class="result-head">
        <text class="result-title" @tap="goDream(r.dream_id)">{{ r.title }}</text>
        <text class="result-sim" v-if="r.similarity != null">{{ (r.similarity * 100).toFixed(0) }}%</text>
      </view>
      <text class="result-meta">{{ formatTime(r.created_at) }}</text>
      <view class="result-tags" v-if="r.symbol_tags?.length || r.emotion_tags?.length">
        <text v-for="t in (r.emotion_tags || []).slice(0,2)" :key="t" class="tag tag-emotion">{{ t }}</text>
        <text v-for="t in (r.symbol_tags || []).slice(0,3)" :key="t" class="tag tag-symbol">{{ t }}</text>
      </view>
      <view class="confirm-btn" @tap="onConfirm(r)">
        <text>This is the one ✓</text>
      </view>
    </view>

    <text v-if="links.length" class="section-label">Confirmed crossings</text>
    <view v-for="l in links" :key="l.id" class="link-card">
      <text class="link-event">{{ l.waking_event }}</text>
      <text class="link-meta" @tap="goDream(l.dream_id)">→ Dream {{ l.dream_id.slice(0,8) }} · {{ formatTime(l.created_at) }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { dejaReveSearch, dejaReveConfirm, dejaReveList } from '@/api/dream'

const query = ref('')
const searching = ref(false)
const results = ref<any[]>([])
const links = ref<any[]>([])

onMounted(async () => { await loadLinks() })

async function loadLinks() {
  try { links.value = await dejaReveList() || [] } catch {}
}

async function onSearch() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    results.value = await dejaReveSearch(query.value) || []
    if (results.value.length === 0) {
      uni.showToast({ title: 'No matches yet — record more dreams to enrich the archive.', icon: 'none', duration: 3000 })
    }
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Search failed', icon: 'none' })
  }
  searching.value = false
}

async function onConfirm(r: any) {
  try {
    await dejaReveConfirm(r.dream_id, query.value, r.similarity)
    uni.showToast({ title: 'Crossing saved', icon: 'none' })
    await loadLinks()
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Save failed', icon: 'none' })
  }
}

function goDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function formatTime(s: string | null) { if (!s) return '—'; const dt = new Date(s); return `${dt.getMonth()+1}/${dt.getDate()} ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.search-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-4); }
.search-input { width: 100%; min-height: 160rpx; background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); margin-bottom: var(--dream-space-3); box-sizing: border-box; }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }
.btn-disabled { opacity: 0.4; pointer-events: none; }

.section-label { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin: var(--dream-space-3) 0 var(--dream-space-2); }

.result-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.result-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4rpx; }
.result-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); font-weight: 500; }
.result-sim { font-size: var(--dream-text-sm); color: var(--dream-primary-300); font-variant-numeric: tabular-nums; }
.result-meta { font-size: var(--dream-text-xs); color: var(--dream-text-muted); display: block; margin-bottom: var(--dream-space-2); }
.result-tags { display: flex; gap: 6rpx; flex-wrap: wrap; margin-bottom: var(--dream-space-2); }
.tag { font-size: 18rpx; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); }
.tag-emotion { background: rgba(245,158,11,0.15); color: #fbbf24; }
.tag-symbol { background: rgba(139,92,246,0.15); color: #c4b5fd; }
.confirm-btn { background: rgba(20,184,166,0.15); color: #5eead4; padding: 6rpx 14rpx; border-radius: var(--dream-radius-full); font-size: var(--dream-text-xs); align-self: flex-start; display: inline-block; }

.link-card { background: rgba(255,255,255,0.03); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); margin-bottom: var(--dream-space-2); }
.link-event { color: var(--dream-text-primary); font-size: var(--dream-text-sm); display: block; margin-bottom: 4rpx; }
.link-meta { color: var(--dream-text-accent); font-size: var(--dream-text-xs); display: block; }
</style>
