<template>
  <view class="auth-screen dc-screen">
    <!-- First-session cinematic splash -->
    <DreamSplash />

    <!-- Cinematic atmosphere backdrop -->
    <DreamAtmosphere variant="moonrise" :star-count="80" :rays="true" grain-strong />

    <!-- Title marquee — film-title feel, sits above the auth card -->
    <view class="auth-marquee">
      <view class="dc-moon marquee-moon dc-breathe"></view>
      <text class="auth-eyebrow dc-eyebrow">A Cinema of Dreams</text>
      <text class="auth-title dc-display">DreamApp</text>
      <text class="auth-sub">{{ subtitle }}</text>
    </view>

    <view class="auth-card">
      <view class="auth-tabs">
        <view
          v-for="m in modes"
          :key="m.key"
          class="auth-tab"
          :class="{ 'auth-tab-active': mode === m.key }"
          @tap="setMode(m.key)"
        >
          <text>{{ m.label }}</text>
        </view>
      </view>

      <!-- LOGIN / REGISTER (email + password) -->
      <view v-if="mode === 'login' || mode === 'register'" class="auth-form">
        <view v-if="mode === 'register'" class="form-row">
          <text class="form-label">Nickname</text>
          <input class="form-input" v-model="nickname" placeholder="Dreamer" maxlength="30" />
        </view>
        <view class="form-row">
          <text class="form-label">Email</text>
          <input class="form-input" v-model="email" type="text" placeholder="you@example.com" />
        </view>
        <view class="form-row">
          <text class="form-label">Password</text>
          <input class="form-input" v-model="password" :password="true" placeholder="At least 8 characters" />
        </view>
        <view v-if="error" class="form-error">{{ error }}</view>
        <view class="submit-wrap">
          <view class="dc-portal submit-portal" @tap="onSubmit">
            <text class="portal-text">{{ submitLabel }}</text>
          </view>
        </view>
        <view class="form-aux">
          <text class="aux-link" @tap="setMode('forgot')">Forgot password?</text>
        </view>
      </view>

      <!-- PHONE OTP -->
      <view v-if="mode === 'phone'" class="auth-form">
        <view class="form-row">
          <text class="form-label">Phone</text>
          <input class="form-input" v-model="phone" type="number" placeholder="13800000000" />
        </view>
        <view class="form-row">
          <text class="form-label">Code</text>
          <view class="code-row">
            <input class="form-input form-input-flex" v-model="code" type="number" placeholder="6 digits" maxlength="6" />
            <view class="btn-code" :class="{ 'btn-disabled': resendCooldown > 0 }" @tap="onSendOtp">
              <text>{{ resendCooldown > 0 ? resendCooldown + 's' : 'Send code' }}</text>
            </view>
          </view>
        </view>
        <view v-if="error" class="form-error">{{ error }}</view>
        <view class="submit-wrap">
          <view class="dc-portal submit-portal" @tap="onSubmit">
            <text class="portal-text">{{ submitLabel }}</text>
          </view>
        </view>
      </view>

      <!-- FORGOT PASSWORD -->
      <view v-if="mode === 'forgot'" class="auth-form">
        <text class="form-hint">We'll email a reset code if the address is registered.</text>
        <view class="form-row">
          <text class="form-label">Email</text>
          <input class="form-input" v-model="email" type="text" placeholder="you@example.com" />
        </view>
        <view class="form-row">
          <text class="form-label">Reset code</text>
          <view class="code-row">
            <input class="form-input form-input-flex" v-model="code" type="number" placeholder="6 digits" maxlength="6" />
            <view class="btn-code" :class="{ 'btn-disabled': resendCooldown > 0 }" @tap="onRequestReset">
              <text>{{ resendCooldown > 0 ? resendCooldown + 's' : 'Send code' }}</text>
            </view>
          </view>
        </view>
        <view class="form-row">
          <text class="form-label">New password</text>
          <input class="form-input" v-model="password" :password="true" placeholder="At least 8 characters" />
        </view>
        <view v-if="error" class="form-error">{{ error }}</view>
        <view class="submit-wrap">
          <view class="dc-portal submit-portal" @tap="onSubmit">
            <text class="portal-text">Reset &amp; sign in</text>
          </view>
        </view>
      </view>

      <view class="dc-divider"></view>

      <!-- ANONYMOUS SKIP — now as a ghost portal -->
      <view class="auth-skip" @tap="onSkip">
        <text class="skip-link">Enter the dream without an account →</text>
        <text class="skip-hint">You can bind an email later from Profile.</text>
      </view>
    </view>

    <!-- Footer tagline — film credit style -->
    <view class="auth-credit">
      <text class="credit-line">dreams · interpreted · visualized</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'
