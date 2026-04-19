<template>
  <view class="page dc-screen">
    <!-- Crisis overlay — shown when backend returns {crisis: true} -->
    <CrisisOverlay :payload="crisisPayload" @dismiss="onCrisisDismiss" />

    <!-- Cinematic atmosphere — shinkai for the "pre-sleep" / "about to dream" feel -->
    <DreamAtmosphere
      :variant="dreamId || messages.length > 0 ? 'solaris' : 'shinkai'"
      :star-count="100"
      :pollen="!dreamId && messages.length === 0"
      :rays="!dreamId && messages.length === 0"
      grain-strong
    />

    <!-- Orb area (before chat starts) — cinematic invitation -->
    <view class="orb-zone" v-if="!dreamId && messages.length === 0">
      <view class="orb-header">
        <text class="orb-eyebrow dc-eyebrow">dreamapp</text>
        <view v-if="quota" class="quota-chip" :class="quotaSeverityClass" @tap="onProfile">
          <text class="quota-chip-text">{{ quota.remaining }}/{{ quota.daily_cap }}</text>
          <text class="quota-chip-label">videos today</text>
        </view>
      </view>

      <!-- Central orb (existing DreamOrb) wrapped in halo rings -->
      <view class="orb-stage">
        <view class="orb-halo halo-1"></view>
        <view class="orb-halo halo-2"></view>
        <view class="orb-halo halo-3"></view>
        <DreamOrb :isActive="false" />
      </view>

      <text class="orb-prompt dc-display">what did you dream?</text>
      <text class="orb-hint dc-narrative">告诉我 —— 不用连贯,片段也可以</text>

      <!-- Style chips — dream aesthetic selector -->
      <text class="style-label dc-eyebrow">choose the atmosphere</text>
      <scroll-view class="style-scroll" scroll-x>
        <view class="style-list">
          <view v-for="s in styles" :key="s.id" :class="['style-chip', selectedStyle === s.id ? 'style-chip-active' : '']" @tap="selectedStyle = s.id">
            <text class="style-emoji">{{ s.emoji }}</text>
            <text class="style-name">{{ s.name }}</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- Chat mode (with mini orb) -->
    <view class="chat-mode" v-else>
      <!-- Mini orb header -->
      <view class="mini-header">
        <view class="mini-orb-wrap">
          <DreamOrb :isActive="loading" :isListening="isRecording" :isThinking="loading" />
        </view>
        <view class="mini-info">
          <text class="mini-eyebrow dc-eyebrow">in progress</text>
          <text class="mini-title dc-display">Recording a dream</text>
          <text class="mini-round">Round {{ roundNumber }}</text>
        </view>
      </view>

      <!-- Chat messages — cinema bubble treatment -->
      <scroll-view class="chat-scroll" scroll-y :scroll-into-view="scrollTarget" scroll-with-animation>
        <view v-for="(msg, idx) in messages" :key="idx" :class="['bubble', msg.role === 'user' ? 'user' : 'ai']" :id="'msg-' + idx">
          <view v-if="msg.role === 'ai'" class="bubble-eyebrow dc-eyebrow">dreamapp</view>
          <text class="bubble-text" :class="{ 'bubble-text-ai': msg.role === 'ai' }">{{ msg.content }}</text>
        </view>

        <view class="bubble ai" v-if="loading">
          <view class="bubble-eyebrow dc-eyebrow">listening</view>
          <view class="typing-dots">
            <view class="dot d1"></view>
            <view class="dot d2"></view>
            <view class="dot d3"></view>
          </view>
        </view>

        <!-- Complete — cinematic film-reel moment -->
        <view class="complete-zone" v-if="isComplete">
          <view class="complete-card">
            <view class="complete-header">
              <view class="dc-moon complete-moon"></view>
              <text class="complete-eyebrow dc-eyebrow">the dream is yours now</text>
              <text class="complete-title dc-display">梦已收好</text>
              <text class="complete-sub dc-narrative">你可以把它变成一部电影,或者先读懂它</text>
            </view>
            <view class="complete-actions">
              <view class="dc-portal complete-portal" @tap="onGenerate">
                <text class="portal-text">Generate Video</text>
              </view>
              <view class="complete-ghost" @tap="onInterpret">
                <text class="ghost-text">先看解读 →</text>
              </view>
            </view>
            <view class="dc-divider"></view>
            <text class="new-dream-link" @tap="onNewDream">Record another dream</text>
          </view>
        </view>

        <view id="scroll-bottom" style="height: 20rpx;"></view>
      </scroll-view>
    </view>

    <!-- Input bar -->
    <view class="input-bar" v-if="!isComplete">
      <view class="input-row">
        <view class="voice-hold" v-if="isVoiceMode" @touchstart="onVoiceStart" @touchend="onVoiceEnd" @touchcancel="onVoiceEnd">
          <text class="voice-label">{{ isRecording ? '松开发送' : '按住说话' }}</text>
        </view>
        <textarea v-else class="input-field" v-model="inputText" :placeholder="dreamId ? '继续描述...' : '我梦到了...'" :auto-height="true" :maxlength="2000" confirm-type="send" @confirm="onSend" :disabled="loading" />
        <view class="icon-btn" @tap="isVoiceMode = !isVoiceMode">
          <text class="icon-text">{{ isVoiceMode ? '⌨' : '🎙' }}</text>
        </view>
        <view v-if="!isVoiceMode" class="send-btn" :class="{ disabled: !inputText.trim() || loading }" @tap="onSend">
          <text class="send-arrow">↑</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import DreamOrb from '../../components/DreamOrb.vue'
