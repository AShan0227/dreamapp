<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Customize Dream</text>
      <view class="back" />
    </view>

    <text class="subtitle">Re-render your dream with new style, mood, camera, music or completion. The original stays intact.</text>

    <view class="form-card">
      <text class="form-label">Source dream</text>
      <picker mode="selector" :range="dreamLabels" @change="onPickDream">
        <view class="picker">
          <text class="picker-text">{{ pickedDream ? pickedDream.title || 'Untitled' : 'Tap to choose…' }}</text>
        </view>
      </picker>

      <text class="form-label">Style</text>
      <view class="chip-row">
        <view v-for="s in STYLES" :key="s" :class="['chip', params.style === s && 'chip-active']" @tap="setParam('style', s)">
          <text>{{ s }}</text>
        </view>
      </view>

      <text class="form-label">Mood</text>
      <view class="chip-row">
        <view v-for="m in MOODS" :key="m" :class="['chip', params.mood === m && 'chip-active']" @tap="setParam('mood', m)">
          <text>{{ m }}</text>
        </view>
      </view>

      <text class="form-label">Camera</text>
      <view class="chip-row">
        <view v-for="c in CAMERAS" :key="c.id" :class="['chip', params.camera === c.id && 'chip-active']" @tap="setParam('camera', c.id)">
          <text>{{ c.label }}</text>
        </view>
      </view>

      <text class="form-label">Music</text>
      <view class="chip-row">
        <view v-for="m in MUSICS" :key="m" :class="['chip', params.music === m && 'chip-active']" @tap="setParam('music', m)">
          <text>{{ m }}</text>
        </view>
      </view>

      <text class="form-label">Time</text>
      <view class="chip-row">
        <view v-for="t in TIMES" :key="t.id" :class="['chip', params.time === t.id && 'chip-active']" @tap="setParam('time', t.id)">
          <text>{{ t.label }}</text>
        </view>
      </view>

      <text class="form-label">Continue the dream (optional)</text>
      <textarea
        class="form-input"
        v-model="completion"
        :auto-height="true"
        placeholder="The dream cut off — what happens next?"
        maxlength="2000"
      />

      <view class="btn btn-primary" @tap="onSubmit" :class="{ 'btn-disabled': !pickedDream || submitting }">
        <text class="btn-text">{{ submitting ? 'Submitting…' : 'Generate variant' }}</text>
      </view>
    </view>

    <text v-if="cz.length" class="section-label">Recent variants</text>
    <view v-for="c in cz" :key="c.id" class="cz-card">
      <view class="cz-head">
        <text class="cz-status" :class="'st-' + c.status">{{ c.status }}</text>
        <text class="cz-time">{{ formatTime(c.created_at) }}</text>
      </view>
      <text class="cz-params">{{ formatParams(c.parameters) }}</text>
      <video v-if="c.video_url" :src="c.video_url" class="cz-video" controls />
      <text v-else-if="c.status === 'failed'" class="cz-fail">{{ c.failure_reason }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { listDreams, createCustomization, listCustomizations } from '@/api/dream'

const STYLES = ['surreal', 'cyberpunk', 'ink wash', 'film grain', 'anime', 'pastel']
const MOODS = ['horror', 'healing', 'euphoric', 'melancholy', 'tense']
const CAMERAS = [
  { id: 'first_person', label: 'First-person' },
  { id: 'third_person', label: 'Third-person' },
  { id: 'gods_eye', label: "God's eye" },
]
const MUSICS = ['ambient', 'piano', 'electronic', 'silence']
const TIMES = [
  { id: 'slow_mo', label: 'Slow motion' },
  { id: 'time_lapse', label: 'Time lapse' },
  { id: 'normal', label: 'Normal' },
]

const dreams = ref<any[]>([])
const pickedDream = ref<any>(null)
const params = ref<Record<string, string>>({})
const completion = ref('')
const submitting = ref(false)
const cz = ref<any[]>([])

const dreamLabels = computed(() =>
  dreams.value.map(d => `${d.title || 'Untitled'} (${formatTime(d.created_at)})`)
)

onMounted(async () => {
  try { dreams.value = (await listDreams(0, 50)).filter((d: any) => d.dream_script) } catch {}
  await refreshCz()
})

async function refreshCz() {
  try { cz.value = await listCustomizations() || [] } catch {}
}

function setParam(key: string, value: string) {
  params.value = { ...params.value, [key]: params.value[key] === value ? '' : value }
}

function onPickDream(e: any) {
  pickedDream.value = dreams.value[e.detail.value]
}

async function onSubmit() {
  if (!pickedDream.value) return
  const kinds = Object.keys(params.value).filter(k => params.value[k])
  if (completion.value.trim()) kinds.push('completion')

  if (kinds.length === 0) {
    uni.showToast({ title: 'Pick at least one parameter', icon: 'none' }); return
  }

  submitting.value = true
  try {
    await createCustomization(pickedDream.value.id, kinds, params.value, completion.value || undefined)
    uni.showToast({ title: 'Generating in background', icon: 'none' })
    completion.value = ''
    params.value = {}
    setTimeout(refreshCz, 2000)
  } catch (e: any) {
    if (e?.code === 429) {
      uni.showToast({ title: 'Daily quota reached', icon: 'none' })
    } else {
      uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
    }
  }
  submitting.value = false
}

function formatTime(s: string | null) { if (!s) return '—'; const dt = new Date(s); return `${dt.getMonth()+1}/${dt.getDate()}` }
function formatParams(p: any) {
  if (!p || typeof p !== 'object') return ''
  return Object.entries(p).filter(([_, v]) => v).map(([k, v]) => `${k}: ${v}`).join(' · ')
}
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.form-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: var(--dream-space-2); }
.form-label { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); margin-top: var(--dream-space-2); }
.form-input { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); min-height: 80rpx; }
.picker { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); }
.picker-text { color: var(--dream-text-primary); font-size: var(--dream-text-base); }
.chip-row { display: flex; gap: 8rpx; flex-wrap: wrap; }
.chip { padding: 8rpx 16rpx; border-radius: var(--dream-radius-full); background: var(--dream-bg-input); color: var(--dream-text-secondary); font-size: var(--dream-text-sm); }
.chip-active { background: var(--dream-gradient-primary); color: white; }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); margin-top: var(--dream-space-3); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }
.btn-disabled { opacity: 0.4; pointer-events: none; }

.section-label { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin: var(--dream-space-3) 0 var(--dream-space-2); }

.cz-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-3); margin-bottom: var(--dream-space-2); }
.cz-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6rpx; }
.cz-status { font-size: 18rpx; font-weight: 600; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.st-pending { background: rgba(168,162,158,0.15); color: #d6d3d1; }
.st-generating { background: rgba(245,158,11,0.15); color: #fbbf24; }
.st-completed { background: rgba(16,185,129,0.15); color: #34d399; }
.st-failed { background: rgba(239,68,68,0.15); color: #f87171; }
.cz-time { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
.cz-params { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); display: block; margin-bottom: var(--dream-space-2); }
.cz-video { width: 100%; aspect-ratio: 16/9; border-radius: var(--dream-radius-md); }
.cz-fail { font-size: var(--dream-text-sm); color: var(--dream-error); }
</style>
