<template>
  <view class="kn-screen dc-screen">
    <DreamAtmosphere variant="solaris" :star-count="30" />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">knowledge</text>
      <view class="back" />
    </view>

    <view class="hero">
      <text class="hero-eyebrow dc-eyebrow">the library</text>
      <text class="hero-title dc-display">梦境知识库</text>
      <text class="hero-sub dc-narrative">荣格 · 弗洛伊德 · 当代脑科学 · 中医 · 亚文化</text>
    </view>

    <!-- Scheduler status -->
    <view class="card">
      <view class="card-header">
        <text class="card-title">Sleep cycle</text>
        <view class="run-now-btn" @tap="onRunNow"><text>Run now</text></view>
      </view>
      <view v-if="scheduler" class="meta-grid">
        <view class="meta-cell">
          <text class="meta-label">Status</text>
          <text class="meta-value" :class="scheduler.running ? 'meta-ok' : 'meta-warn'">
            {{ scheduler.running ? 'Running' : 'Stopped' }}
          </text>
        </view>
        <view class="meta-cell">
          <text class="meta-label">Cycle interval</text>
          <text class="meta-value">{{ scheduler.interval_hours }}h</text>
        </view>
        <view class="meta-cell">
          <text class="meta-label">Runs</text>
          <text class="meta-value">{{ scheduler.run_count }}</text>
        </view>
        <view class="meta-cell">
          <text class="meta-label">Last run</text>
          <text class="meta-value">{{ scheduler.last_run_at ? formatTime(scheduler.last_run_at) : '—' }}</text>
        </view>
      </view>
      <view v-if="scheduler && scheduler.last_result" class="last-result">
        <text class="lr-label">Last result</text>
        <text class="lr-value">decayed={{ scheduler.last_result.decayed }}, promoted={{ scheduler.last_result.promoted_l2_to_l1 }}, merged={{ scheduler.last_result.merged_duplicates }}, pruned={{ scheduler.last_result.pruned_quarantined }}</text>
      </view>
    </view>

    <!-- Top entries by use_count -->
    <view class="card">
      <view class="card-header">
        <text class="card-title">Most used entries</text>
        <view class="seg">
          <view v-for="b in byOptions" :key="b.k" class="seg-item" :class="{ 'seg-active': by === b.k }" @tap="setBy(b.k)">
            <text>{{ b.label }}</text>
          </view>
        </view>
      </view>
      <view v-for="e in topEntries" :key="e.id" class="entry-row">
        <view class="entry-tier" :class="'tier-' + e.tier">{{ e.tier }}</view>
        <view class="entry-body">
          <text class="entry-name">{{ e.name }}</text>
          <text class="entry-meta">
            {{ e.source }} · uses {{ e.use_count }} · 👍{{ e.success_count }}  👎{{ e.failure_count }} · conf {{ (e.confidence * 100).toFixed(0) }}%
          </text>
        </view>
        <view class="entry-status" :class="'status-' + e.status">{{ e.status }}</view>
      </view>
      <text v-if="topEntries.length === 0" class="empty-line">No entries yet.</text>
    </view>

    <!-- Research dashboard -->
    <view class="card">
      <view class="card-header">
        <text class="card-title">Research</text>
        <view class="seg">
          <view v-for="t in researchTabs" :key="t.k" class="seg-item" :class="{ 'seg-active': researchTab === t.k }" @tap="setResearchTab(t.k)">
            <text>{{ t.label }}</text>
          </view>
        </view>
      </view>

      <!-- Symbols -->
      <view v-if="researchTab === 'symbols'">
        <view v-for="row in symbolRows" :key="row.symbol" class="bar-row">
          <text class="bar-label">{{ row.symbol }}</text>
          <view class="bar-track">
            <view class="bar-fill" :style="{ width: pct(row.count, symbolMax) + '%' }" />
          </view>
          <text class="bar-count">{{ row.count }}</text>
        </view>
        <text v-if="symbolRows.length === 0" class="empty-line">No entity data yet — record + interpret a few dreams.</text>
      </view>

      <!-- Emotions -->
      <view v-if="researchTab === 'emotions'">
        <text class="research-meta" v-if="emotion">Across {{ emotion.total_dreams_with_script }} dreams with structured scripts.</text>
        <view v-for="row in (emotion?.top_emotions || []).slice(0, 12)" :key="row.emotion" class="bar-row">
          <text class="bar-label">{{ row.emotion }}</text>
          <view class="bar-track">
            <view class="bar-fill bar-fill-warm" :style="{ width: pct(row.count, emotionMax) + '%' }" />
          </view>
          <text class="bar-count">{{ row.count }}</text>
        </view>
      </view>

      <!-- Papers -->
      <view v-if="researchTab === 'papers'">
        <text class="research-meta" v-if="papers">{{ papers.total_papers }} papers in knowledge base · ranked by use_count.</text>
        <view v-for="p in (papers?.papers || []).slice(0, 8)" :key="p.id" class="paper-row">
          <view class="paper-head">
            <text class="paper-title">{{ p.title }}</text>
            <text class="paper-uses">{{ p.use_count }}×</text>
          </view>
          <text class="paper-meta">
            {{ (p.authors || []).slice(0, 2).join(', ') }}{{ p.authors && p.authors.length > 2 ? ' et al.' : '' }}{{ p.year ? ` (${p.year})` : '' }}{{ p.journal ? ` — ${p.journal}` : '' }}
          </text>
        </view>
      </view>

      <!-- Cultural -->
      <view v-if="researchTab === 'cultural'">
        <view v-for="row in cultural.slice(0, 12)" :key="row.name" class="bar-row">
          <text class="bar-label">{{ row.name }}<text class="bar-sub"> · {{ row.culture }}</text></text>
          <view class="bar-track">
            <view class="bar-fill bar-fill-cool" :style="{ width: pct(row.use_count, culturalMax) + '%' }" />
          </view>
          <text class="bar-count">{{ row.use_count }}</text>
        </view>
        <text v-if="cultural.length === 0" class="empty-line">No cultural citations yet.</text>
      </view>

      <view class="export-row">
        <text class="export-label">Export CSV:</text>
        <text class="export-link" @tap="onExport('symbols')">Symbols</text>
        <text class="export-link" @tap="onExport('emotions')">Emotions</text>
        <text class="export-link" @tap="onExport('papers')">Papers</text>
        <text class="export-link" @tap="onExport('cultural')">Cultural</text>
      </view>
    </view>

    <!-- Quarantined -->
    <view class="card">
      <view class="card-header">
        <text class="card-title">Quarantined ({{ quarantined.length }})</text>
      </view>
      <view v-for="e in quarantined" :key="e.id" class="entry-row entry-quarantined">
        <view class="entry-tier" :class="'tier-' + e.tier">{{ e.tier }}</view>
        <view class="entry-body">
          <text class="entry-name">{{ e.name }}</text>
          <text class="entry-content">{{ e.content }}</text>
          <text class="entry-meta">
            {{ e.source }} · 👎{{ e.failure_count }}  👍{{ e.success_count }} · conf {{ (e.confidence * 100).toFixed(0) }}%
          </text>
        </view>
        <view class="entry-restore" @tap="onRestore(e)">
          <text>Restore</text>
        </view>
      </view>
      <text v-if="quarantined.length === 0" class="empty-line">No quarantined entries.</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  knowledgeTop,
  knowledgeQuarantined,
  knowledgeRestore,
  knowledgeRunSleepCycle,
  knowledgeSchedulerStatus,
  researchSymbolFrequency,
  researchEmotionDistribution,
  researchCulturalBreakdown,
  researchPapersCited,
  researchExportUrl,
} from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const scheduler = ref<any>(null)
const topEntries = ref<any[]>([])
const quarantined = ref<any[]>([])
const by = ref<'use_count' | 'success' | 'failure' | 'confidence'>('use_count')