import DreamAtmosphere from '../../components/DreamAtmosphere.vue'
import CrisisOverlay from '../../components/CrisisOverlay.vue'

const crisisPayload = ref<any | null>(null)
function onCrisisDismiss() { crisisPayload.value = null }
import { startDream, chatDream, generateVideo, interpretDream, getMyQuota, getApiHost, getAuthToken } from '../../api/dream'

const dreamId = ref('')
const messages = ref<{ role: string; content: string }[]>([])
const inputText = ref('')
const loading = ref(false)
const isComplete = ref(false)
const roundNumber = ref(0)
const scrollTarget = ref('')
const isVoiceMode = ref(false)
const isRecording = ref(false)
const selectedStyle = ref('surreal')

const styles = [
  { id: 'surreal', name: 'Surreal', emoji: '🌀' },
  { id: 'ethereal', name: 'Ethereal', emoji: '✨' },
  { id: 'noir', name: 'Noir', emoji: '🌑' },
  { id: 'cyberpunk_dream', name: 'Cyber', emoji: '🌃' },
  { id: 'tarkovsky_poetic', name: 'Poetic', emoji: '🎬' },
  { id: 'studio_ghibli_dream', name: 'Ghibli', emoji: '🍃' },
  { id: 'david_lynch_uncanny', name: 'Lynch', emoji: '🚪' },
  { id: 'gothic_romantic', name: 'Gothic', emoji: '🏰' },
]

let recorderManager: any = null

function onVoiceStart() {
  isRecording.value = true
  recorderManager = uni.getRecorderManager()
  recorderManager.onStop((res: any) => { isRecording.value = false; if (res.tempFilePath) uploadVoice(res.tempFilePath) })
  recorderManager.start({ format: 'mp3', duration: 60000 })
}
function onVoiceEnd() { if (recorderManager && isRecording.value) recorderManager.stop(); isRecording.value = false }

function uploadVoice(filePath: string) {
  loading.value = true
  const token = getAuthToken()
  uni.uploadFile({
    url: `${getApiHost()}/api/dreams/voice-to-text`,
    filePath,
    name: 'file',
    header: token ? { Authorization: `Bearer ${token}` } : {},
    success: (res) => { try { const d = JSON.parse(res.data); if (d.text) inputText.value = d.text } catch {} loading.value = false },
    fail: () => { loading.value = false }
  })
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  scrollToBottom()

  try {
    if (!dreamId.value) {
      const res: any = await startDream(text, selectedStyle.value)
      if (res?.crisis) {
        crisisPayload.value = res
        if (res.dream_id) dreamId.value = res.dream_id
        loading.value = false
        return
      }
      dreamId.value = res.dream_id; roundNumber.value = res.round_number
      messages.value.push({ role: 'assistant', content: res.ai_message })
      isComplete.value = res.is_complete
    } else {
      const res: any = await chatDream(dreamId.value, text)
      if (res?.crisis) {
        crisisPayload.value = res
        loading.value = false
        return
      }
      roundNumber.value = res.round_number
      messages.value.push({ role: 'assistant', content: res.ai_message.replace('[DREAM_COMPLETE]', '').trim() })
      isComplete.value = res.is_complete
    }
  } catch { messages.value.push({ role: 'assistant', content: '连接失败，请重试' }) }
  loading.value = false
  scrollToBottom()
}

