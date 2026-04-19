<template>
  <view class="page">
    <view class="page-header">
      <view class="header-row">
        <text class="page-title">Archive</text>
        <text class="page-subtitle">{{ dreams.length }} dreams</text>
      </view>
    </view>

    <view class="filter-bar">
      <view v-for="f in filters" :key="f.id" :class="['chip-dream', activeFilter === f.id ? 'chip-active' : '']" @tap="activeFilter = f.id">
        <text>{{ f.label }}</text>
      </view>
    </view>

    <view class="search-wrap">
      <input class="input-dream" v-model="searchText" placeholder="Search dreams..." />
    </view>

    <scroll-view class="timeline" scroll-y refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="refresh">
      <!-- Loading skeleton -->
      <view v-if="loading && dreams.length === 0">
        <view class="skel-card" v-for="i in 4" :key="i" />
      </view>

      <!-- Hard error -->
      <view v-else-if="loadError" class="empty-state">
        <text class="empty-icon">&#x26A0;</text>
        <text class="empty-title">Couldn't load dreams</text>
        <text class="empty-hint">{{ loadError }}</text>
        <view class="btn-dream btn-ghost-dream" @tap="refresh"><text>Retry</text></view>
      </view>

      <!-- Empty (filter or truly empty) -->
      <view v-else-if="filteredDreams.length === 0" class="empty-state">
        <text class="empty-icon">&#x1F319;</text>
        <text class="empty-title" v-if="dreams.length === 0">No dreams yet</text>
        <text class="empty-title" v-else>No dreams match</text>
        <text class="empty-hint" v-if="dreams.length === 0">Tap Record to capture your first dream.</text>
        <view v-if="dreams.length === 0" class="btn-dream btn-primary-dream" @tap="goRecord"><text>Record a dream</text></view>
      </view>

      <!-- Timeline -->
      <view v-for="(group, date) in groupedDreams" :key="date" class="tl-group">
        <text class="tl-date">{{ date }}</text>
        <view
          v-for="d in group"
          :key="d.id"
          class="tl-item glass-card"
          @tap="goTo(d.id)"
          @longpress="onLongPress(d)"
        >
          <view class="tl-dot dot-pulse" :class="'dot-' + d.status"></view>
          <view class="tl-content">
            <text class="tl-title">{{ d.title || 'Untitled' }}</text>
            <text class="tl-time">{{ formatTime(d.created_at) }}</text>
            <view class="tl-chips" v-if="d.emotion_tags?.length">
              <text v-for="t in d.emotion_tags.slice(0, 2)" :key="t" class="chip-dream chip-emotion">{{ t }}</text>
            </view>
          </view>
          <view class="tl-actions">
            <view class="tl-action" @tap.stop="onEdit(d)"><text class="tl-action-icon">&#x270E;</text></view>
            <view class="tl-action" @tap.stop="onDelete(d)"><text class="tl-action-icon">&#x1F5D1;</text></view>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- Edit modal -->
    <view v-if="editing" class="modal-overlay" @tap.self="editing = null">
      <view class="modal-card">
        <text class="modal-title">Edit dream</text>
        <text class="modal-label">Title</text>
        <input class="modal-input" v-model="editTitle" maxlength="120" placeholder="Untitled" />
        <view class="modal-actions">
          <view class="btn-dream btn-ghost-dream flex1" @tap="editing = null"><text>Cancel</text></view>
          <view class="btn-dream btn-primary-dream flex1" @tap="onSaveEdit"><text>Save</text></view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listDreams, deleteDream, updateDream, type Dream } from '../../api/dream'

const dreams = ref<Dream[]>([])
const activeFilter = ref('all')
const searchText = ref('')
const loading = ref(false)
const refreshing = ref(false)
const loadError = ref('')
const editing = ref<Dream | null>(null)
const editTitle = ref('')

const filters = [
  { id: 'all', label: 'All' },
  { id: 'completed', label: 'With Video' },
  { id: 'interpreted', label: 'Interpreted' },
]

async function refresh() {
  refreshing.value = true
  loadError.value = ''
  try {
    dreams.value = await listDreams(0, 100)
  } catch (e: any) {
    if (e?.code === 401) { /* api layer redirected */ return }
    loadError.value = e?.body?.detail || 'Network error'
  } finally {
    refreshing.value = false
    loading.value = false
  }
}

onShow(async () => {
  loading.value = dreams.value.length === 0
  await refresh()
})

const filteredDreams = computed(() => {
  let r = dreams.value
  if (activeFilter.value === 'completed') r = r.filter(d => d.video_url)
  else if (activeFilter.value === 'interpreted') r = r.filter(d => d.interpretation)
  if (searchText.value.trim()) {
    const q = searchText.value.toLowerCase()
    r = r.filter(d => (d.title || '').toLowerCase().includes(q) || d.emotion_tags?.some(t => t.toLowerCase().includes(q)))
  }
  return r
})

const groupedDreams = computed(() => {
  const g: Record<string, Dream[]> = {}
  for (const d of filteredDreams.value) { const k = formatDate(d.created_at); if (!g[k]) g[k] = []; g[k].push(d) }
  return g
})

