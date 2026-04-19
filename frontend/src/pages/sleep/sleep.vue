<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Sleep × Dreams</text>
      <view class="back" />
    </view>

    <text class="subtitle">Cross-correlate sleep quality with dream content. Manual entry now; Apple Health / Mi Band auto-import on roadmap.</text>

    <view class="form-card">
      <text class="form-label">Last night — duration (minutes)</text>
      <input class="form-input" v-model.number="durationMin" type="number" placeholder="e.g. 420 (7h)" />
      <text class="form-label">REM minutes (optional)</text>
      <input class="form-input" v-model.number="remMin" type="number" placeholder="e.g. 90" />
      <text class="form-label">Deep minutes (optional)</text>
      <input class="form-input" v-model.number="deepMin" type="number" placeholder="e.g. 70" />
      <view class="btn btn-primary" @tap="onSave">
        <text class="btn-text">Log last night</text>
      </view>
    </view>

    <text class="section-label">Last 30 days</text>
    <view v-if="records.length === 0" class="empty">No sleep records yet.</view>
    <view v-for="r in records" :key="r.id" class="rec-row">
      <text class="rec-date">{{ formatDate(r.night_of) }}</text>
      <view class="rec-bar">
        <view class="rec-fill" :style="{ width: pct(r.duration_minutes) + '%' }" />
      </view>
      <text class="rec-dur">{{ Math.round(r.duration_minutes / 60 * 10) / 10 }}h</text>
      <text v-if="r.rem_minutes" class="rec-rem">REM {{ r.rem_minutes }}m</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { recordSleep, listSleep } from '@/api/dream'

const durationMin = ref<number | null>(null)
const remMin = ref<number | null>(null)
const deepMin = ref<number | null>(null)
const records = ref<any[]>([])

onMounted(async () => { await refresh() })

async function refresh() {
  try { records.value = await listSleep(30) || [] } catch {}
}

async function onSave() {
  if (!durationMin.value) {
    uni.showToast({ title: 'Duration required', icon: 'none' }); return
  }
  // Default to last night (yesterday at 23:00 local)
  const night = new Date()
  night.setDate(night.getDate() - 1)
  night.setHours(23, 0, 0, 0)
  try {
    await recordSleep({
      night_of: night.toISOString(),
      duration_minutes: durationMin.value,
      rem_minutes: remMin.value || null,
      deep_minutes: deepMin.value || null,
      source: 'manual',
    })
    uni.showToast({ title: 'Logged', icon: 'success' })
    durationMin.value = null; remMin.value = null; deepMin.value = null
    await refresh()
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

function pct(mins: number) { return Math.min(100, Math.round((mins / 600) * 100)) }
function formatDate(s: string) { const d = new Date(s); return `${d.getMonth()+1}/${d.getDate()}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.form-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: 8rpx; }
.form-label { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); margin-top: 6rpx; }
.form-input { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); }
.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); margin-top: var(--dream-space-2); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }

.section-label { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin: var(--dream-space-3) 0 var(--dream-space-2); }
.empty { color: var(--dream-text-muted); font-size: var(--dream-text-sm); padding: var(--dream-space-3); text-align: center; }

.rec-row { display: flex; align-items: center; gap: var(--dream-space-2); padding: var(--dream-space-2) 0; }
.rec-date { flex: 0 0 80rpx; color: var(--dream-text-secondary); font-size: var(--dream-text-sm); font-variant-numeric: tabular-nums; }
.rec-bar { flex: 1; height: 12rpx; background: var(--dream-bg-input); border-radius: var(--dream-radius-full); overflow: hidden; }
.rec-fill { height: 100%; background: var(--dream-gradient-aurora); }
.rec-dur { flex: 0 0 70rpx; text-align: right; color: var(--dream-text-primary); font-size: var(--dream-text-sm); font-variant-numeric: tabular-nums; }
.rec-rem { flex: 0 0 100rpx; color: var(--dream-text-muted); font-size: var(--dream-text-xs); }
</style>
