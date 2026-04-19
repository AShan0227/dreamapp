<template>
  <view class="page">
    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title">Therapists</text>
      <view class="back" />
    </view>

    <text class="subtitle">Licensed dream-work therapists. Sessions are billed through DreamApp; we take a 20% platform fee.</text>

    <view class="seg">
      <view :class="['seg-item', mode === 'suggested' && 'seg-active']" @tap="setMode('suggested')"><text>Matched for you</text></view>
      <view :class="['seg-item', mode === 'all' && 'seg-active']" @tap="setMode('all')"><text>Browse all</text></view>
      <view :class="['seg-item', mode === 'mine' && 'seg-active']" @tap="setMode('mine')"><text>My bookings</text></view>
    </view>

    <view v-if="loading"><view v-for="i in 3" :key="i" class="skel" /></view>

    <view v-else-if="mode === 'mine'">
      <view v-if="bookings.length === 0" class="empty">No bookings yet.</view>
      <view v-for="b in bookings" :key="b.id" class="booking-card">
        <view class="booking-head">
          <text class="booking-when">{{ formatDate(b.scheduled_for) }}</text>
          <text class="booking-status" :class="'st-' + b.status">{{ b.status }}</text>
        </view>
        <text class="booking-price">¥{{ (b.price_cents / 100).toFixed(0) }} · {{ b.duration_minutes }}min</text>
      </view>
    </view>

    <view v-else>
      <view v-if="therapists.length === 0" class="empty">No therapists yet — directory is filling.</view>
      <view v-for="t in therapists" :key="t.id" class="ther-card">
        <view class="ther-head">
          <view class="avatar">{{ (t.display_name || 'T').charAt(0) }}</view>
          <view class="ther-info">
            <text class="ther-name">{{ t.display_name }}</text>
            <text class="ther-rate">¥{{ (t.hourly_rate_cents / 100).toFixed(0) }}/hr · {{ t.languages?.join(', ') }}</text>
            <view v-if="t.match_specialties?.length" class="match-tags">
              <text v-for="s in t.match_specialties" :key="s" class="tag tag-match">matches: {{ s }}</text>
            </view>
            <view v-else class="match-tags">
              <text v-for="s in (t.specialties || []).slice(0,3)" :key="s" class="tag">{{ s }}</text>
            </view>
          </view>
        </view>
        <text class="ther-bio" v-if="t.bio">{{ t.bio.slice(0, 200) }}</text>
        <view class="rating-row" v-if="t.rating_avg">
          <text>★ {{ t.rating_avg.toFixed(1) }} ({{ t.rating_count }})</text>
        </view>
        <view class="btn btn-primary" @tap="onBook(t)">
          <text class="btn-text">Book a session</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTherapists, suggestedTherapists, listMyBookings, requestBooking, createPayment, sandboxCompletePayment } from '@/api/dream'

const mode = ref<'suggested' | 'all' | 'mine'>('suggested')
const therapists = ref<any[]>([])
const bookings = ref<any[]>([])
const loading = ref(false)

onMounted(async () => { await load() })

async function setMode(m: typeof mode.value) { mode.value = m; await load() }

async function load() {
  loading.value = true
  try {
    if (mode.value === 'suggested') {
      therapists.value = await suggestedTherapists() || []
    } else if (mode.value === 'all') {
      therapists.value = await listTherapists() || []
    } else {
      bookings.value = await listMyBookings() || []
    }
  } catch {}
  loading.value = false
}

function onBook(t: any) {
  uni.showModal({
    title: `Book ${t.display_name}?`,
    content: `¥${(t.hourly_rate_cents / 100).toFixed(0)}/hr · 50 min session. Tomorrow 20:00.`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        const tomorrow = new Date(Date.now() + 86400000)
        tomorrow.setHours(20, 0, 0, 0)
        const bk: any = await requestBooking(
          t.id, tomorrow.toISOString(), 50, [], '',
        )
        const pay: any = await createPayment('therapy_booking', 'wechat', bk.id)
        const payload = pay.provider_payload || {}
        if (payload.mode === 'sandbox') {
          await sandboxCompletePayment(pay.out_trade_no)
        }
        uni.showToast({ title: 'Booked', icon: 'success' })
        await load()
      } catch (e: any) {
        uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
      }
    },
  })
}