function scrollToBottom() { nextTick(() => { scrollTarget.value = ''; nextTick(() => { scrollTarget.value = 'scroll-bottom' }) }) }

async function onGenerate() {
  if (!dreamId.value) return
  uni.showLoading({ title: '提交中...' })
  try {
    await generateVideo(dreamId.value)
    uni.hideLoading()
    uni.navigateTo({ url: `/pages/dream/dream?id=${dreamId.value}` })
  } catch (e: any) {
    uni.hideLoading()
    if (e?.code === 429) {
      // Quota exhausted — actionable explanation, route to profile to see status
      uni.showModal({
        title: 'Daily quota reached',
        content: e?.body?.detail || 'You have used today\'s video generations. Resets at UTC midnight.',
        confirmText: 'View quota',
        success: (res) => {
          if (res.confirm) uni.navigateTo({ url: '/pages/profile/profile' })
        },
      })
    } else {
      uni.showToast({ title: e?.body?.detail || '失败', icon: 'none' })
    }
  }
}

async function onInterpret() {
  if (!dreamId.value) return
  uni.showLoading({ title: '解读中...' })
  try { await interpretDream(dreamId.value); uni.hideLoading(); uni.navigateTo({ url: `/pages/dream/dream?id=${dreamId.value}&tab=interpret` }) }
  catch { uni.hideLoading(); uni.showToast({ title: '失败', icon: 'none' }) }
}

function onNewDream() { dreamId.value = ''; messages.value = []; inputText.value = ''; isComplete.value = false; roundNumber.value = 0; selectedStyle.value = 'surreal' }

import { computed as _computed } from 'vue'
const quota = ref<{ daily_cap: number; used_today: number; remaining: number } | null>(null)
const quotaSeverityClass = _computed(() => {
  if (!quota.value) return ''
  if (quota.value.remaining === 0) return 'quota-empty'
  if (quota.value.remaining <= 1) return 'quota-low'
  return ''
})
function onProfile() { uni.navigateTo({ url: '/pages/profile/profile' }) }
async function refreshQuota() { try { quota.value = await getMyQuota() as any } catch {} }
onMounted(() => {
  refreshQuota()
  // Sample-dream seed from the onboarding hero — prefill so new users see
  // the full loop without writing their own dream first.
  try {
    const seed = uni.getStorageSync('sample_dream_seed')
    if (seed && !inputText.value && !dreamId.value) {
      inputText.value = seed
      uni.removeStorageSync('sample_dream_seed')
    }
  } catch {}
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: relative;
  overflow: hidden;
  z-index: 1;
}

.orb-zone, .chat-mode, .input-bar { position: relative; z-index: 2; }

/* ===== Orb Zone — cinematic opening ================================ */
.orb-zone {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 80rpx 40rpx 40rpx;
  gap: 32rpx;
}

.orb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  margin-bottom: 8rpx;
}
.orb-eyebrow {
  opacity: 0.8;
}
.quota-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10rpx 20rpx;
  background: rgba(20, 10, 54, 0.6);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 16rpx;
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
}
.quota-chip-text {
  font-family: var(--dc-font-display);
  color: var(--dc-solaris-pearl);
  font-size: 28rpx;
  line-height: 1;
}
.quota-chip-label {
  font-family: var(--dc-font-caption);
  font-size: 18rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  margin-top: 4rpx;
}
.quota-low {
  background: rgba(249, 160, 63, 0.15);
  border-color: rgba(249, 160, 63, 0.35);
}
.quota-low .quota-chip-text { color: #f9a03f; }
.quota-empty {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.35);
}
.quota-empty .quota-chip-text { color: #fca5a5; }

/* Central orb with layered halos */
.orb-stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 420rpx;
  height: 420rpx;
  margin: 16rpx 0;
}
.orb-halo {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  animation: orb-halo-pulse var(--dc-breath) ease-in-out infinite;
}
.halo-1 {
  inset: 40rpx;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.25), transparent 65%);
  animation-delay: 0s;
}
.halo-2 {
  inset: 0;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.12), transparent 70%);
  animation-delay: 0.6s;
}
.halo-3 {
  inset: -40rpx;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.08), transparent 75%);
  animation-delay: 1.2s;
}
@keyframes orb-halo-pulse {
  0%, 100% { transform: scale(0.9); opacity: 0.7; }
  50%      { transform: scale(1.1); opacity: 1; }
}