import DreamSplash from '@/components/DreamSplash.vue'
import {
  loginEmail,
  registerEmail,
  requestPhoneOtp,
  verifyPhoneOtp,
  requestPasswordReset,
  confirmPasswordReset,
  registerUser,
} from '@/api/dream'

type Mode = 'login' | 'register' | 'phone' | 'forgot'

const modes = [
  { key: 'login' as const, label: 'Sign in' },
  { key: 'register' as const, label: 'Register' },
  { key: 'phone' as const, label: 'Phone' },
]

const mode = ref<Mode>('login')
const email = ref('')
const password = ref('')
const phone = ref('')
const code = ref('')
const nickname = ref('')
const error = ref('')
const resendCooldown = ref(0)
let cooldownTimer: any = null

const subtitle = computed(() => ({
  login: '欢迎回到你的梦',
  register: '开始收藏你的梦',
  phone: '用手机号进入',
  forgot: '重置你的密码',
}[mode.value]))

const submitLabel = computed(() => ({
  login: 'Sign in',
  register: 'Create account',
  phone: 'Verify & continue',
  forgot: 'Reset password',
}[mode.value]))

function setMode(m: Mode) {
  mode.value = m
  error.value = ''
}

function startCooldown(seconds: number) {
  resendCooldown.value = seconds
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = setInterval(() => {
    resendCooldown.value -= 1
    if (resendCooldown.value <= 0) {
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

onUnmounted(() => { if (cooldownTimer) clearInterval(cooldownTimer) })

async function onSendOtp() {
  if (resendCooldown.value > 0) return
  if (!phone.value) { error.value = 'Phone required'; return }
  error.value = ''
  try {
    await requestPhoneOtp(phone.value)
    startCooldown(60)
    uni.showToast({ title: 'Code sent', icon: 'none' })
  } catch (e: any) {
    error.value = e?.body?.detail?.message || 'Failed to send code'
  }
}

async function onRequestReset() {
  if (resendCooldown.value > 0) return
  if (!email.value) { error.value = 'Email required'; return }
  error.value = ''
  try {
    await requestPasswordReset(email.value)
    startCooldown(60)
    uni.showToast({ title: 'Code sent (check email)', icon: 'none' })
  } catch (e: any) {
    error.value = e?.body?.detail || 'Failed to send code'
  }
}

async function onSubmit() {
  error.value = ''
  try {
    if (mode.value === 'login') {
      if (!email.value || !password.value) { error.value = 'Email + password required'; return }
      await loginEmail(email.value, password.value)
    } else if (mode.value === 'register') {
      if (!email.value || !password.value) { error.value = 'Email + password required'; return }
      if (password.value.length < 8) { error.value = 'Password must be at least 8 characters'; return }
      await registerEmail(email.value, password.value, nickname.value || 'Dreamer')
    } else if (mode.value === 'phone') {
      if (!phone.value || !code.value) { error.value = 'Phone + code required'; return }
      await verifyPhoneOtp(phone.value, code.value, nickname.value)
    } else if (mode.value === 'forgot') {
      if (!email.value || !code.value || !password.value) { error.value = 'All fields required'; return }
      if (password.value.length < 8) { error.value = 'Password must be at least 8 characters'; return }
      await confirmPasswordReset(email.value, code.value, password.value)
    }
    uni.showToast({ title: 'Welcome', icon: 'none' })
    uni.switchTab({ url: '/pages/index/index' })
  } catch (e: any) {
    const detail = e?.body?.detail
    error.value = typeof detail === 'string' ? detail : (detail?.message || 'Failed — check your input')
  }
}

async function onSkip() {
  try {
    await registerUser('Dreamer')
    uni.switchTab({ url: '/pages/index/index' })
  } catch {
    error.value = 'Could not create anonymous account'
  }
}
</script>

<style lang="scss" scoped>
.auth-screen {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80rpx 40rpx 40rpx;
  position: relative;
  z-index: 1;
}

/* Title marquee */
.auth-marquee {
  position: relative;
  z-index: 2;
  text-align: center;
  margin-bottom: 56rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16rpx;
}
.marquee-moon {
  width: 120rpx;
  height: 120rpx;
  margin-bottom: 8rpx;
}
.auth-eyebrow {
  display: block;
  margin-top: 4rpx;
}
.auth-title {
  font-size: 84rpx;
  line-height: 1.1;
  display: block;
  margin: 8rpx 0 4rpx;
}
.auth-sub {
  font-family: var(--dc-font-narrative);
  font-size: 28rpx;
  color: var(--dream-text-secondary);
  letter-spacing: 0.04em;
  font-style: italic;
  display: block;
}

/* Glass card for the auth form */
.auth-card {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 600rpx;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.72) 0%, rgba(10, 8, 32, 0.82) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  border-radius: 32rpx;
  padding: 48rpx 40rpx;
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  box-shadow:
    0 24rpx 60rpx rgba(0, 0, 0, 0.55),
    0 0 120rpx rgba(139, 92, 246, 0.12),
    inset 0 1rpx 0 rgba(255, 255, 255, 0.06);
}

.auth-tabs {
  display: flex;
  gap: 4rpx;
  background: rgba(10, 8, 32, 0.6);
  border: 1rpx solid rgba(196, 181, 253, 0.1);
  border-radius: 9999px;
  padding: 6rpx;
  margin-bottom: 40rpx;
}
.auth-tab {
  flex: 1;
  text-align: center;
  padding: 14rpx 0;
  border-radius: 9999px;
  color: var(--dream-text-muted);
  font-size: 26rpx;
  letter-spacing: 0.05em;
  transition: all 300ms ease;
}
.auth-tab-active {
  background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
  color: #ffffff;
  box-shadow: 0 4rpx 20rpx rgba(139, 92, 246, 0.35);
}

.auth-form { display: flex; flex-direction: column; gap: 28rpx; }
.form-row { display: flex; flex-direction: column; gap: 10rpx; }
.form-label {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: var(--dc-tracking-caption);
  text-transform: uppercase;
  color: var(--dream-text-secondary);
  opacity: 0.8;
}
.form-input {
  background: rgba(10, 8, 32, 0.55);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 16rpx;
  padding: 24rpx 28rpx;
  color: var(--dream-text-primary);
  font-size: 28rpx;
  transition: all 200ms ease;
}
.form-input:focus {
  border-color: rgba(167, 139, 250, 0.5);
  box-shadow: 0 0 0 4rpx rgba(139, 92, 246, 0.08);
}
.form-input-flex { flex: 1; }
.code-row { display: flex; gap: 12rpx; align-items: stretch; }

.btn-code {
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  padding: 0 28rpx;
  border: 1rpx solid rgba(196, 181, 253, 0.25);
  border-radius: 16rpx;
  background: rgba(45, 27, 94, 0.5);
  color: var(--dream-primary-300);
  font-size: 24rpx;
  letter-spacing: 0.04em;
}
.btn-disabled { opacity: 0.4; pointer-events: none; }

.form-error {
  background: rgba(239, 68, 68, 0.08);
  color: #fca5a5;
  padding: 14rpx 20rpx;
  border-radius: 12rpx;
  font-size: 24rpx;
  border: 1rpx solid rgba(239, 68, 68, 0.2);
}
.form-hint {
  color: var(--dream-text-muted);
  font-size: 24rpx;
  line-height: 1.6;
  font-style: italic;
  font-family: var(--dc-font-narrative);
}

.submit-wrap {
  display: flex;
  justify-content: center;
  margin-top: 12rpx;
}
.submit-portal {
  min-width: unset;
  width: 100%;
  padding: 26rpx 48rpx;
}
.portal-text {
  color: #ffffff;
  font-family: var(--dc-font-display);
  font-size: 30rpx;
  letter-spacing: 0.12em;
  font-weight: 500;
  position: relative;
  z-index: 1;
}

.form-aux { text-align: center; margin-top: 4rpx; }
.aux-link {
  font-size: 24rpx;
  color: var(--dream-primary-300);
  letter-spacing: 0.04em;
}

.auth-skip {
  text-align: center;
  padding: 8rpx 0 4rpx;
}
.skip-link {
  display: block;
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 28rpx;
  color: var(--dc-aurora-lavender);
  margin-bottom: 8rpx;
  letter-spacing: 0.03em;
}
.skip-hint {
  display: block;
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  opacity: 0.6;
}

.auth-credit {
  position: relative;
  z-index: 2;
  margin-top: 48rpx;
  text-align: center;
}
.credit-line {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.4em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  opacity: 0.5;
}
</style>