// Research dashboard state
type ResearchTab = 'symbols' | 'emotions' | 'papers' | 'cultural'
const researchTab = ref<ResearchTab>('symbols')
const researchTabs = [
  { k: 'symbols' as const, label: 'Symbols' },
  { k: 'emotions' as const, label: 'Emotions' },
  { k: 'papers' as const, label: 'Papers' },
  { k: 'cultural' as const, label: 'Cultural' },
]
const symbolRows = ref<{ symbol: string; count: number }[]>([])
const emotion = ref<any>(null)
const papers = ref<any>(null)
const cultural = ref<any[]>([])
const symbolMax = computed(() => Math.max(1, ...symbolRows.value.map(r => r.count)))
const emotionMax = computed(() => Math.max(1, ...((emotion.value?.top_emotions || []) as any[]).map((r: any) => r.count)))
const culturalMax = computed(() => Math.max(1, ...cultural.value.map(r => r.use_count || 0)))

function pct(v: number, max: number): number {
  if (!max) return 0
  return Math.max(2, Math.round((v / max) * 100))
}

async function setResearchTab(tab: ResearchTab) {
  researchTab.value = tab
  await loadResearchTab(tab)
}

async function loadResearchTab(tab: ResearchTab) {
  try {
    if (tab === 'symbols' && symbolRows.value.length === 0) {
      symbolRows.value = (await researchSymbolFrequency(20)) || []
    } else if (tab === 'emotions' && !emotion.value) {
      emotion.value = await researchEmotionDistribution()
    } else if (tab === 'papers' && !papers.value) {
      papers.value = await researchPapersCited()
    } else if (tab === 'cultural' && cultural.value.length === 0) {
      cultural.value = (await researchCulturalBreakdown()) || []
    }
  } catch (e) { /* surfaced via global toast */ }
}