.orb-prompt {
  font-size: 64rpx;
  line-height: 1.2;
  text-align: center;
  margin: 8rpx 0 4rpx;
  display: block;
}
.orb-hint {
  font-size: 28rpx;
  color: var(--dream-text-secondary);
  text-align: center;
  display: block;
  margin-bottom: 16rpx;
}

/* Atmosphere selector */
.style-label {
  display: block;
  margin-bottom: 12rpx;
  opacity: 0.8;
}
.style-scroll {
  white-space: nowrap;
  width: 100%;
}
.style-list {
  display: inline-flex;
  gap: 14rpx;
  padding: 4rpx 20rpx 20rpx;
}
.style-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18rpx 24rpx;
  gap: 8rpx;
  min-width: 140rpx;
  border-radius: 20rpx;
  background: linear-gradient(135deg, rgba(20, 10, 54, 0.6) 0%, rgba(10, 8, 32, 0.75) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.12);
  backdrop-filter: blur(12rpx);
  -webkit-backdrop-filter: blur(12rpx);
  transition: all 200ms ease;
}
.style-chip-active {
  border-color: rgba(167, 139, 250, 0.5);
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.25) 0%, rgba(236, 72, 153, 0.15) 100%);
  box-shadow: 0 0 24rpx rgba(139, 92, 246, 0.3);
}
.style-emoji {
  font-size: 40rpx;
  filter: drop-shadow(0 0 8rpx rgba(196, 181, 253, 0.3));
}
.style-name {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--dream-text-secondary);
}
.style-chip-active .style-name { color: var(--dc-solaris-pearl); }

