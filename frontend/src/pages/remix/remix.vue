<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Dream Remix</text>
      <view class="back" />
    </view>

    <text class="subtitle">Splice your dreams together, remix others' plaza dreams, or analyze two dreams in dialogue.</text>

    <view class="kind-tabs">
      <view v-for="k in KINDS" :key="k.id" :class="['kind-tab', activeKind === k.id && 'kind-tab-active']" @tap="activeKind = k.id">
        <text>{{ k.label }}</text>
      </view>
    </view>

    <view class="form-card">
      <view v-if="activeKind === 'splice' || activeKind === 'dialogue'">
        <text class="form-label">Dream A</text>
        <picker mode="selector" :range="dreamLabels" @change="(e) => pickedA = dreams[e.detail.value]">
          <view class="picker"><text class="picker-text">{{ pickedA ? pickedA.title || 'Untitled' : 'Pick a dream…' }}</text></view>
        </picker>
        <text class="form-label">Dream B</text>
        <picker mode="selector" :range="dreamLabels" @change="(e) => pickedB = dreams[e.detail.value]">
          <view class="picker"><text class="picker-text">{{ pickedB ? pickedB.title || 'Untitled' : 'Pick a dream…' }}</text></view>
        </picker>
      </view>

      <view v-if="activeKind === 'splice' || activeKind === 'chain'">
        <text class="form-label">Guidance (optional)</text>
        <textarea class="form-input" v-model="userPrompt" :auto-height="true" placeholder="Make it scary / make them meet at the lake / ..." maxlength="500" />
      </view>

      <view v-if="activeKind === 'chain'">
        <text class="form-label">Continue from your dream</text>
        <picker mode="selector" :range="dreamLabels" @change="(e) => pickedA = dreams[e.detail.value]">
          <view class="picker"><text class="picker-text">{{ pickedA ? pickedA.title || 'Untitled' : 'Pick a dream…' }}</text></view>
        </picker>
      </view>

      <view class="btn btn-primary" @tap="onCreate" :class="{ 'btn-disabled': busy }">
        <text class="btn-text">{{ busy ? 'Generating…' : 'Create remix' }}</text>
      </view>
    </view>

    <text v-if="remixes.length" class="section-label">My remixes</text>
    <view v-for="r in remixes" :key="r.id" class="remix-card">
      <view class="remix-head">
        <text class="remix-kind">{{ r.kind.replace(/_/g, ' ') }}</text>
        <text class="remix-time">{{ formatTime(r.created_at) }}</text>
      </view>
      <text class="remix-title">{{ r.title || 'Untitled remix' }}</text>
      <text v-if="r.user_prompt" class="remix-prompt">"{{ r.user_prompt }}"</text>
      <view v-if="r.kind === 'dialogue' && r.remixed_interpretation" class="dialogue-block">
        <text v-if="r.remixed_interpretation.synthesis" class="dialogue-syn">{{ r.remixed_interpretation.synthesis }}</text>
        <view v-if="r.remixed_interpretation.shared_symbols?.length" class="dialogue-tags">
          <text v-for="s in r.remixed_interpretation.shared_symbols.slice(0,5)" :key="s" class="tag">{{ s }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { listDreams, remixSplice, remixOther, remixChain, remixDialogue, listMyRemixes } from '@/api/dream'

const KINDS = [
  { id: 'splice', label: 'Splice 2 of mine' },
  { id: 'chain', label: 'Continue chain' },
  { id: 'dialogue', label: 'Dream dialogue' },
]

const activeKind = ref('splice')
const dreams = ref<any[]>([])
const pickedA = ref<any>(null)
const pickedB = ref<any>(null)
const userPrompt = ref('')
const busy = ref(false)
const remixes = ref<any[]>([])

const dreamLabels = computed(() => dreams.value.map(d => `${d.title || 'Untitled'} (${formatTime(d.created_at)})`))

onMounted(async () => {
  try { dreams.value = (await listDreams(0, 50)).filter((d: any) => d.dream_script) } catch {}
  await refresh()
})

async function refresh() {
  try { remixes.value = await listMyRemixes() || [] } catch {}
}

async function onCreate() {
  busy.value = true
  try {
    if (activeKind.value === 'splice') {
      if (!pickedA.value || !pickedB.value) throw new Error('Pick both dreams')
      await remixSplice(pickedA.value.id, pickedB.value.id, userPrompt.value)
    } else if (activeKind.value === 'chain') {
      if (!pickedA.value) throw new Error('Pick a dream to continue')
      await remixChain({ previous_dream_id: pickedA.value.id, user_prompt: userPrompt.value })
    } else if (activeKind.value === 'dialogue') {
      if (!pickedA.value || !pickedB.value) throw new Error('Pick both dreams')
      await remixDialogue(pickedA.value.id, pickedB.value.id)
    }
    uni.showToast({ title: 'Remix created', icon: 'none' })
    await refresh()
    pickedA.value = pickedB.value = null
    userPrompt.value = ''
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || e?.message || 'Failed', icon: 'none' })
  }
  busy.value = false
}

function formatTime(s: string | null) { if (!s) return '—'; const dt = new Date(s); return `${dt.getMonth()+1}/${dt.getDate()}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.kind-tabs { display: flex; gap: var(--dream-space-1); margin-bottom: var(--dream-space-3); flex-wrap: wrap; }
.kind-tab { padding: 8rpx 16rpx; border-radius: var(--dream-radius-full); background: var(--dream-bg-input); color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
.kind-tab-active { background: var(--dream-gradient-primary); color: white; }

.form-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: var(--dream-space-2); }
.form-label { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); margin-top: var(--dream-space-2); }
.form-input { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); }
.picker { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); }
.picker-text { color: var(--dream-text-primary); font-size: var(--dream-text-base); }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); margin-top: var(--dream-space-3); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }
.btn-disabled { opacity: 0.4; pointer-events: none; }

.section-label { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin: var(--dream-space-3) 0 var(--dream-space-2); }

.remix-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-3); margin-bottom: var(--dream-space-2); }
.remix-head { display: flex; justify-content: space-between; align-items: center; }
.remix-kind { font-size: 18rpx; padding: 4rpx 10rpx; background: rgba(139,92,246,0.15); color: #c4b5fd; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.remix-time { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
.remix-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); display: block; margin: 6rpx 0; }
.remix-prompt { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); font-style: italic; display: block; }

.dialogue-block { margin-top: var(--dream-space-2); padding: var(--dream-space-2); background: rgba(255,255,255,0.03); border-radius: var(--dream-radius-md); }
.dialogue-syn { font-size: var(--dream-text-sm); color: var(--dream-text-primary); display: block; margin-bottom: var(--dream-space-2); line-height: 1.5; }
.dialogue-tags { display: flex; gap: 6rpx; flex-wrap: wrap; }
.tag { font-size: 18rpx; padding: 4rpx 8rpx; background: var(--dream-bg-input); color: var(--dream-text-accent); border-radius: var(--dream-radius-sm); }
</style>
