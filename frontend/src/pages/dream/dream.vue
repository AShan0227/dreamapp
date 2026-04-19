<template>
  <view class="page dc-screen">
    <!-- Cinematic atmosphere (solaris — deep water + pearl, suits interpretive feel) -->
    <DreamAtmosphere variant="solaris" :star-count="40" />

    <!-- Header — film-strip style -->
    <view class="header">
      <view class="header-back" @tap="goBack">
        <text class="back-icon">&#x2190;</text>
      </view>
      <view class="header-title-wrap">
        <text class="header-eyebrow dc-eyebrow">a dream</text>
        <text class="header-title dc-display">{{ dream?.title || '…' }}</text>
      </view>
      <view class="header-actions" v-if="dream">
        <view class="header-action" @tap="onShowEdit"><text class="header-action-icon">&#x270E;</text></view>
        <view class="header-action" @tap="onConfirmDelete"><text class="header-action-icon">&#x1F5D1;</text></view>
      </view>
    </view>

    <!-- Failure banner — surfaces dream.failure_reason when generation failed -->
    <view v-if="dream?.status === 'failed' && dream?.failure_reason" class="failure-banner">
      <text class="failure-icon">&#x26A0;</text>
      <view class="failure-body">
        <text class="failure-title">Generation failed</text>
        <text class="failure-detail">{{ dream.failure_reason }}</text>
      </view>
    </view>

    <!-- Edit modal -->
    <view v-if="editing" class="edit-overlay" @tap.self="editing = false">
      <view class="edit-modal">
        <text class="edit-title">Edit dream</text>
        <text class="edit-label">Title</text>
        <input class="edit-input" v-model="editTitle" maxlength="120" />
        <text class="edit-label">Visual style</text>
        <input class="edit-input" v-model="editStyle" maxlength="40" />
        <view class="edit-actions">
          <view class="btn btn-secondary flex1" @tap="editing = false"><text class="btn-text">Cancel</text></view>
          <view class="btn btn-primary flex1" @tap="onSaveEdit"><text class="btn-text">Save</text></view>
        </view>
      </view>
    </view>

    <!-- Tab Bar -->
    <view class="tabs">
      <view
        :class="['tab', activeTab === 'video' ? 'tab-active' : '']"
        @tap="activeTab = 'video'"
      >
        <text class="tab-text">Video</text>
      </view>
      <view
        :class="['tab', activeTab === 'interpret' ? 'tab-active' : '']"
        @tap="activeTab = 'interpret'"
      >
        <text class="tab-text">Interpret</text>
      </view>
      <view
        :class="['tab', activeTab === 'script' ? 'tab-active' : '']"
        @tap="activeTab = 'script'"
      >
        <text class="tab-text">Script</text>
      </view>
    </view>

    <scroll-view class="content" scroll-y>
      <!-- Video Tab -->
      <view v-if="activeTab === 'video'" class="tab-content">
        <!-- Single film player (auto-concatenated) -->
        <view v-if="filmUrl" class="video-container">
          <video
            :src="filmUrl"
            class="dream-video"
            controls
            autoplay
            object-fit="contain"
          />
        </view>
        <view v-else class="video-placeholder">
          <text class="placeholder-icon">&#x1F3AC;</text>
          <text class="placeholder-text" v-if="dream?.status === 'generating'">
            {{ videoProgress || 'Generating your dream video...' }}
          </text>
          <text class="placeholder-text" v-else-if="dream?.status === 'scripted'">
            Dream captured. Ready to generate video.
          </text>
          <text class="placeholder-text" v-else-if="dream?.status === 'failed'">
            Video generation failed. Try again?
          </text>
          <text class="placeholder-text" v-else>
            Complete the dream interview first.
          </text>
          <view
            v-if="dream?.status === 'scripted' || dream?.status === 'failed'"
            class="btn btn-primary"
            @tap="onGenerate"
          >
            <text class="btn-text">Generate Video</text>
          </view>
        </view>

        <!-- Rewrite button for completed dreams -->
        <view v-if="dream?.video_url" class="rewrite-section">
          <view class="action-row">
            <view class="btn btn-secondary flex1" @tap="onPublish">
              <text class="btn-text">{{ (dream as any)?.is_public ? 'Unpublish' : 'Share to Plaza' }}</text>
            </view>
            <view class="btn btn-secondary flex1" @tap="onShareExternal">
              <text class="btn-text">分享 Share</text>
            </view>
            <view class="btn btn-secondary flex1" @tap="onRewrite">
              <text class="btn-text">Rewrite</text>
            </view>
          </view>
        </view>

        <!-- Reactions strip — only meaningful for published dreams -->
        <view v-if="dream?.video_url && (dream as any)?.is_public" class="reaction-strip">
          <view
            v-for="r in REACTIONS"
            :key="r.kind"
            class="reaction-chip"
            @tap="onReact(r.kind)"
          >
            <text class="reaction-emoji">{{ r.emoji }}</text>
            <text class="reaction-count">{{ reactionCounts[r.kind] || 0 }}</text>
          </view>
        </view>

        <!-- Wave O — Duet block. Only on public dreams (you can't remix a private one) -->
        <view v-if="dream?.video_url && (dream as any)?.is_public" class="duet-block">
          <view class="duet-head">
            <text class="duet-eyebrow dc-eyebrow">remix this dream</text>
            <text class="duet-count" v-if="remixCount > 0">{{ remixCount }} remixes</text>
          </view>
          <view class="duet-row">
            <view class="duet-btn" @tap="onDuet('duet')">
              <text class="duet-emoji">🎬</text>
              <text class="duet-label">Duet</text>
              <text class="duet-hint">side-by-side</text>
            </view>
            <view class="duet-btn" @tap="onDuet('cover')">
              <text class="duet-emoji">🎨</text>
              <text class="duet-label">Cover</text>
              <text class="duet-hint">your aesthetic</text>
            </view>
            <view class="duet-btn" @tap="onDuet('continuation')">
              <text class="duet-emoji">→</text>
              <text class="duet-label">Continue</text>
              <text class="duet-hint">what happens next</text>
            </view>
          </view>
        </view>

        <!-- Video feedback — drives director knowledge Attribution -->
        <view v-if="dream?.video_url" class="feedback-bar">
          <text class="feedback-prompt">How does the video feel?</text>
          <view class="feedback-btns">
            <view
              class="feedback-btn"
              :class="{ 'feedback-active-up': videoFeedback === 'helpful' }"
              @tap="onVideoFeedback(true)"
            >
              <text class="feedback-icon">&#x1F3AC;</text>
              <text class="feedback-label">Cinematic</text>
            </view>
            <view
              class="feedback-btn"
              :class="{ 'feedback-active-down': videoFeedback === 'unhelpful' }"
              @tap="onVideoFeedback(false)"
            >
              <text class="feedback-icon">&#x1F614;</text>
              <text class="feedback-label">Generic</text>
            </view>
          </view>
        </view>

        <!-- Director citations — which cinematic knowledge was used -->
        <view v-if="directorCitations.length" class="meta-section citations-meta">
          <text class="meta-label">Cinematography knowledge ({{ directorCitations.length }})</text>
          <view class="citation-grid">
            <view v-for="c in directorCitations" :key="c.id" class="citation-chip">
              <text class="citation-tier" :class="'tier-' + (c.tier || 'L1')">{{ c.tier || 'L1' }}</text>
              <text class="citation-name">{{ c.name }}</text>
              <text class="citation-source">{{ formatSource(c) }}</text>
              <text v-if="academicMeta(c)" class="citation-academic">{{ academicMeta(c) }}</text>
            </view>
          </view>
        </view>

        <!-- Metadata -->
        <view class="meta-section" v-if="dream">
          <view class="meta-row">
            <text class="meta-label">Style</text>
            <text class="meta-value">{{ dream.video_style }}</text>
          </view>
          <view class="meta-row">
            <text class="meta-label">Recorded</text>
            <text class="meta-value">{{ formatDate(dream.created_at) }}</text>
          </view>
          <view class="meta-row" v-if="dream.emotion_tags.length">
            <text class="meta-label">Emotions</text>
            <view class="tag-row">
              <text v-for="t in dream.emotion_tags" :key="t" class="tag">{{ t }}</text>
            </view>
          </view>
          <view class="meta-row" v-if="dream.symbol_tags.length">
            <text class="meta-label">Symbols</text>
            <view class="tag-row">
              <text v-for="t in dream.symbol_tags" :key="t" class="tag">{{ t }}</text>
            </view>
          </view>
        </view>
      </view>

      <!-- Interpretation Tab -->
      <view v-if="activeTab === 'interpret'" class="tab-content">
        <view v-if="dream?.interpretation" class="interpret-content">

          <!-- IRT proactive banner — surfaces when nightmare detected -->
          <view v-if="nextAction" class="irt-banner" :class="'irt-' + nextAction.kind">
            <text class="irt-icon">{{ nextAction.kind === 'therapist' ? '🧑‍⚕️' : '🌙' }}</text>
            <view class="irt-body">
              <text class="irt-title">
                {{ nextAction.kind === 'therapist' ? 'A licensed therapist might help' : 'This dream looks distressing' }}
              </text>
              <text class="irt-reason">{{ nextAction.reason }}</text>
              <text v-if="nextAction.evidence" class="irt-evidence">{{ nextAction.evidence }}</text>
            </view>
            <view class="irt-cta" @tap="onIrtAction">
              <text>{{ nextAction.kind === 'therapist' ? 'See matches →' : 'Rewrite ending →' }}</text>
            </view>
          </view>

          <!-- Summary -->
          <view class="interpret-section">
            <text class="section-title">Summary</text>
            <text class="section-body">{{ dream.interpretation.summary }}</text>
          </view>

          <!-- Symbols -->
          <view class="interpret-section" v-if="dream.interpretation.symbols?.length">
            <text class="section-title">Symbols</text>
            <view
              v-for="(sym, idx) in dream.interpretation.symbols"
              :key="idx"
              class="symbol-card"
            >
              <text class="symbol-name">{{ sym.symbol }}</text>
              <text class="symbol-meaning">{{ sym.meaning }}</text>
              <text class="symbol-context" v-if="sym.context">{{ sym.context }}</text>
            </view>
          </view>

          <!-- Emotion -->
          <view class="interpret-section" v-if="dream.interpretation.emotion_analysis">
            <text class="section-title">Emotion Analysis</text>
            <text class="section-body">{{ dream.interpretation.emotion_analysis }}</text>
          </view>

          <!-- Psychology -->
          <view class="interpret-section" v-if="dream.interpretation.psychological_lens">
            <text class="section-title">Psychological Lens</text>
            <text class="section-body">{{ dream.interpretation.psychological_lens }}</text>
          </view>

          <!-- Archetype -->
          <view class="interpret-section" v-if="dream.interpretation.narrative_archetype">
            <text class="section-title">Narrative Archetype</text>
            <text class="section-body">{{ dream.interpretation.narrative_archetype }}</text>
          </view>

          <!-- Insight -->
          <view class="interpret-section highlight" v-if="dream.interpretation.life_insight">
            <text class="section-title">Life Insight</text>
            <text class="section-body">{{ dream.interpretation.life_insight }}</text>
          </view>

          <!-- TCM -->
          <view class="interpret-section" v-if="dream.interpretation.tcm_perspective">
            <text class="section-title">TCM Perspective</text>
            <text class="section-body">{{ dream.interpretation.tcm_perspective }}</text>
          </view>

          <!-- Feedback — drives Genesis success/failure counts -->
          <view class="feedback-bar">
            <text class="feedback-prompt">Was this interpretation helpful?</text>
            <view class="feedback-btns">
              <view
                class="feedback-btn"
                :class="{ 'feedback-active-up': userFeedback === 'helpful' }"
                @tap="onFeedback(true)"
              >
                <text class="feedback-icon">&#x1F44D;</text>
                <text class="feedback-label">Helpful</text>
              </view>
              <view
                class="feedback-btn"
                :class="{ 'feedback-active-down': userFeedback === 'unhelpful' }"
                @tap="onFeedback(false)"
              >
                <text class="feedback-icon">&#x1F44E;</text>
                <text class="feedback-label">Off-base</text>
              </view>
            </view>
          </view>

          <!-- Knowledge citations — show which entries drove this interpretation -->
          <view class="interpret-section" v-if="interpretCitations.length">
            <text class="section-title">Knowledge used ({{ interpretCitations.length }})</text>
            <view class="citation-grid">
              <view v-for="c in interpretCitations" :key="c.id" class="citation-chip">
                <text class="citation-tier" :class="'tier-' + (c.tier || 'L1')">{{ c.tier || 'L1' }}</text>
                <text class="citation-name">{{ c.name }}</text>
                <text class="citation-source">{{ formatSource(c) }}</text>
                <text v-if="academicMeta(c)" class="citation-academic">{{ academicMeta(c) }}</text>
              </view>
            </view>
          </view>

          <!-- Comments — only when published. Discussion is the engagement multiplier -->
          <view class="interpret-section" v-if="(dream as any)?.is_public">
            <text class="section-title">Discussion ({{ comments.length }})</text>
            <view v-for="c in comments" :key="c.id" class="comment-row">
              <text class="comment-author">{{ c.nickname }}</text>
              <text class="comment-body">{{ c.body }}</text>
              <text class="comment-time">{{ formatDate(c.created_at) }}</text>
            </view>
            <view class="comment-input-row">
              <input v-model="newComment" class="comment-input" placeholder="Add a comment…" maxlength="1000" />
              <view class="btn btn-primary" :class="{ 'btn-disabled': !newComment.trim() }" @tap="onPostComment">
                <text class="btn-text">Post</text>
              </view>
            </view>
          </view>
        </view>

        <view v-else class="interpret-empty">
          <text class="placeholder-text">No interpretation yet.</text>
          <view
            v-if="dream?.dream_script"
            class="btn btn-primary"
            @tap="onInterpret"
          >
            <text class="btn-text">Interpret Dream</text>
          </view>
        </view>
      </view>

      <!-- Script Tab -->
      <view v-if="activeTab === 'script'" class="tab-content">
        <view v-if="dream?.dream_script" class="script-content">
          <view class="interpret-section">
            <text class="section-title">{{ dream.dream_script.title }}</text>
            <text class="section-body">Overall: {{ dream.dream_script.overall_emotion }}</text>
          </view>

          <view
            v-for="scene in dream.dream_script.scenes"
            :key="scene.scene_number"
            class="scene-card"
          >
            <text class="scene-number">Scene {{ scene.scene_number }}</text>
            <text class="scene-desc">{{ scene.description }}</text>
            <text class="scene-visual">{{ scene.visual_details }}</text>
            <view class="scene-meta">
              <text class="scene-tag" v-if="scene.emotion">{{ scene.emotion }}</text>
              <text class="scene-tag" v-if="scene.camera">{{ scene.camera }}</text>
              <text class="scene-tag" v-if="scene.time_feel">{{ scene.time_feel }}</text>
            </view>
          </view>

          <view class="interpret-section" v-if="dream.dream_script.color_palette?.length">
            <text class="section-title">Color Palette</text>
            <view class="tag-row">
              <text
                v-for="c in dream.dream_script.color_palette"
                :key="c"
                class="tag"
              >{{ c }}</text>
            </view>
          </view>
        </view>
        <view v-else class="interpret-empty">
          <text class="placeholder-text">Complete the interview to see the dream script.</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getDream, generateVideo, interpretDream, checkVideoStatus, rewriteNightmare, getCitations, submitFeedback, deleteDream, updateDream, publishDream, unpublishDream, postComment, listComments, toggleReaction, getReactions, shareCard, startDuet, listRemixesOf, type Dream, type RemixKind } from '../../api/dream'
