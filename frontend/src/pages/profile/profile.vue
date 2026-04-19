<template>
  <view class="profile-screen dc-screen">
    <DreamAtmosphere variant="moonrise" :star-count="60" />

    <view class="header">
      <view class="back" @tap="onBack">←</view>
      <text class="title dc-eyebrow">profile</text>
      <view class="back" />
    </view>

    <!-- Identity — film credits -->
    <view class="identity-block">
      <view class="avatar-stage">
        <view class="dc-moon avatar-moon dc-breathe"></view>
        <text class="avatar-initial">{{ initial }}</text>
      </view>
      <text class="identity-eyebrow dc-eyebrow">a dreamer</text>
      <text class="nickname dc-display">{{ user?.nickname || 'Dreamer' }}</text>
      <text class="meta" v-if="user?.email">{{ user.email }}</text>
      <text class="meta" v-else-if="user?.phone">{{ user.phone }}</text>
      <text class="meta meta-warn" v-else>anonymous · bind an email below to keep your dreams safe</text>
    </view>

    <!-- Quota -->
    <view class="card">
      <view class="card-header">
        <text class="card-title">Daily video quota</text>
      </view>
      <view class="quota-bar">
        <view class="quota-fill" :style="{ width: quotaFillPct + '%' }" />
      </view>
      <view class="quota-meta">
        <text class="quota-text">{{ quota?.remaining ?? '–' }} of {{ quota?.daily_cap ?? '–' }} remaining</text>
        <text class="quota-text quota-text-muted">Resets at UTC midnight</text>
      </view>
    </view>

    <!-- Bind / change credentials -->
    <view class="card">
      <view class="card-header"><text class="card-title">Account</text></view>

      <view v-if="!user?.email" class="action-block">
        <text class="action-label">Bind email + password</text>
        <input class="form-input" v-model="bindEmailVal" placeholder="you@example.com" />
        <input class="form-input" v-model="bindPasswordVal" :password="true" placeholder="Password (8+ chars)" />
        <view class="btn btn-primary" @tap="onBindEmail"><text class="btn-text">Bind email</text></view>
      </view>
      <view v-else class="action-block">
        <text class="action-label">Change password</text>
        <input class="form-input" v-model="oldPwVal" :password="true" placeholder="Current password" />
        <input class="form-input" v-model="newPwVal" :password="true" placeholder="New password (8+ chars)" />
        <view class="btn btn-secondary" @tap="onChangePassword"><text class="btn-text">Update password</text></view>
      </view>

      <view v-if="!user?.phone" class="action-block">
        <text class="action-label">Bind phone</text>
        <input class="form-input" v-model="bindPhoneVal" type="number" placeholder="13800000000" />
        <view class="code-row">
          <input class="form-input form-input-flex" v-model="bindCodeVal" type="number" placeholder="6-digit code" maxlength="6" />
          <view class="btn btn-secondary code-btn" :class="{ 'btn-disabled': bindCooldown > 0 }" @tap="onSendBindOtp">
            <text class="btn-text">{{ bindCooldown > 0 ? bindCooldown + 's' : 'Send code' }}</text>
          </view>
        </view>
        <view class="btn btn-primary" @tap="onBindPhone"><text class="btn-text">Bind phone</text></view>
      </view>
    </view>

    <!-- Internal tools -->
    <view class="card" @tap="onKnowledge">
      <view class="link-row">
        <text class="link-text">Knowledge base health</text>
        <text class="link-arrow">›</text>
      </view>
    </view>

    <!-- Logout -->
    <view class="card danger" @tap="onLogout">
      <text class="danger-text">Log out</text>
    </view>

    <view v-if="error" class="form-error">{{ error }}</view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  getMe, getMyQuota, bindEmail, bindPhone, requestPhoneOtp, changePassword, logout,
} from '@/api/dream'
import DreamAtmosphere from '@/components/DreamAtmosphere.vue'

const user = ref<any>(null)
const quota = ref<any>(null)
const error = ref('')
const bindEmailVal = ref('')
const bindPasswordVal = ref('')
const bindPhoneVal = ref('')
const bindCodeVal = ref('')
const oldPwVal = ref('')
const newPwVal = ref('')
const bindCooldown = ref(0)
let cooldownTimer: any = null