function formatDate(d: string) { const dt = new Date(d); const diff = Date.now() - dt.getTime(); if (diff < 86400000) return 'Today'; if (diff < 172800000) return 'Yesterday'; return `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}` }
function formatTime(d: string) { const dt = new Date(d); return `${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}` }
function goTo(id: string) { uni.navigateTo({ url: `/pages/dream/dream?id=${id}` }) }
function goRecord() { uni.switchTab({ url: '/pages/record/record' }) }

// Long-press shows the action sheet on touch devices that don't surface inline
// action buttons clearly. Inline buttons stay as the primary affordance.
function onLongPress(d: Dream) {
  uni.showActionSheet({
    itemList: ['Edit title', 'Delete'],
    success: (res) => {
      if (res.tapIndex === 0) onEdit(d)
      else if (res.tapIndex === 1) onDelete(d)
    },
  })
}

function onEdit(d: Dream) {
  editing.value = d
  editTitle.value = d.title || ''
}

async function onSaveEdit() {
  if (!editing.value) return
  const id = editing.value.id
  try {
    const updated = await updateDream(id, { title: editTitle.value }) as Dream
    // Mutate in place so the list re-renders without a refetch
    const idx = dreams.value.findIndex(d => d.id === id)
    if (idx >= 0) dreams.value[idx] = { ...dreams.value[idx], ...updated }
    editing.value = null
    uni.showToast({ title: 'Saved', icon: 'none' })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Save failed', icon: 'none' })
  }
}

function onDelete(d: Dream) {
  uni.showModal({
    title: 'Delete this dream?',
    content: (d.title || 'Untitled') + ' will be permanently removed from your archive and the plaza.',
    confirmText: 'Delete',
    confirmColor: '#ef4444',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteDream(d.id)
        // Optimistic local removal — no extra fetch
        dreams.value = dreams.value.filter(x => x.id !== d.id)
        uni.showToast({ title: 'Deleted', icon: 'none' })
      } catch (e: any) {
        uni.showToast({ title: e?.body?.detail || 'Delete failed', icon: 'none' })
      }
    },
  })
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); }
.header-row { display: flex; justify-content: space-between; align-items: baseline; }
.filter-bar { display: flex; gap: var(--dream-space-2); padding: var(--dream-space-3) var(--dream-space-5); }
.search-wrap { padding: 0 var(--dream-space-5) var(--dream-space-3); }
.timeline { padding: 0 var(--dream-space-5); height: calc(100vh - 420rpx); }

.tl-group { margin-bottom: var(--dream-space-5); }
.tl-date { font-size: var(--dream-text-xs); color: var(--dream-primary-400); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin-bottom: var(--dream-space-3); }
.tl-item { display: flex; align-items: center; padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); gap: var(--dream-space-3); }
.tl-dot { width: 16rpx; height: 16rpx; border-radius: var(--dream-radius-full); flex-shrink: 0; }
.dot-completed { background: var(--dream-success); }
.dot-generating { background: var(--dream-warning); }
.dot-scripted { background: var(--dream-primary-400); }
.dot-interviewing { background: var(--dream-text-muted); }
.tl-content { flex: 1; min-width: 0; }
.tl-title { font-size: var(--dream-text-base); font-weight: 500; color: var(--dream-text-primary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tl-time { font-size: var(--dream-text-xs); color: var(--dream-text-muted); display: block; margin-top: 4rpx; }
.tl-chips { display: flex; gap: var(--dream-space-1); margin-top: var(--dream-space-2); }

.tl-actions { display: flex; gap: 8rpx; flex-shrink: 0; opacity: 0.5; }
.tl-action {
  width: 56rpx; height: 56rpx;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.04);
  border-radius: 50%;
}
.tl-action-icon { color: var(--dream-text-secondary); font-size: 24rpx; }

/* Skeleton */
.skel-card {
  height: 140rpx;
  background: linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.05) 50%, rgba(255,255,255,0.02) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--dream-radius-lg);
  margin-bottom: var(--dream-space-3);
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Empty / error states */
.empty-state {
  padding: 100rpx 40rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--dream-space-2);
  text-align: center;
}
.empty-icon { font-size: 80rpx; color: var(--dream-text-muted); }
.empty-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); font-weight: 500; }
.empty-hint { font-size: var(--dream-text-sm); color: var(--dream-text-muted); margin-bottom: var(--dream-space-3); line-height: 1.5; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; z-index: 30;
  background: rgba(6,6,18,0.85);
  display: flex; align-items: center; justify-content: center;
  padding: var(--dream-space-4);
}
.modal-card {
  width: 100%;
  max-width: 580rpx;
  background: var(--dream-bg-card);
  border: 1rpx solid var(--dream-glass-border);
  border-radius: var(--dream-radius-lg);
  padding: var(--dream-space-5);
  display: flex; flex-direction: column; gap: var(--dream-space-3);
}
.modal-title { color: var(--dream-text-primary); font-size: var(--dream-text-lg); font-weight: 600; }
.modal-label { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); }
.modal-input {
  background: var(--dream-bg-input);
  border: 1rpx solid var(--dream-border-default);
  border-radius: var(--dream-radius-md);
  padding: var(--dream-space-3);
  color: var(--dream-text-primary);
  font-size: var(--dream-text-base);
}
.modal-actions { display: flex; gap: var(--dream-space-2); margin-top: var(--dream-space-2); }
.flex1 { flex: 1; }
</style>