/* ===== Chat Mode =================================================== */
.chat-mode {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mini-header {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 80rpx 40rpx 24rpx;
  background: linear-gradient(180deg, rgba(3, 2, 16, 0.85) 0%, transparent 100%);
  border-bottom: 1rpx solid rgba(196, 181, 253, 0.08);
}
.mini-orb-wrap {
  transform: scale(0.3);
  transform-origin: center;
  width: 84rpx;
  height: 84rpx;
  margin: -40rpx;
}
.mini-info { flex: 1; display: flex; flex-direction: column; gap: 2rpx; }
.mini-eyebrow { display: block; }
.mini-title {
  font-size: 34rpx;
  display: block;
  line-height: 1.2;
}
.mini-round {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  margin-top: 2rpx;
  display: block;
}

.chat-scroll { flex: 1; padding: 24rpx 32rpx; }

.bubble {
  max-width: 82%;
  padding: 22rpx 28rpx;
  margin-bottom: 20rpx;
  word-wrap: break-word;
  position: relative;
}
.bubble.ai {
  background: linear-gradient(135deg, rgba(20, 10, 54, 0.7) 0%, rgba(10, 8, 32, 0.85) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 24rpx 24rpx 24rpx 8rpx;
  margin-right: auto;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.bubble.user {
  background: linear-gradient(135deg, #6d28d9 0%, #8b5cf6 100%);
  border-radius: 24rpx 24rpx 8rpx 24rpx;
  margin-left: auto;
  box-shadow: 0 8rpx 24rpx rgba(109, 40, 217, 0.4);
}

.bubble-eyebrow {
  display: block;
  margin-bottom: 8rpx;
  opacity: 0.7;
}
.bubble-text {
  font-size: 28rpx;
  line-height: 1.7;
  color: var(--dc-solaris-pearl);
  display: block;
}
.bubble-text-ai {
  font-family: var(--dc-font-narrative);
  font-size: 30rpx;
  letter-spacing: 0.01em;
}

/* Typing dots */
.typing-dots { display: flex; gap: 10rpx; padding: 4rpx 0; }
.dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: var(--dc-aurora-lavender);
  box-shadow: 0 0 12rpx var(--dc-aurora-lavender);
  animation: dot-bounce 1.4s ease-in-out infinite;
}
.d1 { animation-delay: 0s; }
.d2 { animation-delay: 0.2s; }
.d3 { animation-delay: 0.4s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== Complete card — cinematic closing credit =================== */
.complete-zone { padding: 24rpx 0 48rpx; }
.complete-card {
  padding: 56rpx 40rpx;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.7) 0%, rgba(10, 8, 32, 0.85) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 32rpx;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  box-shadow: 0 24rpx 60rpx rgba(0, 0, 0, 0.5), 0 0 80rpx rgba(139, 92, 246, 0.12);
}
.complete-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 40rpx;
}
.complete-moon {
  width: 120rpx;
  height: 120rpx;
  margin-bottom: 16rpx;
}
.complete-eyebrow { display: block; }
.complete-title {
  font-size: 56rpx;
  line-height: 1.2;
  display: block;
  margin: 4rpx 0;
}
.complete-sub {
  font-size: 26rpx;
  color: var(--dream-text-secondary);
  line-height: 1.6;
  display: block;
  max-width: 480rpx;
}
.complete-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20rpx;
  width: 100%;
}
.complete-portal {
  min-width: unset;
  width: 100%;
  max-width: 480rpx;
  padding: 26rpx 48rpx;
}
.portal-text {
  color: #ffffff;
  font-family: var(--dc-font-display);
  font-size: 30rpx;
  letter-spacing: 0.1em;
  position: relative;
  z-index: 1;
}
.complete-ghost { padding: 12rpx 24rpx; }
.ghost-text {
  font-family: var(--dc-font-narrative);
  font-style: italic;
  font-size: 26rpx;
  color: var(--dc-aurora-lavender);
  letter-spacing: 0.04em;
}
.new-dream-link {
  font-family: var(--dc-font-caption);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
  opacity: 0.7;
}

/* === Input Bar — water reflection ================================= */
.input-bar {
  padding: 20rpx 32rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, transparent 0%, rgba(3, 2, 16, 0.9) 40%, #030210 100%);
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  border-top: 1rpx solid rgba(196, 181, 253, 0.1);
  position: relative;
}
.input-bar::before {
  /* Reflective water surface — thin horizontal shimmer at top edge */
  content: '';
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1rpx;
  background: linear-gradient(90deg,
    transparent, rgba(196, 181, 253, 0.4), rgba(236, 72, 153, 0.3),
    rgba(6, 182, 212, 0.3), rgba(196, 181, 253, 0.4), transparent);
  animation: dc-breathe var(--dc-breath) ease-in-out infinite;
}

.input-row { display: flex; align-items: flex-end; gap: 12rpx; }

.input-field {
  flex: 1;
  background: rgba(20, 10, 54, 0.55);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 40rpx;
  padding: 24rpx 32rpx;
  color: var(--dc-solaris-pearl);
  font-size: 28rpx;
  max-height: 200rpx;
  min-height: 80rpx;
  transition: all 200ms ease;
  backdrop-filter: blur(10rpx);
  -webkit-backdrop-filter: blur(10rpx);
}
.input-field:focus {
  border-color: rgba(167, 139, 250, 0.5);
  box-shadow: 0 0 0 4rpx rgba(139, 92, 246, 0.1);
}

.voice-hold {
  flex: 1;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(236, 72, 153, 0.15));
  border: 1rpx solid rgba(196, 181, 253, 0.35);
  border-radius: 40rpx;
  padding: 28rpx;
  text-align: center;
}
.voice-label {
  color: var(--dc-aurora-lavender);
  font-family: var(--dc-font-display);
  font-size: 28rpx;
  letter-spacing: 0.06em;
}

.icon-btn {
  width: 80rpx; height: 80rpx;
  background: rgba(20, 10, 54, 0.6);
  border: 1rpx solid rgba(196, 181, 253, 0.2);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

.icon-text { font-size: 32rpx; }

.send-btn {
  width: 80rpx; height: 80rpx;
  background: var(--dc-grad-aurora);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  box-shadow: var(--dc-halo-violet), inset 0 2rpx 0 rgba(255,255,255,0.25);
  transition: all 150ms ease;
}
.send-btn.disabled { opacity: 0.35; filter: grayscale(0.3); }
.send-btn:active { transform: scale(0.92); }
.send-arrow { color: white; font-size: 36rpx; font-weight: 300; line-height: 1; }
</style>
