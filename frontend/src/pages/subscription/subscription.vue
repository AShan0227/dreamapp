<template>
  <view class="page dc-screen">
    <DreamAtmosphere variant="inception" :star-count="50" :rays="true" />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">subscription</text>
      <view class="back" />
    </view>

    <!-- Hero — pricing as a film festival programme -->
    <view class="sub-hero">
      <text class="hero-eyebrow dc-eyebrow">choose your seat</text>
      <text class="hero-title dc-display">梦的电影院</text>
      <text class="hero-sub dc-narrative">三种放映等级 · 你的梦,你来定</text>
    </view>

    <view v-if="current" class="current-card">
      <text class="current-label dc-eyebrow">current plan</text>
      <text class="current-tier dc-display" :class="'tier-' + current.tier">{{ current.tier.toUpperCase() }}</text>
      <text class="current-quota">{{ current.video_quota_daily }} videos / day</text>
      <text v-if="current.current_period_end" class="current-renew">renews · {{ formatDate(current.current_period_end) }}</text>
      <view v-if="current.tier !== 'free' && current.status === 'active'" class="cancel-link" @tap="onCancel">
        <text>cancel renewal</text>
      </view>
    </view>

    <text class="section-label dc-eyebrow">all plans</text>
    <view v-for="p in plans" :key="p.tier" class="plan-card" :class="{ 'plan-active': current && p.tier === current.tier, ['plan-' + p.tier]: true }">
      <view class="plan-head">
        <view>
          <text class="plan-eyebrow dc-eyebrow">tier</text>
          <text class="plan-name dc-display" :class="'tier-' + p.tier">{{ p.tier.toUpperCase() }}</text>
        </view>
        <view class="plan-price-block">
          <text class="plan-price">{{ p.monthly_price_cents === 0 ? 'Free' : '¥' + (p.monthly_price_cents / 100) }}</text>
          <text class="plan-price-unit" v-if="p.monthly_price_cents > 0">/月</text>
        </view>
      </view>
      <view class="dc-divider plan-divider"></view>
      <view class="plan-features">
        <view class="feat-row">
          <text class="feat-icon">▸</text>
          <text class="feat">{{ p.video_quota_daily >= 999 ? '不限量' : p.video_quota_daily }} 个视频 / 每天</text>
        </view>
        <view class="feat-row" v-if="p.priority_queue">
          <text class="feat-icon">▸</text>
          <text class="feat">优先排队 · 不用等</text>
        </view>
        <view class="feat-row" v-if="p.premium_styles">
          <text class="feat-icon">▸</text>
          <text class="feat">高级美学 · Tarkovsky / Lynch / Shinkai...</text>
        </view>
        <view class="feat-row" v-if="p.watermark_free_share">
          <text class="feat-icon">▸</text>
          <text class="feat">分享无水印</text>
        </view>
        <view class="feat-row" v-if="p.therapy_credits_monthly > 0">
          <text class="feat-icon">▸</text>
          <text class="feat">{{ p.therapy_credits_monthly }} 次心理咨询 / 月</text>
        </view>
        <view class="feat-row">
          <text class="feat-icon">▸</text>
          <text class="feat">关注上限 {{ p.max_follows >= 99999 ? '不限' : p.max_follows }} 人</text>
        </view>
      </view>
      <view v-if="p.monthly_price_cents > 0 && (!current || p.tier !== current.tier)" class="pay-row">
        <view class="pay-btn pay-wechat" @tap="onPay(p.tier, 'wechat')"><text>微信支付</text></view>
        <view class="pay-btn pay-alipay" @tap="onPay(p.tier, 'alipay')"><text>支付宝</text></view>
        <view class="pay-btn pay-stripe" @tap="onPay(p.tier, 'stripe')"><text>Stripe</text></view>
      </view>
      <text v-else-if="current && p.tier === current.tier" class="active-badge">★ CURRENT</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { mySubscription, listPlans, createPayment, sandboxCompletePayment, cancelSubscription } from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const current = ref<any>(null)
const plans = ref<any[]>([])

onMounted(async () => { await refresh() })

async function refresh() {
  try { current.value = await mySubscription() } catch {}
  try { plans.value = await listPlans() || [] } catch {}
}

