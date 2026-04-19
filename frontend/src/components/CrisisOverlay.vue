<template>
  <!-- Cinematic, non-interruptive crisis interstitial.
       Shows when the backend returns crisis: true from dream endpoints.
       Designed to feel warm + reach, not clinical + clinical-dismiss. -->
  <view v-if="payload" class="crisis-overlay" @tap.self="onDismiss">
    <view class="crisis-card">
      <view class="crisis-halo dc-breathe"></view>

      <text class="crisis-eyebrow dc-eyebrow">before we keep going</text>
      <text class="crisis-title dc-display">你写的,我看见了</text>

      <text class="crisis-msg dc-narrative">{{ payload.message }}</text>

      <view class="hotlines">
        <view
          v-for="slot in hotlineSlots"
          :key="slot.key"
          class="hotline-card"
          :class="'hotline-' + slot.key"
        >
          <text class="hotline-name">{{ slot.data.name }}</text>
          <text class="hotline-availability">{{ slot.data.available }}</text>
          <view class="hotline-actions">
            <view class="hotline-btn hotline-btn-primary" @tap="callNumber(slot.data.phone)">
              <text class="hotline-btn-text">拨打 · Call</text>
            </view>
            <view class="hotline-btn" @tap="copyNumber(slot.data.phone)">
              <text class="hotline-btn-text">{{ copiedKey === slot.key ? '已复制' : '复制号码' }}</text>
            </view>
          </view>
          <text class="hotline-phone">{{ slot.data.phone }}</text>
        </view>
      </view>

      <text v-if="payload.hotlines?.text" class="hotline-note dc-narrative">
        {{ payload.hotlines.text }}
      </text>

      <view class="crisis-dismiss" @tap="onDismiss">
        <text class="crisis-dismiss-text">我知道了 · 关闭</text>
      </view>

      <text class="crisis-legal">
        DreamApp 不替代专业心理援助 · 你愿意找人说话,随时都好
      </text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface Hotline {
  name: string
  phone: string
  available: string
}
interface HotlineDir {
  primary?: Hotline
  secondary?: Hotline
  text?: string
}
interface CrisisPayload {
  crisis: boolean
  severity: string
  message: string
  hotlines: HotlineDir
  interpretation_paused?: boolean
  dream_id?: string
}

const props = defineProps<{ payload: CrisisPayload | null }>()
const emit = defineEmits<{ (e: 'dismiss'): void }>()

const copiedKey = ref<string | null>(null)

const hotlineSlots = computed(() => {
  if (!props.payload?.hotlines) return []
  const slots: { key: string; data: Hotline }[] = []
  if (props.payload.hotlines.primary) {
    slots.push({ key: 'primary', data: props.payload.hotlines.primary })
  }
  if (props.payload.hotlines.secondary) {
    slots.push({ key: 'secondary', data: props.payload.hotlines.secondary })
  }
  return slots
})

function onDismiss() { emit('dismiss') }

function callNumber(phone: string) {
  const raw = (phone || '').trim()
  if (!raw || !raw.match(/\d/)) {
    copyNumber(phone)
    return
  }
  // #ifdef H5
  try { window.location.href = `tel:${raw.replace(/[^\d+]/g, '')}` } catch {}
  // #endif
  try { (uni as any).makePhoneCall({ phoneNumber: raw.replace(/[^\d+]/g, '') }) } catch {}
}

function copyNumber(phone: string) {
  const raw = (phone || '').trim()
  uni.setClipboardData({
    data: raw,
    success: () => {
      copiedKey.value = 'primary'
      setTimeout(() => { copiedKey.value = null }, 2000)
    },
  })
}
</script>

<style scoped>
.crisis-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: radial-gradient(ellipse at center, rgba(20, 10, 54, 0.78) 0%, rgba(3, 2, 16, 0.94) 70%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48rpx 40rpx;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
}

.crisis-card {
  position: relative;
  width: 100%;
  max-width: 680rpx;
  padding: 60rpx 44rpx;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.82) 0%, rgba(10, 8, 32, 0.92) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.28);
  border-radius: 36rpx;
  box-shadow: 0 40rpx 100rpx rgba(0, 0, 0, 0.6), 0 0 160rpx rgba(139, 92, 246, 0.2);
  display: flex; flex-direction: column; align-items: stretch; gap: 12rpx;
  overflow: hidden;
}

.crisis-halo {
  position: absolute;
  top: -160rpx; left: 50%;
  width: 400rpx; height: 400rpx;
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(249, 160, 63, 0.35) 0%, transparent 65%);
  filter: blur(20rpx);
  pointer-events: none;
  z-index: 0;
}

.crisis-eyebrow, .crisis-title, .crisis-msg, .hotlines, .hotline-note,
.crisis-dismiss, .crisis-legal { position: relative; z-index: 1; }

.crisis-eyebrow { display: block; text-align: center; margin-top: 8rpx; opacity: 0.85; }
.crisis-title {
  font-size: 52rpx;
  line-height: 1.2;
  text-align: center;
  display: block;
  margin: 8rpx 0 24rpx;
}
.crisis-msg {
  font-size: 28rpx;
  line-height: 1.75;
  color: var(--dc-solaris-pearl);
  display: block;
  margin-bottom: 24rpx;
  text-align: left;
}

.hotlines {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  margin: 8rpx 0 16rpx;
}
.hotline-card {
  padding: 24rpx 24rpx 20rpx;
  background: rgba(20, 10, 54, 0.6);
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 24rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.hotline-primary {
  border-color: rgba(249, 160, 63, 0.5);
  background: linear-gradient(135deg, rgba(249, 160, 63, 0.12) 0%, rgba(20, 10, 54, 0.6) 100%);
}
.hotline-name {
  font-family: var(--dc-font-display);
  font-size: 30rpx;
  color: var(--dc-solaris-pearl);
}
.hotline-availability {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  opacity: 0.85;
}
.hotline-actions { display: flex; gap: 12rpx; margin-top: 10rpx; }
.hotline-btn {
  flex: 1;
  display: flex; align-items: center; justify-content: center;
  padding: 18rpx 12rpx;
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 14rpx;
  background: rgba(3, 2, 16, 0.55);
}
.hotline-btn-primary {
  background: var(--dc-grad-aurora);
  border-color: transparent;
  box-shadow: 0 6rpx 18rpx rgba(139, 92, 246, 0.35);
}
.hotline-btn-text {
  color: white;
  font-family: var(--dc-font-display);
  font-size: 26rpx;
  letter-spacing: 0.08em;
}
.hotline-phone {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.2em;
  color: var(--dc-aurora-lavender);
  text-align: right;
  margin-top: 4rpx;
  opacity: 0.8;
}

.hotline-note {
  display: block;
  font-size: 24rpx;
  color: var(--dream-text-secondary);
  text-align: center;
  margin: 8rpx 0 16rpx;
}

.crisis-dismiss {
  align-self: center;
  padding: 16rpx 36rpx;
  margin-top: 8rpx;
}
.crisis-dismiss-text {
  font-family: var(--dc-font-narrative);
  font-size: 26rpx;
  color: var(--dc-aurora-lavender);
  font-style: italic;
}

.crisis-legal {
  display: block;
  text-align: center;
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.12em;
  color: var(--dream-text-muted);
  opacity: 0.55;
  line-height: 1.7;
  margin-top: 16rpx;
}
</style>