import DreamAtmosphere from '../../components/DreamAtmosphere.vue'

const dream = ref<Dream | null>(null)
const activeTab = ref('video')
const loading = ref(false)
const videoProgress = ref('')
const currentClip = ref(0)
const citations = ref<any>({})
const userFeedback = ref<'helpful' | 'unhelpful' | ''>('')
const videoFeedback = ref<'helpful' | 'unhelpful' | ''>('')
const editing = ref(false)
const editTitle = ref('')
const editStyle = ref('')

// Wave H state
const REACTIONS = [
  { kind: 'like', emoji: '👍' },
  { kind: 'scary', emoji: '😨' },
  { kind: 'curious', emoji: '🤔' },
  { kind: 'moon', emoji: '🌙' },
  { kind: 'heart', emoji: '❤️' },
  { kind: 'wow', emoji: '😮' },
  { kind: 'sad', emoji: '😢' },
]
const reactionCounts = ref<Record<string, number>>({})
const comments = ref<any[]>([])
const newComment = ref('')
const nextAction = ref<any>(null)  // IRT push payload set by the interpret response
const remixCount = ref(0)          // Wave O — # of remixes of this dream
let dreamId = ''
let pollTimer: any = null

// Wave O — start a remix and navigate to its interview
async function onDuet(kind: RemixKind) {
  if (!dream.value) return
  uni.showLoading({ title: '准备 remix...' })
  try {
    const res = await startDuet(dream.value.id, kind)
    uni.hideLoading()
    uni.navigateTo({ url: `/pages/record/record?dream_id=${res.dream_id}` })
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({
      title: e?.body?.detail || 'Could not start remix',
      icon: 'none',
    })
  }
}

