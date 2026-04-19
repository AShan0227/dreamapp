<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Agent Store</text>
      <view class="back" />
    </view>

    <text class="subtitle">Discover and install dream agents created by other users.</text>

    <view class="tab-row">
      <view v-for="t in TABS" :key="t.id" :class="['tab', activeTab === t.id && 'tab-active']" @tap="setTab(t.id)">
        <text>{{ t.label }}</text>
      </view>
    </view>

    <view v-if="loading">
      <view v-for="i in 3" :key="i" class="skel" />
    </view>

    <view v-else-if="rows.length === 0" class="empty-state">
      <text class="empty-icon">&#x1F916;</text>
      <text class="empty-title">No agents yet</text>
      <text class="empty-hint">Build the first one in Agents tab.</text>
    </view>

    <view v-for="a in rows" :key="a.id" class="agent-card">
      <view class="agent-head">
        <text class="agent-name">{{ a.name }}</text>
        <text class="agent-price" v-if="a.price">¥{{ a.price }}</text>
        <text class="agent-price free" v-else>FREE</text>
      </view>
      <text class="agent-desc">{{ a.description }}</text>
      <view class="agent-meta">
        <text class="meta-text">{{ a.installs || 0 }} installs</text>
        <text class="meta-text" v-if="a.rating">★ {{ a.rating.toFixed(1) }}</text>
      </view>
      <view class="btn btn-primary" @tap="onInstall(a)">
        <text class="btn-text">Install</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { browseStore, installAgent } from '@/api/dream'

const TABS = [
  { id: 'popular', label: 'Popular' },
  { id: 'rating', label: 'Top rated' },
  { id: 'new', label: 'New' },
]
const activeTab = ref('popular')
const rows = ref<any[]>([])
const loading = ref(false)

onMounted(async () => { await load() })

async function setTab(t: string) { activeTab.value = t; await load() }

async function load() {
  loading.value = true
  try { rows.value = await browseStore() || [] } catch {}
  loading.value = false
}

async function onInstall(a: any) {
  try {
    await installAgent(a.id)
    uni.showToast({ title: 'Installed', icon: 'none' })
    await load()
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Install failed', icon: 'none' })
  }
}

function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.tab-row { display: flex; gap: var(--dream-space-2); margin-bottom: var(--dream-space-3); }
.tab { padding: 8rpx 16rpx; border-radius: var(--dream-radius-full); background: var(--dream-bg-input); color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
.tab-active { background: var(--dream-gradient-primary); color: white; }

.agent-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.agent-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--dream-space-2); }
.agent-name { font-size: var(--dream-text-md); color: var(--dream-text-primary); font-weight: 500; flex: 1; }
.agent-price { font-size: var(--dream-text-sm); color: var(--dream-warning); font-weight: 600; }
.agent-price.free { color: var(--dream-success); }
.agent-desc { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); display: block; margin-bottom: var(--dream-space-2); line-height: 1.5; }
.agent-meta { display: flex; gap: var(--dream-space-3); margin-bottom: var(--dream-space-3); }
.meta-text { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-2); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }

.empty-state { padding: 100rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: var(--dream-space-2); }
.empty-icon { font-size: 80rpx; color: var(--dream-text-muted); }
.empty-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); }
.empty-hint { font-size: var(--dream-text-sm); color: var(--dream-text-muted); }
.skel { height: 200rpx; background: rgba(255,255,255,0.04); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); }
</style>