function onExport(kind: 'symbols' | 'emotions' | 'papers' | 'cultural') {
  // H5 navigates the browser; native targets fall back to copying the URL
  // since they can't trigger a download.
  const url = researchExportUrl(kind)
  // #ifdef H5
  if (typeof window !== 'undefined') { window.location.href = url; return }
  // #endif
  uni.setClipboardData({ data: url, success: () => uni.showToast({ title: 'CSV URL copied', icon: 'none' }) })
}

const byOptions = [
  { k: 'use_count' as const, label: 'Used' },
  { k: 'success' as const, label: '👍' },
  { k: 'failure' as const, label: '👎' },
  { k: 'confidence' as const, label: 'Conf' },
]

onMounted(async () => { await refresh() })

async function refresh() {
  try { scheduler.value = await knowledgeSchedulerStatus() } catch {}
  try { topEntries.value = await knowledgeTop(by.value, 10) || [] } catch {}
  try { quarantined.value = await knowledgeQuarantined(50) || [] } catch {}
  await loadResearchTab(researchTab.value)
}

async function setBy(k: typeof by.value) {
  by.value = k
  try { topEntries.value = await knowledgeTop(k, 10) || [] } catch {}
}

async function onRunNow() {
  uni.showLoading({ title: 'Running…' })
  try {
    const r: any = await knowledgeRunSleepCycle(false)
    uni.hideLoading()
    uni.showToast({
      title: `Decayed ${r.decayed}, promoted ${r.promoted_l2_to_l1}`,
      icon: 'none',
    })
    await refresh()
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

async function onRestore(e: any) {
  uni.showModal({
    title: 'Restore entry?',
    content: `${e.name} will go back to probation and may be re-cited in interpretations.`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await knowledgeRestore(e.id)
        uni.showToast({ title: 'Restored', icon: 'none' })
        await refresh()
      } catch (err: any) {
        uni.showToast({ title: err?.body?.detail || 'Restore failed', icon: 'none' })
      }
    },
  })
}

function formatTime(s: string) {
  const dt = new Date(s)
  return `${dt.getMonth()+1}/${dt.getDate()} ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}`
}

function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style lang="scss" scoped>
.kn-screen {
  min-height: 100vh;
  padding: 32rpx;
  padding-top: calc(60rpx + env(safe-area-inset-top, 0));
  position: relative;
  z-index: 1;
}
.header, .hero, .card { position: relative; z-index: 2; }

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
  padding: 24rpx 0 32rpx;
  display: flex; flex-direction: column; align-items: center; gap: 8rpx;
}
.hero-eyebrow { display: block; }
.hero-title { font-size: 56rpx; line-height: 1.2; display: block; margin: 4rpx 0; }
.hero-sub { font-size: 24rpx; color: var(--dream-text-secondary); display: block; max-width: 540rpx; }

.card {
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 24rpx;
  padding: 32rpx 28rpx;
  margin-bottom: 20rpx;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.card-title {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
}

.run-now-btn {
  background: var(--dream-gradient-primary);
  padding: 8rpx 20rpx;
  border-radius: var(--dream-radius-full);
  color: white;
  font-size: var(--dream-text-sm);
}

.meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--dream-space-3); }
.meta-cell { display: flex; flex-direction: column; gap: 4rpx; }
.meta-label { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
.meta-value { font-size: var(--dream-text-base); color: var(--dream-text-primary); }
.meta-ok { color: var(--dream-success); }
.meta-warn { color: var(--dream-warning); }

.last-result {
  margin-top: var(--dream-space-3);
  padding-top: var(--dream-space-3);
  border-top: 1rpx solid var(--dream-border-subtle);
}
.lr-label { font-size: var(--dream-text-xs); color: var(--dream-text-muted); display: block; margin-bottom: 4rpx; }
.lr-value { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); display: block; line-height: 1.5; }

.seg {
  display: flex;
  background: var(--dream-bg-input);
  border-radius: var(--dream-radius-full);
  padding: 3rpx;
  gap: 2rpx;
}
.seg-item {
  padding: 6rpx 14rpx;
  border-radius: var(--dream-radius-full);
  font-size: var(--dream-text-xs);
  color: var(--dream-text-muted);
}
.seg-active { background: var(--dream-primary-600); color: white; }

