<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Customize App</text>
      <view class="back" />
    </view>

    <text class="subtitle">Tell the app how you want it to look. Natural language only — no menus, no settings.</text>

    <view class="form-card">
      <textarea
        class="form-input"
        v-model="prompt"
        :auto-height="true"
        placeholder="e.g. I only care about recording and plaza — hide everything else.
Or: I want to focus on emotion tracking, surface health and recurring patterns prominently.
Or: Make me a creator — homepage = video timeline + share buttons."
        maxlength="500"
      />
      <view class="btn btn-primary" @tap="onSubmit" :class="{ 'btn-disabled': !prompt.trim() || busy }">
        <text class="btn-text">{{ busy ? 'Reconfiguring…' : 'Apply' }}</text>
      </view>
    </view>

    <view v-if="layout" class="config-card">
      <text class="config-section">Current archetype</text>
      <text class="config-value archetype">{{ layout.user_archetype }}</text>

      <text v-if="layout.explanation" class="config-section">Explanation</text>
      <text v-if="layout.explanation" class="config-value">{{ layout.explanation }}</text>

      <text class="config-section">Tab bar</text>
      <view class="tab-grid">
        <view v-for="t in (layout.tab_bar || [])" :key="t.id" :class="['tab-item', t.hidden && 'tab-hidden', t.primary && 'tab-primary']">
          <text class="tab-icon">{{ t.icon }}</text>
          <text class="tab-label">{{ t.label }}</text>
        </view>
      </view>

      <text class="config-section">Home widgets</text>
      <view class="widget-list">
        <view v-for="w in (layout.home_widgets || [])" :key="w.id" :class="['widget-item', w.hidden && 'widget-hidden']">
          <text class="widget-id">{{ w.id }}</text>
          <text class="widget-meta">{{ w.size }} · {{ w.hidden ? 'hidden' : 'visible' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { vibeCustomize, vibeGetLayout } from '@/api/dream'

const prompt = ref('')
const busy = ref(false)
const layout = ref<any>(null)

onMounted(async () => {
  try { const r: any = await vibeGetLayout(); layout.value = r.layout } catch {}
})

async function onSubmit() {
  if (!prompt.value.trim()) return
  busy.value = true
  try {
    const r: any = await vibeCustomize(prompt.value)
    layout.value = r.layout
    uni.showToast({ title: 'Layout updated', icon: 'none' })
    prompt.value = ''
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
  busy.value = false
}

function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.form-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: var(--dream-space-3); }
.form-input { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); min-height: 200rpx; }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }
.btn-disabled { opacity: 0.4; pointer-events: none; }

.config-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); }
.config-section { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; display: block; margin: var(--dream-space-3) 0 var(--dream-space-1); letter-spacing: 1rpx; }
.config-section:first-child { margin-top: 0; }
.config-value { font-size: var(--dream-text-sm); color: var(--dream-text-primary); display: block; line-height: 1.5; }
.archetype { font-size: var(--dream-text-md); color: var(--dream-text-accent); font-weight: 500; text-transform: capitalize; }

.tab-grid { display: flex; flex-wrap: wrap; gap: var(--dream-space-2); }
.tab-item { background: var(--dream-bg-input); padding: 12rpx 16rpx; border-radius: var(--dream-radius-md); display: flex; align-items: center; gap: 8rpx; }
.tab-primary { background: var(--dream-gradient-primary); }
.tab-hidden { opacity: 0.3; }
.tab-icon { font-size: var(--dream-text-base); }
.tab-label { color: var(--dream-text-primary); font-size: var(--dream-text-sm); }

.widget-list { display: flex; flex-direction: column; gap: 4rpx; }
.widget-item { display: flex; justify-content: space-between; padding: 8rpx 12rpx; background: var(--dream-bg-input); border-radius: var(--dream-radius-sm); }
.widget-id { color: var(--dream-text-primary); font-size: var(--dream-text-sm); }
.widget-meta { color: var(--dream-text-muted); font-size: var(--dream-text-xs); }
.widget-hidden { opacity: 0.3; }
</style>
