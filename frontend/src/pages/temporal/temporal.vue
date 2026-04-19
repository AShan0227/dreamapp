<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Recurring Patterns</text>
      <view class="action-btn" @tap="onRefresh">
        <text class="action-text">{{ refreshing ? '…' : '↻' }}</text>
      </view>
    </view>

    <text class="subtitle">Cross-temporal correlation across your dreams.</text>

    <view class="kind-tabs">
      <view
        v-for="k in kinds"
        :key="k.id"
        class="kind-tab"
        :class="{ 'kind-tab-active': activeKind === k.id }"
        @tap="setKind(k.id)"
      >
        <text>{{ k.label }}</text>
      </view>
    </view>

    <scroll-view class="list" scroll-y>
      <view v-if="loading && patterns.length === 0">
        <view v-for="i in 3" :key="i" class="skel" />
      </view>

      <view v-else-if="patterns.length === 0" class="empty-state">
        <text class="empty-icon">&#x1F50D;</text>
        <text class="empty-title">No recurring patterns yet</text>
        <text class="empty-hint">Record at least 2 dreams sharing a symbol/character to start seeing patterns.</text>
      </view>

      <view v-for="p in patterns" :key="p.id" class="pattern-card">
        <view class="pattern-head">
          <view class="pattern-tag" :class="'pk-' + p.kind">{{ p.kind }}</view>
          <text class="pattern-count">{{ p.occurrence_count }}× over {{ p.spans_days }}d</text>
        </view>
        <text class="pattern-name">{{ p.canonical_name }}</text>
        <view class="pattern-dreams">
          <view
            v-for="(did, idx) in p.dream_ids.slice(0, 5)"
            :key="did"
            class="dream-pill"
            @tap="goDream(did)"
          >
            <text>#{{ idx + 1 }}</text>
          </view>
          <text v-if="p.dream_ids.length > 5" class="dream-more">+{{ p.dream_ids.length - 5 }}</text>
        </view>
        <text class="pattern-time">First: {{ formatTime(p.first_seen_at) }} · Last: {{ formatTime(p.last_seen_at) }}</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTemporalPatterns, refreshTemporalPatterns } from '@/api/dream'

const patterns = ref<any[]>([])
const loading = ref(false)
const refreshing = ref(false)
const activeKind = ref('')
const kinds = [
  { id: '', label: 'All' },
  { id: 'symbol', label: 'Symbols' },
  { id: 'character', label: 'Characters' },
  { id: 'theme', label: 'Themes' },
  { id: 'scene', label: 'Scenes' },
  { id: 'narrative', label: 'Narratives' },
  { id: 'emotion', label: 'Emotions' },
]

onMounted(async () => { await load() })

async function load() {
  loading.value = true
  try { patterns.value = await listTemporalPatterns(activeKind.value || undefined) || [] }
  catch {}
  loading.value = false
}

async function setKind(k: string) { activeKind.value = k; await load() }

async function onRefresh() {
  refreshing.value = true
  try {
    await refreshTemporalPatterns()
    await load()
    uni.showToast({ title: 'Patterns recomputed', icon: 'none' })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Refresh failed', icon: 'none' })
  }
  refreshing.value = false
}

function goDream(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function formatTime(s: string | null) {
  if (!s) return '—'
  const dt = new Date(s)
  return `${dt.getMonth()+1}/${dt.getDate()}`
}
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.action-btn { width: 48rpx; text-align: center; font-size: var(--dream-text-lg); color: var(--dream-text-accent); }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); }

.kind-tabs { display: flex; gap: var(--dream-space-1); flex-wrap: wrap; margin-bottom: var(--dream-space-3); }
.kind-tab { padding: 8rpx 18rpx; border-radius: var(--dream-radius-full); background: var(--dream-bg-input); color: var(--dream-text-muted); font-size: var(--dream-text-xs); }
.kind-tab-active { background: var(--dream-gradient-primary); color: white; }

.list { height: calc(100vh - 280rpx); }

.pattern-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.pattern-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--dream-space-2); }
.pattern-tag { font-size: 18rpx; font-weight: 600; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.pk-symbol { background: rgba(139,92,246,0.15); color: #c4b5fd; }
.pk-character { background: rgba(245,158,11,0.15); color: #fbbf24; }
.pk-theme { background: rgba(20,184,166,0.15); color: #5eead4; }
.pk-scene { background: rgba(59,130,246,0.15); color: #93c5fd; }
.pk-narrative { background: rgba(236,72,153,0.15); color: #f9a8d4; }
.pk-emotion { background: rgba(239,68,68,0.15); color: #f87171; }
.pattern-count { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
.pattern-name { font-size: var(--dream-text-md); color: var(--dream-text-primary); font-weight: 500; display: block; margin-bottom: var(--dream-space-2); }
.pattern-dreams { display: flex; gap: 6rpx; flex-wrap: wrap; margin-bottom: var(--dream-space-2); }
.dream-pill { background: var(--dream-bg-input); padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); font-size: 18rpx; color: var(--dream-text-accent); }
.dream-more { font-size: 18rpx; color: var(--dream-text-muted); align-self: center; }
.pattern-time { font-size: 18rpx; color: var(--dream-text-muted); display: block; }

.empty-state { padding: 100rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: var(--dream-space-2); }
.empty-icon { font-size: 80rpx; color: var(--dream-text-muted); }
.empty-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); }
.empty-hint { font-size: var(--dream-text-sm); color: var(--dream-text-muted); line-height: 1.5; }
.skel { height: 160rpx; background: rgba(255,255,255,0.04); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); }
</style>
