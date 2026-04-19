<template>
  <view class="page dc-screen">
    <DreamAtmosphere variant="spirited" :star-count="40" pollen />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">wallet</text>
      <view class="back" />
    </view>

    <view class="balance-card">
      <view class="balance-grain dc-grain"></view>
      <text class="balance-label dc-eyebrow">dream coins</text>
      <view class="balance-row">
        <text class="balance-num dc-display">{{ balance }}</text>
        <text class="balance-moon">🌙</text>
      </view>
      <text class="balance-hint dc-narrative">¥1 = 100 coins · 分享、收到反应、邀请好友 都能赚</text>
    </view>

    <text class="section-label">Top up</text>
    <view class="topup-row">
      <view v-for="amt in TOPUP_AMOUNTS" :key="amt" class="topup-btn" @tap="onTopup(amt)">
        <text class="topup-coins">{{ amt }} 🌙</text>
        <text class="topup-price">¥{{ (amt / 100).toFixed(0) }}</text>
      </view>
    </view>

    <text class="section-label">My referral code</text>
    <view class="referral-card" @tap="onCopyCode">
      <text class="referral-code">{{ referralCode }}</text>
      <text class="referral-hint">Tap to copy. Friend gets {{ refReferredReward }} 🌙, you get {{ refReferrerReward }} 🌙 when they sign up.</text>
      <text v-if="referralUseCount > 0" class="referral-count">{{ referralUseCount }} friends joined</text>
    </view>

    <text class="section-label">Recent activity</text>
    <view v-if="history.length === 0" class="empty">No coin activity yet.</view>
    <view v-for="h in history" :key="h.id" class="hist-row">
      <text class="hist-reason">{{ h.reason }}</text>
      <text class="hist-delta" :class="h.delta >= 0 ? 'pos' : 'neg'">{{ h.delta >= 0 ? '+' : '' }}{{ h.delta }}</text>
      <text class="hist-time">{{ formatTime(h.created_at) }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { coinBalance, coinHistory, myReferralCode, createPayment, sandboxCompletePayment } from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const TOPUP_AMOUNTS = [600, 1500, 3000, 6800]  // coins (¥6, ¥15, ¥30, ¥68)
const balance = ref(0)
const history = ref<any[]>([])
const referralCode = ref('—')
const referralUseCount = ref(0)
const refReferredReward = 50
const refReferrerReward = 100

onMounted(async () => { await refresh() })

async function refresh() {
  try { balance.value = (await coinBalance()).balance } catch {}
  try { history.value = await coinHistory(50) || [] } catch {}
  try {
    const r: any = await myReferralCode()
    referralCode.value = r.code
    referralUseCount.value = r.use_count || 0
  } catch {}
}

async function onTopup(coins: number) {
  uni.showLoading({ title: '创建订单...' })
  try {
    // 1 RMB = 100 coins → amount_cents = coins
    const r: any = await createPayment('dream_coins', 'wechat', undefined, coins)
    uni.hideLoading()
    const payload = r.provider_payload || {}
    if (payload.mode === 'sandbox') {
      uni.showModal({
        title: 'Top-up sandbox',
        content: `Confirm ¥${(coins / 100).toFixed(0)} for ${coins} coins?`,
        success: async (res) => {
          if (res.confirm) {
            await sandboxCompletePayment(r.out_trade_no)
            uni.showToast({ title: `+${coins} 🌙`, icon: 'success' })
            await refresh()
          }
        },
      })
    }
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

function onCopyCode() {
  uni.setClipboardData({ data: referralCode.value })
  uni.showToast({ title: 'Code copied', icon: 'none' })
}

function formatTime(s: string) { const d = new Date(s); return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page { min-height: 100vh; padding: 32rpx; padding-top: calc(60rpx + env(safe-area-inset-top, 0)); position: relative; z-index: 1; }
.header, .balance-card, .section-label, .topup-row, .referral-card, .hist-row, .empty { position: relative; z-index: 2; }

.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24rpx; }
.back {
  width: 64rpx; height: 64rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: 36rpx; color: var(--dc-solaris-pearl);
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 50%;
}
.title { display: block; }

.balance-card {
  position: relative;
  background:
    radial-gradient(ellipse 70% 60% at 50% 0%, rgba(249, 160, 63, 0.25), transparent 70%),
    linear-gradient(135deg, var(--dc-spirited-twilight) 0%, var(--dc-spirited-lantern) 120%);
  border: 1rpx solid rgba(249, 210, 110, 0.3);
  border-radius: 32rpx;
  padding: 48rpx 32rpx;
  display: flex; flex-direction: column; align-items: center; gap: 12rpx;
  margin-bottom: 32rpx;
  overflow: hidden;
  box-shadow: 0 16rpx 48rpx rgba(0, 0, 0, 0.4), 0 0 80rpx rgba(249, 160, 63, 0.2);
}
.balance-grain { position: absolute; inset: 0; opacity: 0.08; mix-blend-mode: overlay; pointer-events: none; }
.balance-label { display: block; color: rgba(255, 240, 210, 0.85); }
.balance-row { display: flex; align-items: center; gap: 16rpx; }
.balance-num {
  color: #ffffff;
  font-size: 100rpx;
  line-height: 1;
  background: linear-gradient(180deg, #ffffff 0%, #fef3c7 100%);
  -webkit-background-clip: text;
  background-clip: text;
  text-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.3);
}
.balance-moon { font-size: 64rpx; filter: drop-shadow(0 0 20rpx rgba(255, 230, 180, 0.6)); }
.balance-hint {
  color: rgba(255, 240, 210, 0.85);
  font-size: 24rpx;
  text-align: center;
  line-height: 1.6;
  max-width: 480rpx;
}

.section-label {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  display: block;
  margin: 24rpx 0 16rpx;
  opacity: 0.85;
}

.topup-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14rpx; margin-bottom: 16rpx; }
.topup-btn {
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.6) 0%, rgba(10, 8, 32, 0.75) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  border-radius: 20rpx;
  padding: 24rpx;
  display: flex; flex-direction: column; align-items: center; gap: 6rpx;
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
  transition: all 200ms ease;
}
.topup-btn:active {
  transform: scale(0.97);
  border-color: rgba(167, 139, 250, 0.5);
}
.topup-coins {
  color: var(--dc-solaris-pearl);
  font-family: var(--dc-font-display);
  font-size: 32rpx;
}
.topup-price {
  color: var(--dc-aurora-lavender);
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.15em;
}

.referral-card {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.12) 0%, rgba(20, 10, 54, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 24rpx;
  padding: 32rpx 28rpx;
  display: flex; flex-direction: column; gap: 12rpx;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.referral-code {
  color: var(--dc-solaris-pearl);
  font-size: 48rpx;
  font-weight: 500;
  font-family: var(--dc-font-display);
  letter-spacing: 0.18em;
  text-shadow: 0 0 32rpx rgba(167, 139, 250, 0.4);
}
.referral-hint {
  color: var(--dream-text-secondary);
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 24rpx;
  line-height: 1.6;
}
.referral-count {
  color: var(--dc-spirited-lantern);
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-top: 4rpx;
}

.empty {
  color: var(--dream-text-muted);
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 24rpx;
  padding: 24rpx 0;
}
.hist-row {
  display: flex; align-items: center; gap: 16rpx;
  padding: 18rpx 8rpx;
  border-bottom: 1rpx solid rgba(196, 181, 253, 0.06);
}
.hist-reason {
  flex: 1;
  color: var(--dream-text-secondary);
  font-family: var(--dc-font-narrative);
  font-size: 26rpx;
}
.hist-delta {
  font-family: var(--dc-font-display);
  font-size: 32rpx;
  font-variant-numeric: tabular-nums;
}
.pos { color: var(--dc-aurora-mint); }
.neg { color: #fca5a5; }
.hist-time {
  color: var(--dream-text-muted);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.15em;
}
</style>