function formatDate(s: string) {
  const d = new Date(s)
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); padding: var(--dream-space-4); padding-top: calc(var(--dream-space-5) + env(safe-area-inset-top, 0)); }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--dream-space-2); }
.back { width: 48rpx; text-align: center; font-size: var(--dream-text-xl); color: var(--dream-text-primary); }
.title { font-size: var(--dream-text-lg); color: var(--dream-text-primary); font-weight: 500; }
.subtitle { color: var(--dream-text-muted); font-size: var(--dream-text-sm); display: block; margin-bottom: var(--dream-space-3); line-height: 1.5; }

.seg { display: flex; gap: var(--dream-space-1); background: var(--dream-bg-input); border-radius: var(--dream-radius-full); padding: 4rpx; margin-bottom: var(--dream-space-3); }
.seg-item { flex: 1; text-align: center; padding: 8rpx 0; border-radius: var(--dream-radius-full); color: var(--dream-text-muted); font-size: var(--dream-text-sm); }
.seg-active { background: var(--dream-gradient-primary); color: white; }

.ther-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-4); margin-bottom: var(--dream-space-2); display: flex; flex-direction: column; gap: var(--dream-space-2); }
.ther-head { display: flex; gap: var(--dream-space-3); align-items: flex-start; }
.avatar { width: 80rpx; height: 80rpx; border-radius: 50%; background: var(--dream-gradient-aurora); display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: var(--dream-text-md); }
.ther-info { flex: 1; }
.ther-name { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 600; display: block; }
.ther-rate { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); display: block; margin-top: 2rpx; }
.match-tags { display: flex; gap: 6rpx; flex-wrap: wrap; margin-top: 6rpx; }
.tag { font-size: 18rpx; padding: 4rpx 10rpx; border-radius: var(--dream-radius-sm); background: var(--dream-bg-input); color: var(--dream-text-accent); }
.tag-match { background: rgba(20,184,166,0.15); color: #5eead4; }
.ther-bio { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); line-height: 1.5; }
.rating-row { color: var(--dream-warning); font-size: var(--dream-text-sm); }

.btn { display: flex; align-items: center; justify-content: center; padding: var(--dream-space-2); border-radius: var(--dream-radius-md); }
.btn-primary { background: var(--dream-gradient-primary); }
.btn-text { color: white; font-size: var(--dream-text-base); font-weight: 500; }

.empty { color: var(--dream-text-muted); font-size: var(--dream-text-sm); padding: var(--dream-space-5); text-align: center; }
.skel { height: 200rpx; background: rgba(255,255,255,0.04); border-radius: var(--dream-radius-lg); margin-bottom: var(--dream-space-2); }

.booking-card { background: var(--dream-glass); border: 1rpx solid var(--dream-glass-border); border-radius: var(--dream-radius-lg); padding: var(--dream-space-3); margin-bottom: var(--dream-space-2); }
.booking-head { display: flex; justify-content: space-between; }
.booking-when { color: var(--dream-text-primary); font-size: var(--dream-text-md); font-weight: 500; }
.booking-status { font-size: 18rpx; padding: 4rpx 8rpx; border-radius: var(--dream-radius-sm); text-transform: uppercase; }
.st-requested { background: rgba(245,158,11,0.15); color: #fbbf24; }
.st-confirmed { background: rgba(16,185,129,0.15); color: #34d399; }
.st-completed { background: rgba(107,114,128,0.15); color: #9ca3af; }
.booking-price { color: var(--dream-text-secondary); font-size: var(--dream-text-sm); display: block; margin-top: 4rpx; }
</style>