async function loadRemixCount(id: string) {
  try {
    const res = await listRemixesOf(id)
    remixCount.value = res?.count || 0
  } catch { remixCount.value = 0 }
}

const interpretCitations = computed<any[]>(() => citations.value?.stages?.interpreter || [])
const directorCitations = computed<any[]>(() => citations.value?.stages?.director || [])

async function loadCitations() {
  if (!dreamId) return
  try {
    const r = await getCitations(dreamId)
    citations.value = r || {}
    userFeedback.value = r?.feedback?.interpretation || ''
    videoFeedback.value = r?.feedback?.video || ''
  } catch (e) { console.error('citations:', e) }
}

async function onFeedback(helpful: boolean) {
  if (!dreamId) return
  try {
    await submitFeedback(dreamId, 'interpretation', helpful)
    userFeedback.value = helpful ? 'helpful' : 'unhelpful'
    uni.showToast({
      title: helpful ? 'Thanks — learning from this' : 'Noted — adjusting',
      icon: 'none',
    })
  } catch (e) { console.error('feedback:', e) }
}

async function onVideoFeedback(helpful: boolean) {
  if (!dreamId) return
  try {
    await submitFeedback(dreamId, 'video', helpful)
    videoFeedback.value = helpful ? 'helpful' : 'unhelpful'
    uni.showToast({
      title: helpful ? 'Thanks — this style worked' : 'Noted — will adjust',
      icon: 'none',
    })
  } catch (e) { console.error('video feedback:', e) }
}