const initial = computed(() => (user.value?.nickname || 'D').charAt(0).toUpperCase())
const quotaFillPct = computed(() => {
  if (!quota.value || !quota.value.daily_cap) return 0
  return Math.round((quota.value.used_today / quota.value.daily_cap) * 100)
})

onMounted(async () => {
  await refresh()
})

onUnmounted(() => { if (cooldownTimer) clearInterval(cooldownTimer) })

async function refresh() {
  try { user.value = await getMe() } catch (e: any) {
    if (e?.code === 401) { uni.redirectTo({ url: '/pages/auth/auth' }); return }
  }
  try { quota.value = await getMyQuota() } catch {}
}

function startCooldown() {
  bindCooldown.value = 60
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = setInterval(() => {
    bindCooldown.value -= 1
    if (bindCooldown.value <= 0) { clearInterval(cooldownTimer); cooldownTimer = null }
  }, 1000)
}

async function onBindEmail() {
  error.value = ''
  if (!bindEmailVal.value || bindPasswordVal.value.length < 8) {
    error.value = 'Email + 8-char password required'; return
  }
  try {
    await bindEmail(bindEmailVal.value, bindPasswordVal.value)
    bindEmailVal.value = ''; bindPasswordVal.value = ''
    uni.showToast({ title: 'Email bound', icon: 'none' })
    await refresh()
  } catch (e: any) {
    error.value = e?.body?.detail || 'Failed to bind email'
  }
}

async function onChangePassword() {
  error.value = ''
  if (!oldPwVal.value || newPwVal.value.length < 8) {
    error.value = 'Old password + 8-char new password required'; return
  }
  try {
    await changePassword(newPwVal.value, oldPwVal.value)
    oldPwVal.value = ''; newPwVal.value = ''
    uni.showToast({ title: 'Password updated', icon: 'none' })
  } catch (e: any) {
    error.value = e?.body?.detail || 'Failed to change password'
  }
}

async function onSendBindOtp() {
  if (bindCooldown.value > 0) return
  if (!bindPhoneVal.value) { error.value = 'Phone required'; return }
  error.value = ''
  try {
    await requestPhoneOtp(bindPhoneVal.value)
    startCooldown()
    uni.showToast({ title: 'Code sent', icon: 'none' })
  } catch (e: any) {
    error.value = e?.body?.detail?.message || 'Failed to send code'
  }
}

async function onBindPhone() {
  error.value = ''
  if (!bindPhoneVal.value || !bindCodeVal.value) {
    error.value = 'Phone + code required'; return
  }
  try {
    await bindPhone(bindPhoneVal.value, bindCodeVal.value)
    bindPhoneVal.value = ''; bindCodeVal.value = ''
    uni.showToast({ title: 'Phone bound', icon: 'none' })
    await refresh()
  } catch (e: any) {
    error.value = e?.body?.detail || 'Failed to bind phone'
  }
}

async function onLogout() {
  uni.showModal({
    title: 'Log out?',
    content: 'You will need to sign back in to access your dreams. Anonymous accounts cannot be recovered.',
    success: async (res) => {
      if (res.confirm) {
        await logout()
        uni.redirectTo({ url: '/pages/auth/auth' })
      }
    },
  })
}

function onBack() {
  uni.navigateBack({ delta: 1 })
}

function onKnowledge() {
  uni.navigateTo({ url: '/pages/knowledge/knowledge' })
}
</script>