.entry-row {
  display: flex;
  align-items: flex-start;
  gap: var(--dream-space-2);
  padding: var(--dream-space-3) 0;
  border-top: 1rpx solid var(--dream-border-subtle);
}
.entry-row:first-of-type { border-top: none; }
.entry-tier {
  font-size: 18rpx;
  font-weight: 700;
  padding: 4rpx 8rpx;
  border-radius: var(--dream-radius-sm);
  flex-shrink: 0;
  min-width: 36rpx;
  text-align: center;
}
.tier-L0 { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.tier-L1 { background: rgba(139, 92, 246, 0.15); color: #c4b5fd; }
.tier-L2 { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.entry-body { flex: 1; min-width: 0; }
.entry-name { font-size: var(--dream-text-base); color: var(--dream-text-primary); font-weight: 500; display: block; }
.entry-content { font-size: var(--dream-text-xs); color: var(--dream-text-muted); display: block; margin-top: 4rpx; line-height: 1.4; }
.entry-meta { font-size: var(--dream-text-xs); color: var(--dream-text-muted); display: block; margin-top: 4rpx; }
.entry-status {
  font-size: 18rpx;
  font-weight: 600;
  padding: 4rpx 8rpx;
  border-radius: var(--dream-radius-sm);
  text-transform: uppercase;
  flex-shrink: 0;
  align-self: flex-start;
}
.status-graduated { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.status-probation { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.status-quarantined { background: rgba(239, 68, 68, 0.15); color: #f87171; }

.entry-quarantined { background: rgba(239, 68, 68, 0.04); margin: 0 -8rpx; padding: var(--dream-space-3) 8rpx; border-radius: 8rpx; }
.entry-restore {
  background: var(--dream-bg-card);
  border: 1rpx solid var(--dream-border-default);
  padding: 6rpx 14rpx;
  border-radius: var(--dream-radius-full);
  font-size: var(--dream-text-xs);
  color: var(--dream-text-accent);
  flex-shrink: 0;
  align-self: flex-start;
}

.empty-line { font-size: var(--dream-text-sm); color: var(--dream-text-muted); display: block; padding: var(--dream-space-3) 0; }

/* Research dashboard */
.research-meta {
  font-size: var(--dream-text-xs);
  color: var(--dream-text-muted);
  display: block;
  margin-bottom: var(--dream-space-3);
  font-style: italic;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: var(--dream-space-2);
  padding: 8rpx 0;
}
.bar-label {
  flex: 0 0 200rpx;
  font-size: var(--dream-text-sm);
  color: var(--dream-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-sub { color: var(--dream-text-muted); font-size: var(--dream-text-xs); }
.bar-track {
  flex: 1;
  height: 12rpx;
  background: var(--dream-bg-input);
  border-radius: var(--dream-radius-full);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--dream-gradient-primary);
  border-radius: var(--dream-radius-full);
  transition: width var(--dream-transition-normal);
}
.bar-fill-warm { background: linear-gradient(90deg, #f59e0b, #ef4444); }
.bar-fill-cool { background: linear-gradient(90deg, #14b8a6, #818cf8); }
.bar-count {
  flex: 0 0 60rpx;
  text-align: right;
  font-size: var(--dream-text-xs);
  color: var(--dream-text-muted);
  font-variant-numeric: tabular-nums;
}

.paper-row {
  padding: var(--dream-space-3) 0;
  border-top: 1rpx solid var(--dream-border-subtle);
}
.paper-row:first-of-type { border-top: none; }
.paper-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--dream-space-2);
  margin-bottom: 4rpx;
}
.paper-title {
  flex: 1;
  font-size: var(--dream-text-sm);
  color: var(--dream-text-primary);
  font-weight: 500;
  line-height: 1.4;
}
.paper-uses {
  flex-shrink: 0;
  font-size: var(--dream-text-xs);
  color: var(--dream-primary-300);
  font-variant-numeric: tabular-nums;
}
.paper-meta {
  font-size: var(--dream-text-xs);
  color: var(--dream-text-muted);
  font-style: italic;
  display: block;
  line-height: 1.5;
}

.export-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dream-space-2);
  padding-top: var(--dream-space-3);
  margin-top: var(--dream-space-3);
  border-top: 1rpx solid var(--dream-border-subtle);
}
.export-label { font-size: var(--dream-text-xs); color: var(--dream-text-muted); }
.export-link {
  font-size: var(--dream-text-xs);
  color: var(--dream-text-accent);
  padding: 4rpx 10rpx;
  border-radius: var(--dream-radius-sm);
  background: rgba(139,92,246,0.1);
}
</style>