async function onPay(tier: string, provider: 'wechat' | 'alipay' | 'stripe') {
  const purpose = `subscription_${tier}`
  uni.showLoading({ title: '创建订单...' })
  try {
    const r: any = await createPayment(purpose, provider)
    uni.hideLoading()
    const payload = r.provider_payload || {}
    if (payload.mode === 'sandbox' && payload.sandbox_complete_url) {
      // Dev: confirm then auto-complete
      uni.showModal({
        title: 'Sandbox payment',
        content: `¥${r.amount_cents / 100} for ${tier}. Complete sandbox payment?`,
        success: async (res) => {
          if (res.confirm) {
            await sandboxCompletePayment(r.out_trade_no)
            uni.showToast({ title: 'Subscribed', icon: 'success' })
            await refresh()
          }
        },
      })
    } else if (payload.redirect_url) {
      // Real: open the payment URL (browser/SDK takes over)
      // #ifdef H5
      window.location.href = payload.redirect_url
      // #endif
    } else {
      uni.showToast({ title: 'Payment created (check wallet)', icon: 'none' })
    }
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

async function onCancel() {
  uni.showModal({
    title: 'Cancel renewal?',
    content: 'Your subscription stays active until the period ends.',
    success: async (res) => {
      if (res.confirm) {
        try {
          await cancelSubscription()
          uni.showToast({ title: 'Renewal cancelled', icon: 'none' })
          await refresh()
        } catch (e: any) {
          uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
        }
      }
    },
  })
}

function formatDate(s: string) { const d = new Date(s); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
function onBack() { uni.navigateBack({ delta: 1 }) }
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 32rpx;
  padding-top: calc(60rpx + env(safe-area-inset-top, 0));
  position: relative;
  z-index: 1;
}
.header, .sub-hero, .current-card, .section-label, .plan-card { position: relative; z-index: 2; }

.header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 24rpx;
}
.back {
  width: 64rpx; height: 64rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: 36rpx;
  color: var(--dc-solaris-pearl);
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 50%;
}
.title { display: block; }

.sub-hero {
  text-align: center;
  padding: 40rpx 0 56rpx;
  display: flex; flex-direction: column; align-items: center; gap: 12rpx;
}
.hero-eyebrow { display: block; }
.hero-title { font-size: 64rpx; line-height: 1.2; display: block; margin: 8rpx 0; }
.hero-sub { font-size: 26rpx; color: var(--dream-text-secondary); display: block; }

.current-card {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.18) 0%, rgba(20, 10, 54, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.3);
  border-radius: 24rpx;
  padding: 32rpx;
  margin-bottom: 32rpx;
  display: flex; flex-direction: column; gap: 8rpx;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  box-shadow: 0 0 48rpx rgba(139, 92, 246, 0.15);
}
.current-label { display: block; opacity: 0.85; }
.current-tier { font-size: 56rpx; line-height: 1.1; display: block; margin: 6rpx 0 8rpx; }
.current-quota { color: var(--dream-text-secondary); font-family: var(--dc-font-narrative); font-size: 26rpx; }
.current-renew {
  color: var(--dream-text-muted);
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  margin-top: 8rpx;
}
.cancel-link {
  margin-top: 12rpx;
  color: #fca5a5;
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.section-label { display: block; margin: 16rpx 0 24rpx; opacity: 0.85; }

/* Plan cards — film festival programme aesthetic */
.plan-card {
  position: relative;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 28rpx;
  padding: 36rpx 32rpx;
  margin-bottom: 24rpx;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  overflow: hidden;
}
.plan-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3rpx;
  background: linear-gradient(180deg, transparent, var(--dc-aurora-lavender), transparent);
}
.plan-active {
  border-color: rgba(167, 139, 250, 0.5);
  box-shadow: 0 0 60rpx rgba(139, 92, 246, 0.18);
}
.plan-premium::before {
  background: linear-gradient(180deg, transparent, var(--dc-spirited-lantern), transparent);
}
.plan-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 8rpx;
}
.plan-eyebrow { display: block; opacity: 0.7; margin-bottom: 4rpx; }
.plan-name {
  font-size: 56rpx;
  line-height: 1;
  display: block;
}
.plan-price-block { display: flex; align-items: baseline; gap: 4rpx; }
.plan-price {
  font-family: var(--dc-font-display);
  font-size: 48rpx;
  color: var(--dc-solaris-pearl);
  letter-spacing: 0.02em;
}
.plan-price-unit {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.15em;
  color: var(--dream-text-muted);
}

.tier-free { color: var(--dream-text-secondary); }
.tier-pro { color: var(--dc-aurora-lavender); }
.tier-premium {
  background: linear-gradient(135deg, var(--dc-spirited-lantern) 0%, var(--dc-aurora-amber) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.plan-divider { margin: 16rpx 0 20rpx; }

.plan-features { display: flex; flex-direction: column; gap: 14rpx; margin-bottom: 28rpx; }
.feat-row { display: flex; gap: 12rpx; align-items: flex-start; }
.feat-icon {
  font-family: var(--dc-font-caption);
  color: var(--dc-aurora-lavender);
  font-size: 22rpx;
  margin-top: 4rpx;
}
.feat {
  color: var(--dream-text-secondary);
  font-family: var(--dc-font-narrative);
  font-size: 28rpx;
  line-height: 1.5;
  flex: 1;
}

.pay-row { display: flex; gap: 12rpx; }
.pay-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 22rpx 12rpx;
  border-radius: 16rpx;
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.15em;
  color: var(--dc-solaris-pearl);
  transition: transform 150ms ease;
}
.pay-btn:active { transform: scale(0.96); }
.pay-wechat {
  background: linear-gradient(135deg, #00b96b 0%, #07c160 100%);
  box-shadow: 0 6rpx 20rpx rgba(7, 193, 96, 0.3);
}
.pay-alipay {
  background: linear-gradient(135deg, #00a0e9 0%, #1677ff 100%);
  box-shadow: 0 6rpx 20rpx rgba(22, 119, 255, 0.3);
}
.pay-stripe {
  background: linear-gradient(135deg, #635bff 0%, #4f46e5 100%);
  box-shadow: 0 6rpx 20rpx rgba(99, 91, 255, 0.3);
}

.active-badge {
  display: block;
  text-align: center;
  margin-top: 12rpx;
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.3em;
  color: var(--dc-spirited-lantern);
}
</style>