<style lang="scss" scoped>
.profile-screen {
  min-height: 100vh;
  padding: 32rpx;
  padding-top: calc(60rpx + env(safe-area-inset-top, 0));
  position: relative;
  z-index: 1;
}
.header, .identity-block, .card { position: relative; z-index: 2; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32rpx;
}
.back {
  width: 64rpx;
  height: 64rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: 36rpx;
  color: var(--dc-solaris-pearl);
  background: rgba(20, 10, 54, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 50%;
}
.title { display: block; }

/* Identity block — film credits center stage */
.identity-block {
  display: flex; flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 32rpx 0 48rpx;
  gap: 8rpx;
}
.avatar-stage {
  position: relative;
  width: 200rpx;
  height: 200rpx;
  margin-bottom: 24rpx;
  display: flex; align-items: center; justify-content: center;
}
.avatar-moon {
  position: absolute;
  inset: 0;
  width: 200rpx;
  height: 200rpx;
}
.avatar-initial {
  position: relative;
  z-index: 2;
  font-family: var(--dc-font-display);
  font-size: 90rpx;
  font-weight: 500;
  color: var(--dc-solaris-pearl);
  text-shadow: 0 4rpx 24rpx rgba(76, 29, 149, 0.6);
  letter-spacing: 0.04em;
}
.identity-eyebrow { display: block; margin-top: 8rpx; }
.nickname {
  font-size: 64rpx;
  line-height: 1.1;
  display: block;
  margin: 4rpx 0 12rpx;
}
.meta {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 26rpx;
  color: var(--dream-text-secondary);
  letter-spacing: 0.02em;
  display: block;
}
.meta-warn { color: var(--dc-aurora-amber); }

.card {
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 24rpx;
  padding: 32rpx 28rpx;
  margin-bottom: 20rpx;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.card-header { margin-bottom: 20rpx; }
.card-title {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  display: block;
}

.quota-bar {
  height: 14rpx;
  background: rgba(3, 2, 16, 0.6);
  border: 1rpx solid rgba(196, 181, 253, 0.1);
  border-radius: 9999rpx;
  overflow: hidden;
  margin-bottom: 14rpx;
}
.quota-fill {
  height: 100%;
  background: var(--dc-grad-aurora);
  box-shadow: 0 0 12rpx rgba(167, 139, 250, 0.5);
  transition: width 400ms ease;
}
.quota-meta { display: flex; justify-content: space-between; align-items: center; }
.quota-text {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.1em;
  color: var(--dc-solaris-pearl);
}
.quota-text-muted { color: var(--dream-text-muted); text-transform: uppercase; letter-spacing: 0.2em; font-size: 18rpx; }

.action-block {
  display: flex;
  flex-direction: column;
  gap: 14rpx;
  padding-top: 20rpx;
  margin-top: 20rpx;
  border-top: 1rpx solid rgba(196, 181, 253, 0.1);
}
.action-label {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--dream-text-secondary);
  margin-bottom: 8rpx;
}
.form-input {
  background: rgba(3, 2, 16, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  border-radius: 16rpx;
  padding: 20rpx 24rpx;
  color: var(--dc-solaris-pearl);
  font-size: 26rpx;
}
.form-input-flex { flex: 1; }
.code-row { display: flex; gap: 12rpx; align-items: stretch; }
.code-btn {
  white-space: nowrap;
  padding: 0 24rpx;
  display: flex;
  align-items: center;
  background: rgba(45, 27, 94, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 16rpx;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 22rpx 32rpx;
  border-radius: 16rpx;
  transition: transform 150ms ease;
}
.btn:active { transform: scale(0.97); }
.btn-primary {
  background: var(--dc-grad-aurora);
  box-shadow: 0 8rpx 24rpx rgba(139, 92, 246, 0.3);
}
.btn-secondary {
  background: rgba(20, 10, 54, 0.5);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
}
.btn-text {
  color: var(--dc-solaris-pearl);
  font-family: var(--dc-font-display);
  font-size: 26rpx;
  letter-spacing: 0.08em;
}
.btn-disabled { opacity: 0.4; pointer-events: none; }

.danger {
  text-align: center;
  border-color: rgba(239, 68, 68, 0.25);
  background: rgba(45, 12, 12, 0.4);
}
.danger-text {
  color: #fca5a5;
  font-family: var(--dc-font-caption);
  font-size: 24rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.link-row { display: flex; justify-content: space-between; align-items: center; }
.link-text {
  color: var(--dc-solaris-pearl);
  font-family: var(--dc-font-display);
  font-size: 28rpx;
  letter-spacing: 0.04em;
}
.link-arrow { color: var(--dc-aurora-lavender); font-size: 32rpx; }
.link-arrow { color: var(--dream-text-muted); font-size: var(--dream-text-lg); }

.form-error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--dream-error);
  padding: var(--dream-space-2) var(--dream-space-3);
  border-radius: var(--dream-radius-sm);
  font-size: var(--dream-text-sm);
  margin-top: var(--dream-space-3);
  border: 1rpx solid rgba(239, 68, 68, 0.2);
}
</style>
