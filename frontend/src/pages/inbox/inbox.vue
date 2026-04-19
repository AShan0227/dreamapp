<template>
  <view class="page dc-screen">
    <DreamAtmosphere variant="moonrise" :star-count="40" />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">activity</text>
      <view class="action" @tap="onMarkAll"><text class="action-text">mark all read</text></view>
    </view>

    <view class="hero">
      <text class="hero-title dc-display">收件 · 信号</text>
    </view>

    <view class="seg">
      <view :class="['seg-item', !unreadOnly && 'seg-active']" @tap="setMode(false)"><text>All</text></view>
      <view :class="['seg-item', unreadOnly && 'seg-active']" @tap="setMode(true)"><text>Unread</text></view>
    </view>

    <view v-if="rows.length === 0" class="empty">
      <text class="empty-icon">🔔</text>
      <text class="empty-title dc-display">{{ unreadOnly ? 'All caught up' : 'No signal yet' }}</text>
      <text class="empty-hint dc-narrative">when someone reacts to your dreams, you'll see it here.</text>
    </view>

    <view v-for="n in rows" :key="n.id" class="notif" :class="{ unread: !n.is_read }" @tap="onTap(n)">
      <view class="dot" v-if="!n.is_read" />
      <text class="notif-icon">{{ ICONS[n.kind] || '🌙' }}</text>
      <view class="notif-body">
        <text class="notif-text">
          <text class="actor">{{ n.actor_nickname || 'Someone' }}</text>
          <text class="verb"> {{ verbFor(n.kind) }}</text>
          <text v-if="n.payload?.preview" class="preview"> · "{{ n.payload.preview }}"</text>
        </text>
        <text class="notif-time">{{ formatTime(n.created_at) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listNotifications, markRead } from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const ICONS: Record<string, string> = {
  reaction: '❤️', comment: '💬', reply: '↩️', follow: '👤',
  mention: '@', quote: '🔁', dm: '✉️', pick_of_day: '⭐',
  challenge_win: '🏆', therapist_response: '🧑‍⚕️', system: '🌙',
}

const VERBS: Record<string, string> = {
  reaction: 'reacted to your dream',
  comment: 'commented on your dream',
  reply: 'replied to your comment',
  follow: 'followed you',
  mention: 'mentioned you',
  quote: 'quoted your dream',
  dm: 'sent you a message',
  pick_of_day: 'your dream is dream of the day!',
  challenge_win: 'you won the weekly challenge!',
}
function verbFor(k: string) { return VERBS[k] || k }

const rows = ref<any[]>([])
const unreadOnly = ref(false)

onMounted(async () => { await load() })

async function load() {
  try { rows.value = await listNotifications(unreadOnly.value, 100) || [] } catch {}
}

async function setMode(v: boolean) { unreadOnly.value = v; await load() }

async function onMarkAll() {
  try {
    await markRead()
    uni.showToast({ title: 'All marked read', icon: 'none' })
    await load()
  } catch {}
}

async function onTap(n: any) {
  if (!n.is_read) try { await markRead([n.id]) } catch {}
  // Route to the right place
  if (n.target_kind === 'dream' && n.target_id) {
    uni.navigateTo({ url: `/pages/dream/dream?id=${n.target_id}` })
  } else if (n.target_kind === 'thread' && n.target_id) {
    uni.navigateTo({ url: `/pages/dm/dm?thread=${n.target_id}` })
  } else if (n.kind === 'follow' && n.actor_user_id) {
    uni.navigateTo({ url: `/pages/user/user?id=${n.actor_user_id}` })
  }
}

function formatTime(s: string) { if (!s) return ''; const d = new Date(s); const diff = (Date.now() - d.getTime()) / 60000; if (diff < 1) return 'now'; if (diff < 60) return Math.round(diff) + 'm'; if (diff < 1440) return Math.round(diff / 60) + 'h'; return Math.round(diff / 1440) + 'd' }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; padding: 32rpx; padding-top: calc(60rpx + env(safe-area-inset-top, 0)); position: relative; z-index: 1; }
.header, .hero, .seg, .notif, .empty { position: relative; z-index: 2; }
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
.action {
  padding: 10rpx 20rpx;
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 9999rpx;
}
.action-text {
  color: var(--dc-aurora-lavender);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero { text-align: center; padding: 24rpx 0 32rpx; }
.hero-title { font-size: 56rpx; line-height: 1.1; display: block; }

.seg {
  display: flex;
  gap: 4rpx;
  background: rgba(20, 10, 54, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.12);
  border-radius: 9999rpx;
  padding: 6rpx;
  margin-bottom: 24rpx;
}
.seg-item {
  flex: 1;
  text-align: center;
  padding: 14rpx 0;
  border-radius: 9999rpx;
  color: var(--dream-text-muted);
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.15em;
  text-transform: uppercase;
}
.seg-active {
  background: var(--dc-grad-aurora);
  color: white;
  box-shadow: 0 4rpx 16rpx rgba(139, 92, 246, 0.35);
}

.notif {
  display: flex; align-items: flex-start; gap: 16rpx;
  padding: 22rpx 18rpx;
  border-bottom: 1rpx solid rgba(196, 181, 253, 0.06);
  transition: background 200ms ease;
}
.notif.unread {
  background: linear-gradient(90deg, rgba(139, 92, 246, 0.08) 0%, transparent 60%);
}
.dot {
  width: 12rpx; height: 12rpx;
  background: var(--dc-aurora-lavender);
  border-radius: 50%;
  margin-top: 14rpx;
  box-shadow: 0 0 12rpx var(--dc-aurora-lavender);
  animation: dc-breathe 2.4s ease-in-out infinite;
}
.notif-icon { font-size: 32rpx; flex-shrink: 0; filter: drop-shadow(0 0 8rpx rgba(196, 181, 253, 0.3)); }
.notif-body { flex: 1; }
.notif-text {
  color: var(--dc-solaris-pearl);
  font-family: var(--dc-font-narrative);
  font-size: 26rpx;
  line-height: 1.55;
  display: block;
}
.actor {
  font-weight: 500;
  font-style: normal;
  color: var(--dc-aurora-lavender);
  letter-spacing: 0.02em;
}
.verb { color: var(--dream-text-secondary); }
.preview {
  color: var(--dream-text-muted);
  font-style: italic;
}
.notif-time {
  color: var(--dream-text-muted);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  display: block;
  margin-top: 6rpx;
}

.empty { padding: 120rpx 40rpx; text-align: center; }
.empty-icon { font-size: 96rpx; display: block; opacity: 0.6; margin-bottom: 24rpx; }
.empty-title {
  font-size: 36rpx;
  display: block;
  margin-bottom: 12rpx;
}
.empty-hint {
  color: var(--dream-text-muted);
  font-size: 24rpx;
  font-style: italic;
}
</style>
