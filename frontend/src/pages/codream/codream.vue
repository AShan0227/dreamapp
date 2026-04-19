<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Co-Dreaming</text>
      <view class="back" />
    </view>

    <text class="subtitle">Two or more dreamers, one shared theme. Each records independently, then we weave a combined dream.</text>

    <view class="action-row">
      <view class="btn btn-primary flex1" @tap="showCreate = !showCreate">
        <text class="btn-text">{{ showCreate ? 'Cancel' : 'Open new session' }}</text>
      </view>
      <view class="btn btn-secondary flex1" @tap="showJoin = !showJoin">
        <text class="btn-text">{{ showJoin ? 'Cancel' : 'Join with code' }}</text>
      </view>
    </view>

    <view v-if="showCreate" class="form-card">
      <text class="form-label">Title</text>
      <input class="form-input" v-model="newTitle" placeholder="The lake we all see" maxlength="120" />
      <text class="form-label">Theme (everyone dreams about this)</text>
      <textarea class="form-input" v-model="newTheme" :auto-height="true" placeholder="A moonlit lake at midnight, something rising from the water" maxlength="2000" />
      <text class="form-label">Max participants</text>
      <input class="form-input" v-model.number="newMax" type="number" placeholder="4" />
      <view class="btn btn-primary" @tap="onCreate"><text class="btn-text">Open session</text></view>
    </view>

    <view v-if="showJoin" class="form-card">
      <text class="form-label">Invite code</text>
      <input class="form-input" v-model="joinCode" placeholder="6-character code" maxlength="10" style="text-transform: uppercase;" />
      <view class="btn btn-primary" @tap="onJoin"><text class="btn-text">Join</text></view>
    </view>

    <text v-if="sessions.length" class="section-label">My sessions</text>
    <view v-for="s in sessions" :key="s.id" class="session-card" @tap="goSession(s.id)">
      <view class="session-head">
        <text class="session-title">{{ s.title }}</text>
        <text class="session-status" :class="'st-' + s.status">{{ s.status }}</text>
      </view>
      <text class="session-theme">{{ s.theme }}</text>
      <view class="session-meta">
        <text v-if="s.is_creator" class="creator-tag">CREATOR</text>
        <text class="invite-code">{{ s.invite_code }}</text>
        <text class="session-time">{{ formatTime(s.created_at) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { codreamCreate, codreamJoin, codreamListMine } from '@/api/dream'

const sessions = ref<any[]>([])
const showCreate = ref(false)
const showJoin = ref(false)
const newTitle = ref('')
const newTheme = ref('')
const newMax = ref(4)
const joinCode = ref('')

onMounted(async () => { await load() })

async function load() {
  try { sessions.value = await codreamListMine() || [] } catch {}
}

async function onCreate() {
  if (!newTitle.value.trim() || !newTheme.value.trim()) {
    uni.showToast({ title: 'Title + theme required', icon: 'none' }); return
  }
  try {
    const s: any = await codreamCreate(newTitle.value, newTheme.value, newMax.value || 4)
    uni.showToast({ title: 'Session opened', icon: 'none' })
    showCreate.value = false
    newTitle.value = ''; newTheme.value = ''
    await load()
    goSession(s.id)
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Create failed', icon: 'none' })
  }
}

async function onJoin() {
  if (!joinCode.value.trim()) return
  try {
    const s: any = await codreamJoin(joinCode.value.toUpperCase())
    uni.showToast({ title: 'Joined', icon: 'none' })
    showJoin.value = false; joinCode.value = ''
    await load()
    goSession(s.id)
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Join failed', icon: 'none' })
  }
}

function goSession(id: string) {
  uni.navigateTo({ url: `/pages/codream/codream?id=${id}` })
}

function formatTime(s: string | null) { if (!s) return ''; const dt = new Date(s); return `${dt.getMonth()+1}/${dt.getDate()}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.action-row { display: flex; gap: var(--dream-space-2); margin-bottom: var(--dream-space-3); }
.flex1 { flex: 1; }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-3); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-secondary { background: var(--dream-bg-card); border: 1rpx solid var(--dream-border-default); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }

.form-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-3); display: flex; flex-direction: column; gap: var(--dream-space-2); }
.form-label { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); }
.form-input { background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: var(--dream-space-3); color: var(--dream-text-primary); font-size: var(--dream-text-base); }

.section-label { font-size: var(--dream-text-xs); color: var(--dream-primary-300); font-weight: 700; text-transform: uppercase; letter-spacing: 2rpx; display: block; margin: var(--dream-space-3) 0 var(--dream-space-2); }

.session-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); }
.session-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4rpx; }
.session-title { font-size: var(--dream-text-md); color: var(--dream-text-primary); font-weight: 500; }
.session-status { font-size: 18rpx; font-weight: 600; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.st-open { background: rgba(20,184,166,0.15); color: #5eead4; }
.st-recording { background: rgba(245,158,11,0.15); color: #fbbf24; }
.st-completed { background: rgba(16,185,129,0.15); color: #34d399; }
.session-theme { font-size: var(--dream-text-sm); color: var(--dream-text-secondary); display: block; margin: var(--dream-space-1) 0; line-height: 1.4; }
.session-meta { display: flex; gap: var(--dream-space-2); align-items: center; margin-top: var(--dream-space-2); }
.creator-tag { font-size: 18rpx; background: rgba(139,92,246,0.15); color: #c4b5fd; padding: 2rpx 8rpx; border-radius: var(--dream-radius-sm); }
.invite-code { font-size: var(--dream-text-sm); color: var(--dream-text-accent); font-family: var(--dream-font-mono); }
.session-time { font-size: var(--dream-text-xs); color: var(--dream-text-muted); margin-left: auto; }
</style>