function onShowEdit() {
  if (!dream.value) return
  editTitle.value = dream.value.title || ''
  editStyle.value = dream.value.video_style || 'surreal'
  editing.value = true
}

async function onSaveEdit() {
  if (!dreamId) return
  try {
    const updated = await updateDream(dreamId, {
      title: editTitle.value,
      video_style: editStyle.value,
    }) as Dream
    dream.value = updated
    editing.value = false
    uni.showToast({ title: 'Saved', icon: 'none' })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Save failed', icon: 'none' })
  }
}

async function refreshSocial() {
  if (!dreamId) return
  try { reactionCounts.value = await getReactions(dreamId) || {} } catch {}
  try { comments.value = await listComments(dreamId) || [] } catch {}
}

async function onReact(kind: string) {
  try {
    const r: any = await toggleReaction(dreamId, kind)
    reactionCounts.value = r.counts || {}
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

async function onPostComment() {
  if (!newComment.value.trim()) return
  try {
    await postComment(dreamId, newComment.value)
    newComment.value = ''
    comments.value = await listComments(dreamId) || []
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}

async function onShareExternal() {
  try {
    const card: any = await shareCard(dreamId)
    uni.setClipboardData({ data: card.url || '', success: () => {} })
    uni.showModal({
      title: 'Shared 🌙',
      content: `${card.share_text_zh}\n\n${card.url}\n\nLink copied. Paste into WeChat / Douyin / Xiaohongshu.`,
      showCancel: false,
    })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Share failed', icon: 'none' })
  }
}

function onIrtAction() {
  if (!nextAction.value) return
  if (nextAction.value.kind === 'therapist') {
    uni.navigateTo({ url: '/pages/therapists/therapists' })
  } else {
    onRewrite()
  }
}

function onConfirmDelete() {
  if (!dreamId) return
  uni.showModal({
    title: 'Delete this dream?',
    content: 'This cannot be undone. The dream will be removed from your archive and from the plaza.',
    confirmText: 'Delete',
    confirmColor: '#ef4444',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteDream(dreamId)
        uni.showToast({ title: 'Deleted', icon: 'none' })
        setTimeout(() => uni.navigateBack({ delta: 1 }), 500)
      } catch (e: any) {
        uni.showToast({ title: e?.body?.detail || 'Delete failed', icon: 'none' })
      }
    },
  })
}

// Film URL: prefer concatenated single file, fallback to first clip
const filmUrl = computed(() => {
  if (!dream.value) return ''
  const url = dream.value.video_url || ''

  // Concatenated film — rewrite localhost:8000 to relative path for Nginx proxy
  if (url.includes('/videos/')) {
    const path = url.replace(/^https?:\/\/[^/]+/, '')  // strip host, keep /videos/...
    return path
  }

  // Fallback to first remote clip (Kling CDN URL)
  const urls = (dream.value as any).video_urls
  if (urls && Array.isArray(urls) && urls.length > 0) return urls[0]
  if (url) return url
  return ''
})

onLoad((query) => {
  dreamId = query?.id || ''
  if (query?.tab) activeTab.value = query.tab
})

onMounted(async () => {
  if (!dreamId) return
  try {
    dream.value = await getDream(dreamId)
    // Auto-start polling if video is generating
    if (dream.value?.status === 'generating') {
      startVideoPolling()
    }
    loadCitations()
    refreshSocial()
    if ((dream.value as any)?.is_public) loadRemixCount(dreamId)
  } catch (err) {
    uni.showToast({ title: 'Failed to load dream', icon: 'none' })
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

function startVideoPolling() {
  videoProgress.value = 'Generating your dream video...'
  pollTimer = setInterval(async () => {
    try {
      const res = await checkVideoStatus(dreamId)
      const total = res.total_shots || 0
      const done = res.completed_shots || 0

      if (total > 0) {
        videoProgress.value = `Rendering shot ${done}/${total}...`
      }

      if (res.status === 'completed') {
        clearInterval(pollTimer)
        pollTimer = null
        videoProgress.value = ''
        dream.value = await getDream(dreamId)
      } else if (res.status === 'failed') {
        clearInterval(pollTimer)
        pollTimer = null
        videoProgress.value = 'Video generation failed'
        dream.value = await getDream(dreamId)
      }
    } catch (err) {
      // Keep polling on error
    }
  }, 5000)
}

function goBack() {
  uni.navigateBack()
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// Friendlier source label for the citation chip — papers/cultural get
// proper display names instead of raw column values.
function formatSource(c: any): string {
  const map: Record<string, string> = {
    papers: 'RESEARCH',
    cultural: 'CULTURAL',
    corpus: 'REAL DREAM',
    symbols: 'SYMBOL',
    archetypes: 'ARCHETYPE',
    narratives: 'NARRATIVE',
    tcm: 'TCM',
    dreamcore: 'DREAMCORE',
    film_techniques: 'FILM TECHNIQUE',
    prompt_styles: 'STYLE',
    emotion_visual: 'EMOTION → VISUAL',
    incubation: 'INCUBATION',
  }
  return map[c.source] || (c.source || '').toUpperCase()
}

// Surface academic provenance under the chip when meaningful:
// - papers → "Authors (year), Journal"
// - cultural → "Culture · Era"
// - corpus → "From DreamBank / Reddit corpus"
function academicMeta(c: any): string {
  const m = c.metadata || {}
  if (c.source === 'papers') {
    const authorList = Array.isArray(m.authors) ? m.authors : []
    const lead = authorList[0] || ''
    const etAl = authorList.length > 1 ? ' et al.' : ''
    const year = m.year ? ` (${m.year})` : ''
    const journal = m.journal ? ` — ${m.journal}` : ''
    if (!lead) return ''
    return `${lead}${etAl}${year}${journal}`
  }
  if (c.source === 'cultural' && m.culture) {
    return m.era ? `${m.culture} · ${m.era}` : String(m.culture)
  }
  if (c.source === 'corpus') {
    return 'Real dream corpus (DreamBank / Reddit)'
  }
  return ''
}

async function onGenerate() {
  if (!dreamId || loading.value) return
  loading.value = true
  uni.showLoading({ title: 'Submitting to AI Director...' })

  try {
    await generateVideo(dreamId)
    uni.hideLoading()
    dream.value = await getDream(dreamId)
    startVideoPolling()
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Generation failed', icon: 'none' })
  }
  loading.value = false
}

async function onInterpret() {
  if (!dreamId || loading.value) return
  loading.value = true
  uni.showLoading({ title: 'Interpreting...' })

  try {
    const r: any = await interpretDream(dreamId)
    // Backend returns { dream_id, interpretation, next_action } — capture
    // the IRT push so the banner renders immediately.
    nextAction.value = r?.next_action || null
    dream.value = await getDream(dreamId)
    loadCitations()
    refreshSocial()
    uni.hideLoading()
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Interpretation failed', icon: 'none' })
  }
  loading.value = false
}

async function onRewrite() {
  if (!dreamId || loading.value) return
  loading.value = true
  uni.showLoading({ title: 'Rewriting dream ending...' })

  try {
    const res = await rewriteNightmare(dreamId)
    uni.hideLoading()
    if (res.rewritten_script) {
      uni.showModal({
        title: 'Dream Rewritten',
        content: `New title: ${res.rewritten_script.title || 'Healed Dream'}. Generate video with the new ending?`,
        confirmText: 'Generate',
        cancelText: 'Later',
        success: (modalRes) => {
          if (modalRes.confirm) {
            onGenerate()
          }
        }
      })
    }
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Rewrite failed', icon: 'none' })
  }
  loading.value = false
}

async function onPublish() {
  if (!dreamId) return
  const isPublic = (dream.value as any)?.is_public
  try {
    if (isPublic) await unpublishDream(dreamId); else await publishDream(dreamId)
    dream.value = await getDream(dreamId)
    uni.showToast({ title: isPublic ? 'Removed from Plaza' : 'Published to Plaza!', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.body?.detail || 'Failed', icon: 'none' })
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  position: relative;
  z-index: 1;
}
.header, .tabs, .content { position: relative; z-index: 2; }

.header {
  display: flex;
  align-items: flex-end;
  padding: 80rpx 32rpx 24rpx;
  gap: 16rpx;
  background: linear-gradient(180deg, rgba(3, 2, 16, 0.9) 0%, rgba(3, 2, 16, 0.6) 60%, transparent 100%);
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
}
.header-title-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
  min-width: 0;
}
.header-eyebrow { display: block; opacity: 0.7; }

.header-actions {
  display: flex;
  gap: 12rpx;
}
.header-action {
  width: 60rpx;
  height: 60rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.05);
  border-radius: 50%;
}
.header-action-icon { color: #fff; font-size: 30rpx; }

.failure-banner {
  display: flex;
  gap: 16rpx;
  margin: 16rpx 30rpx 0;
  padding: 20rpx 24rpx;
  background: rgba(239, 68, 68, 0.1);
  border: 1rpx solid rgba(239, 68, 68, 0.3);
  border-radius: 16rpx;
}
.failure-icon { color: #ef4444; font-size: 36rpx; }
.failure-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.failure-title { color: #ef4444; font-weight: 600; font-size: 28rpx; }
.failure-detail { color: #fda5a5; font-size: 24rpx; line-height: 1.4; }

.edit-overlay {
  position: fixed;
  inset: 0;
  background: rgba(6,6,18,0.85);
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 30rpx;
}
.edit-modal {
  width: 100%;
  max-width: 580rpx;
  background: #12122a;
  border: 1rpx solid rgba(139,92,246,0.2);
  border-radius: 24rpx;
  padding: 32rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}
.edit-title {
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
  margin-bottom: 8rpx;
}
.edit-label {
  color: #a0a0b8;
  font-size: 24rpx;
}
.edit-input {
  background: #1e1e3a;
  border: 1rpx solid rgba(255,255,255,0.1);
  border-radius: 16rpx;
  padding: 18rpx 20rpx;
  color: #fff;
  font-size: 28rpx;
}
.edit-actions { display: flex; gap: 16rpx; margin-top: 12rpx; }

.header-back {
  width: 60rpx;
  height: 60rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.back-icon {
  color: #fff;
  font-size: 40rpx;
}

.header-title {
  font-size: 40rpx;
  line-height: 1.2;
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* Tabs — film-strip indicator */
.tabs {
  display: flex;
  padding: 0 32rpx;
  background: rgba(3, 2, 16, 0.6);
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  border-bottom: 1rpx solid rgba(196, 181, 253, 0.1);
}
.tab {
  flex: 1;
  padding: 28rpx 0 24rpx;
  text-align: center;
  position: relative;
  transition: all 200ms ease;
}
.tab-active::after {
  content: '';
  position: absolute;
  left: 30%;
  right: 30%;
  bottom: 0;
  height: 3rpx;
  background: var(--dc-grad-aurora);
  box-shadow: 0 0 12rpx rgba(167, 139, 250, 0.6);
  border-radius: 2rpx;
}
.tab-text {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--dream-text-muted);
}
.tab-active .tab-text {
  color: var(--dc-solaris-pearl);
}

/* Content */
.content {
  height: calc(100vh - 260rpx);
}

.tab-content {
  padding: 30rpx;
}

/* Video */
.video-container {
  border-radius: 20rpx;
  overflow: hidden;
  margin-bottom: 30rpx;
}

.dream-video {
  width: 100%;
  height: 420rpx;
}

.clip-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12rpx;
  padding: 16rpx 0;
  background: #12122a;
}

.clip-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #3b3b5c;
}

.clip-dot-active {
  background: #8b5cf6;
  width: 20rpx;
  height: 20rpx;
}

.clip-label {
  font-size: 22rpx;
  color: #8b8ba0;
  margin-left: 12rpx;
}

.video-placeholder {
  height: 420rpx;
  background: #12122a;
  border-radius: 20rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20rpx;
  margin-bottom: 30rpx;
}

.placeholder-icon {
  font-size: 80rpx;
}

.placeholder-text {
  color: #8b8ba0;
  font-size: 28rpx;
  text-align: center;
}

/* Meta */
.meta-section {
  background: #12122a;
  border-radius: 20rpx;
  padding: 24rpx 28rpx;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1px solid #1e1e3a;
}

.meta-row:last-child {
  border-bottom: none;
}

.meta-label {
  color: #8b8ba0;
  font-size: 26rpx;
}

.meta-value {
  color: #e0e0e0;
  font-size: 26rpx;
}

.tag-row {
  display: flex;
  gap: 10rpx;
  flex-wrap: wrap;
}

.tag {
  background: #1e1e3a;
  color: #8b5cf6;
  font-size: 22rpx;
  padding: 6rpx 16rpx;
  border-radius: 8rpx;
}

/* Buttons */
.btn {
  padding: 28rpx;
  border-radius: 20rpx;
  text-align: center;
  margin-top: 20rpx;
}

.btn-primary {
  background: linear-gradient(135deg, #7c3aed, #5b21b6);
}

.btn-secondary {
  background: #1e1e3a;
  border: 1px solid #3b3b5c;
}

.btn-text {
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
}

.rewrite-section {
  padding: 20rpx 0;
}

.action-row {
  display: flex;
  gap: 16rpx;
}

.flex1 {
  flex: 1;
}

/* Interpretation — editorial / film-magazine feel */
.interpret-content {
  display: flex;
  flex-direction: column;
  gap: 32rpx;
  padding-top: 16rpx;
}

.interpret-section {
  position: relative;
  background: linear-gradient(180deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 24rpx;
  padding: 36rpx 32rpx;
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  overflow: hidden;
}
.interpret-section::before {
  /* left film-strip accent */
  content: '';
  position: absolute;
  left: 0; top: 16rpx; bottom: 16rpx;
  width: 2rpx;
  background: linear-gradient(180deg, transparent, var(--dc-aurora-lavender), transparent);
  opacity: 0.6;
}

.interpret-section.highlight {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(236, 72, 153, 0.08) 100%);
  border-color: rgba(167, 139, 250, 0.4);
  box-shadow: 0 0 48rpx rgba(139, 92, 246, 0.15);
}

.section-title {
  font-family: var(--dc-font-caption);
  font-size: 22rpx;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: var(--dc-aurora-lavender);
  display: block;
  margin-bottom: 20rpx;
  opacity: 0.85;
}

.section-body {
  font-family: var(--dc-font-narrative);
  font-size: 30rpx;
  color: var(--dc-solaris-pearl);
  line-height: 1.85;
  letter-spacing: 0.01em;
  display: block;
}

.symbol-card {
  background: rgba(3, 2, 16, 0.55);
  border: 1rpx solid rgba(196, 181, 253, 0.12);
  border-radius: 20rpx;
  padding: 24rpx 28rpx;
  margin-bottom: 16rpx;
  position: relative;
}
.symbol-card::before {
  /* decorative diamond bullet like ◈ */
  content: '◈';
  position: absolute;
  top: 24rpx;
  left: -12rpx;
  color: var(--dc-aurora-lavender);
  background: var(--dream-bg-primary);
  padding: 0 4rpx;
  font-size: 18rpx;
  opacity: 0.7;
}

.symbol-name {
  font-family: var(--dc-font-display);
  font-size: 32rpx;
  font-weight: 500;
  color: var(--dc-solaris-pearl);
  letter-spacing: 0.04em;
  display: block;
  margin-bottom: 10rpx;
}

.symbol-meaning {
  font-family: var(--dc-font-narrative);
  font-size: 28rpx;
  color: var(--dream-text-secondary);
  line-height: 1.7;
  display: block;
}

.symbol-context {
  font-size: 24rpx;
  color: #8b8ba0;
  margin-top: 8rpx;
  font-style: italic;
  display: block;
}

/* Script */
.script-content {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}

.scene-card {
  background: #12122a;
  border-radius: 20rpx;
  padding: 28rpx;
  border-left: 4rpx solid #5b21b6;
}

.scene-number {
  font-size: 24rpx;
  color: #8b5cf6;
  font-weight: 700;
  display: block;
  margin-bottom: 12rpx;
}

.scene-desc {
  font-size: 28rpx;
  color: #e0e0e0;
  line-height: 1.6;
  display: block;
  margin-bottom: 12rpx;
}

.scene-visual {
  font-size: 26rpx;
  color: #8b8ba0;
  line-height: 1.5;
  display: block;
  margin-bottom: 12rpx;
}

.scene-meta {
  display: flex;
  gap: 10rpx;
  flex-wrap: wrap;
}

.scene-tag {
  background: #1e1e3a;
  color: #c4b5fd;
  font-size: 22rpx;
  padding: 6rpx 14rpx;
  border-radius: 8rpx;
}

.interpret-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400rpx;
  gap: 20rpx;
}

/* Feedback bar */
.feedback-bar {
  margin-top: 32rpx;
  padding: 24rpx;
  background: rgba(139, 92, 246, 0.08);
  border-radius: 20rpx;
  border: 1px solid rgba(139, 92, 246, 0.2);
}
.feedback-prompt {
  display: block;
  font-size: 26rpx;
  color: var(--dream-text-secondary);
  margin-bottom: 16rpx;
}
.feedback-btns {
  display: flex;
  gap: 16rpx;
}
.feedback-btn {
  flex: 1;
  padding: 18rpx 12rpx;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  transition: all 0.2s;
}
.feedback-icon { font-size: 32rpx; }
.feedback-label { font-size: 26rpx; color: var(--dream-text-primary); }
.feedback-active-up {
  background: rgba(34, 197, 94, 0.22);
  border-color: rgba(34, 197, 94, 0.5);
}
.feedback-active-down {
  background: rgba(239, 68, 68, 0.22);
  border-color: rgba(239, 68, 68, 0.5);
}

/* Citation chips */
.citation-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 12rpx;
}
.citation-chip {
  padding: 10rpx 16rpx;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14rpx;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
  min-width: 180rpx;
}
.citation-tier {
  font-size: 20rpx;
  font-weight: 700;
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  align-self: flex-start;
}
.citation-tier.tier-L0 { background: rgba(100,150,255,0.25); color: #9bb8ff; }
.citation-tier.tier-L1 { background: rgba(139,92,246,0.25); color: #c4b3ff; }
.citation-tier.tier-L2 { background: rgba(255,180,100,0.2); color: #ffc89b; }
.citation-name { font-size: 24rpx; color: var(--dream-text-primary); font-weight: 600; }
.citation-source { font-size: 20rpx; color: var(--dream-text-muted); text-transform: uppercase; letter-spacing: 0.5rpx; }
.citation-academic {
  font-size: 20rpx;
  color: var(--dream-text-secondary);
  font-style: italic;
  margin-top: 4rpx;
  display: block;
}

/* Wave H UI */
.reaction-strip {
  display: flex;
  gap: 12rpx;
  flex-wrap: wrap;
  padding: 0 30rpx;
  margin-top: 20rpx;
}
.reaction-chip {
  display: flex;
  align-items: center;
  gap: 6rpx;
  background: rgba(255,255,255,0.04);
  border: 1rpx solid rgba(255,255,255,0.08);
  border-radius: 9999rpx;
  padding: 6rpx 14rpx;
}
.reaction-emoji { font-size: 28rpx; }
.reaction-count { color: #c4b5fd; font-size: 20rpx; font-variant-numeric: tabular-nums; }

/* Wave O — Duet block */
.duet-block {
  margin: 32rpx 30rpx 0;
  padding: 28rpx 28rpx 24rpx;
  background: linear-gradient(135deg, rgba(20, 10, 54, 0.55) 0%, rgba(10, 8, 32, 0.7) 100%);
  border: 1rpx solid rgba(196, 181, 253, 0.18);
  border-radius: 24rpx;
  backdrop-filter: blur(16rpx);
  -webkit-backdrop-filter: blur(16rpx);
}
.duet-head {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 16rpx;
}
.duet-eyebrow { display: block; opacity: 0.85; }
.duet-count {
  font-family: var(--dc-font-caption, monospace);
  font-size: 20rpx;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(196, 181, 253, 0.85);
}
.duet-row {
  display: flex; gap: 12rpx;
}
.duet-btn {
  flex: 1;
  display: flex; flex-direction: column; align-items: center;
  gap: 4rpx;
  padding: 18rpx 12rpx;
  background: rgba(45, 27, 94, 0.4);
  border: 1rpx solid rgba(196, 181, 253, 0.15);
  border-radius: 18rpx;
  transition: all 200ms ease;
}
.duet-btn:active {
  transform: scale(0.97);
  border-color: rgba(167, 139, 250, 0.5);
  background: rgba(45, 27, 94, 0.6);
}
.duet-emoji {
  font-size: 36rpx;
  filter: drop-shadow(0 0 8rpx rgba(196, 181, 253, 0.3));
}
.duet-label {
  font-family: var(--dc-font-display, serif);
  font-size: 26rpx;
  color: #f8f4ff;
  letter-spacing: 0.04em;
}
.duet-hint {
  font-family: var(--dc-font-caption, monospace);
  font-size: 16rpx;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(196, 181, 253, 0.6);
}

.irt-banner {
  display: flex;
  gap: 16rpx;
  background: rgba(239, 68, 68, 0.08);
  border: 1rpx solid rgba(239, 68, 68, 0.25);
  border-radius: 16rpx;
  padding: 20rpx;
  margin-bottom: 20rpx;
  align-items: flex-start;
}
.irt-banner.irt-therapist { background: rgba(20, 184, 166, 0.08); border-color: rgba(20, 184, 166, 0.25); }
.irt-icon { font-size: 40rpx; }
.irt-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.irt-title { color: #fff; font-size: 28rpx; font-weight: 600; }
.irt-reason { color: #fecaca; font-size: 24rpx; line-height: 1.4; }
.irt-evidence { color: #a0a0b8; font-size: 20rpx; font-style: italic; margin-top: 4rpx; }
.irt-cta { background: #8b5cf6; color: #fff; padding: 8rpx 16rpx; border-radius: 8rpx; font-size: 22rpx; align-self: center; white-space: nowrap; }

.comment-row {
  padding: 12rpx 0;
  border-top: 1rpx solid rgba(255,255,255,0.04);
}
.comment-row:first-of-type { border-top: none; }
.comment-author { color: #c4b5fd; font-size: 22rpx; font-weight: 600; display: block; }
.comment-body { color: #f0f0f5; font-size: 26rpx; line-height: 1.5; display: block; margin: 4rpx 0; }
.comment-time { color: #6b6b85; font-size: 20rpx; }

.comment-input-row {
  display: flex;
  gap: 12rpx;
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 1rpx solid rgba(255,255,255,0.04);
}
.comment-input {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1rpx solid rgba(255,255,255,0.08);
  border-radius: 12rpx;
  padding: 12rpx 16rpx;
  color: #f0f0f5;
  font-size: 26rpx;
}
.btn-disabled { opacity: 0.4; pointer-events: none; }
</style>
