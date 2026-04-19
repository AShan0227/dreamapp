<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">{{ currentThread ? otherName : 'Messages' }}</text>
      <view class="back" />
    </view>

    <!-- Thread list -->
    <view v-if="!currentThread">
      <view v-if="threads.length === 0" class="empty">
        <text class="empty-icon">✉️</text>
        <text class="empty-title">No messages yet</text>
        <text class="empty-hint">Mutual follows can DM each other.</text>
      </view>
      <view v-for="t in threads" :key="t.thread_id" class="thread-row" @tap="openThread(t)">
        <view class="avatar">{{ (t.other_nickname || 'D').charAt(0) }}</view>
        <view class="thread-info">
          <view class="thread-head">
            <text class="thread-name">{{ t.other_nickname }}</text>
            <text class="thread-time">{{ formatTime(t.last_message_at) }}</text>
          </view>
          <text class="thread-preview">{{ t.last_message_preview || 'Tap to start chatting' }}</text>
        </view>
        <view v-if="t.unread_count > 0" class="badge">{{ t.unread_count }}</view>
      </view>
    </view>

    <!-- Open thread -->
    <view v-else class="thread-view">
      <scroll-view class="msgs" scroll-y :scroll-into-view="scrollTo">
        <view v-for="m in messages" :key="m.id" :id="'m-' + m.id" :class="['bubble', m.sender_user_id === myId ? 'mine' : 'theirs']">
          <text>{{ m.body }}</text>
        </view>
      </scroll-view>
      <view class="composer">
        <input class="input" v-model="draft" placeholder="Type a message..." maxlength="2000" @confirm="onSend" />
        <view class="btn btn-primary" @tap="onSend"><text class="btn-text">Send</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listDMThreads, listDMMessages, sendDM, getMe } from '@/api/dream'

const threads = ref<any[]>([])
const messages = ref<any[]>([])
const currentThread = ref<string>('')
const otherName = ref<string>('')
const draft = ref('')
const myId = ref<string>('')
const scrollTo = ref('')

onLoad(async (q: any) => {
  try { myId.value = (await getMe() as any).id } catch {}
  if (q?.thread) {
    currentThread.value = q.thread
    await loadMessages()
  } else if (q?.to) {
    // Brand-new thread: send a placeholder by composer (don't send anything yet)
    // Just open the composer view; thread will be created on first send.
    currentThread.value = '__new__'
    otherName.value = 'New conversation'
    pendingRecipient.value = q.to
  } else {
    await loadThreads()
  }
})

const pendingRecipient = ref<string>('')

async function loadThreads() {
  try { threads.value = await listDMThreads() || [] } catch {}
}

async function loadMessages() {
  if (!currentThread.value || currentThread.value === '__new__') return
  try {
    messages.value = await listDMMessages(currentThread.value) || []
    const t = threads.value.find(t => t.thread_id === currentThread.value)
    if (t) otherName.value = t.other_nickname
    nextTick(() => {
      if (messages.value.length) scrollTo.value = 'm-' + messages.value[messages.value.length - 1].id
    })
  } catch {}
}

function openThread(t: any) {
  currentThread.value = t.thread_id
  otherName.value = t.other_nickname
  loadMessages()
}

async function onSend() {
  const body = draft.value.trim()
  if (!body) return
  try {
    const recipient = pendingRecipient.value || (threads.value.find(t => t.thread_id === currentThread.value)?.other_user_id)
    if (!recipient) {
      uni.showToast({ title: 'No recipient', icon: 'none' }); return
    }
    const m: any = await sendDM(recipient, body)
    if (currentThread.value === '__new__') currentThread.value = m.thread_id
    draft.value = ''
    await loadMessages()
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Send failed', icon: 'none' })
  }
}

function formatTime(s: string | null) {
  if (!s) return ''
  const d = new Date(s); const diff = (Date.now() - d.getTime()) / 60000
  if (diff < 60) return Math.round(diff) + 'm'
  if (diff < 1440) return Math.round(diff / 60) + 'h'
  return Math.round(diff / 1440) + 'd'
}
function onBack() {
  if (currentThread.value && currentThread.value !== '__new__') {
    currentThread.value = ''; loadThreads()
  } else {
    uni.navigateBack({ delta: 1 })
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); display: flex; flex-direction: column; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-3); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }

.thread-row { display: flex; align-items: center; gap: var(--dream-space-3); padding: var(--dream-space-3) 0; border-bottom: 1rpx solid rgba(255,255,255,0.04); }
.avatar { width: 80rpx; height: 80rpx; border-radius: 50%; background: var(--dream-gradient-aurora); display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: var(--dream-text-md); flex-shrink: 0; }
.thread-info { flex: 1; min-width: 0; }
.thread-head { display: flex; justify-content: space-between; }
.thread-name { color: var(--dream-text-primary); font-size: var(--dream-text-base); font-weight: 500; }
.thread-time { color: var(--dream-text-muted); font-size: 20rpx; }
.thread-preview { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); display: block; margin-top: 4rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { background: var(--dream-error); color: white; font-size: 20rpx; padding: 2rpx 10rpx; border-radius: 9999rpx; font-weight: 600; }

.thread-view { flex: 1; display: flex; flex-direction: column; }
.msgs { flex: 1; height: calc(100vh - 350rpx); padding: 0 8rpx; }
.bubble { max-width: 70%; padding: 12rpx 18rpx; border-radius: 18rpx; margin: 6rpx 0; line-height: 1.5; font-size: var(--dream-text-sm); word-wrap: break-word; }
.bubble.mine { background: var(--dream-primary-600); color: white; align-self: flex-end; margin-left: auto; }
.bubble.theirs { background: var(--dream-bg-card); color: var(--dream-text-primary); }
.composer { display: flex; gap: 8rpx; padding-top: var(--dream-space-2); border-top: 1rpx solid rgba(255,255,255,0.04); }
.input { flex: 1; background: var(--dream-bg-input); border: 1rpx solid var(--dream-border-default); border-radius: var(--dream-radius-md); padding: 12rpx 16rpx; color: var(--dream-text-primary); font-size: var(--dream-text-sm); }
.btn { display: flex; align-items: center; justify-content: center; padding: 0 var(--dream-space-3); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-sm); font-weight: 500; }

.empty { padding: 100rpx 40rpx; text-align: center; }
.empty-icon { font-size: 80rpx; display: block; }
.empty-title { color: var(--dream-text-primary); font-size: var(--dream-text-md); display: block; margin: 16rpx 0 8rpx; }
.empty-hint { color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
</style>
