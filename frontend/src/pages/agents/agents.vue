<template>
  <view class="page">
    <view class="header">
      <text class="header-title">Dream Agents</text>
      <text class="header-subtitle">Automated dream workflows</text>
    </view>

    <!-- Tabs -->
    <view class="tabs">
      <view :class="['tab', activeTab === 'my' ? 'tab-active' : '']" @tap="activeTab = 'my'">
        <text class="tab-text">My Agents</text>
      </view>
      <view :class="['tab', activeTab === 'store' ? 'tab-active' : '']" @tap="activeTab = 'store'">
        <text class="tab-text">Agent Store</text>
      </view>
      <view :class="['tab', activeTab === 'vibe' ? 'tab-active' : '']" @tap="activeTab = 'vibe'">
        <text class="tab-text">Vibe Coder</text>
      </view>
    </view>

    <scroll-view class="content" scroll-y>
      <!-- My Agents -->
      <view v-if="activeTab === 'my'">
        <view class="create-section">
          <textarea
            class="agent-input"
            v-model="agentPrompt"
            placeholder="Describe your agent: 'Every Sunday, find my most negative dream and generate a healing version'"
            :auto-height="true"
          />
          <view class="btn btn-primary" @tap="onCreate">
            <text class="btn-text">Create Agent</text>
          </view>
        </view>

        <view v-for="agent in myAgents" :key="agent.id" class="agent-card">
          <view class="agent-header">
            <text class="agent-name">{{ agent.name }}</text>
            <text class="agent-status" :class="'status-' + agent.status">{{ agent.status }}</text>
          </view>
          <text class="agent-desc">{{ agent.description }}</text>
          <view class="agent-actions">
            <view class="btn-sm btn-primary" @tap="onRun(agent.id)">
              <text class="btn-sm-text">Run</text>
            </view>
          </view>
        </view>

        <view v-if="myAgents.length === 0" class="empty">
          <text class="empty-text">No agents yet. Describe one above to create it.</text>
        </view>
      </view>

      <!-- Store -->
      <view v-if="activeTab === 'store'">
        <view v-for="agent in storeAgents" :key="agent.id" class="agent-card">
          <view class="agent-header">
            <text class="agent-name">{{ agent.name }}</text>
            <text class="agent-installs">{{ agent.installs }} installs</text>
          </view>
          <text class="agent-desc">{{ agent.description }}</text>
          <view class="agent-actions">
            <view class="btn-sm btn-secondary" @tap="onInstall(agent.id)">
              <text class="btn-sm-text">{{ agent.price ? '¥' + agent.price : 'Free' }} — Install</text>
            </view>
          </view>
        </view>
        <view v-if="storeAgents.length === 0" class="empty">
          <text class="empty-text">No agents in store yet</text>
        </view>
      </view>

      <!-- Vibe Coder -->
      <view v-if="activeTab === 'vibe'">
        <view class="vibe-section">
          <text class="section-label">Customize your app with natural language</text>
          <textarea
            class="agent-input"
            v-model="vibePrompt"
            placeholder="Hide the plaza, make health chart my homepage, use dark purple theme..."
            :auto-height="true"
          />
          <view class="btn btn-primary" @tap="onVibe">
            <text class="btn-text">Apply Changes</text>
          </view>
        </view>

        <view class="current-layout" v-if="currentLayout">
          <text class="section-label">Current Layout</text>
          <text class="layout-json">{{ JSON.stringify(currentLayout, null, 2).substring(0, 500) }}</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listAgents, createAgent, runAgent, browseStore, installAgent, customizeLayout, getLayout } from '../../api/dream'

const activeTab = ref('my')
const myAgents = ref<any[]>([])
const storeAgents = ref<any[]>([])
const agentPrompt = ref('')
const vibePrompt = ref('')
const currentLayout = ref<any>(null)
const loading = ref(false)

onShow(async () => {
  try {
    myAgents.value = await listAgents('default')
    storeAgents.value = await browseStore()
    const layout = await getLayout('default')
    currentLayout.value = (layout as any)?.layout
  } catch (err) { console.error(err) }
})

async function onCreate() {
  if (!agentPrompt.value.trim()) return
  uni.showLoading({ title: 'Creating agent...' })
  try {
    // Use LLM to parse natural language into agent definition
    const agentDef = {
      name: agentPrompt.value.substring(0, 50),
      description: agentPrompt.value,
      trigger: { type: 'manual' },
      steps: [
        { action: 'llm_analyze', params: { prompt: agentPrompt.value }, output_var: 'result' },
        { action: 'notify_user', params: { message: '{{result.analysis}}' } },
      ],
    }
    await createAgent('default', agentDef)
    myAgents.value = await listAgents('default')
    agentPrompt.value = ''
    uni.hideLoading()
    uni.showToast({ title: 'Agent created!', icon: 'success' })
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Failed', icon: 'none' })
  }
}

async function onRun(agentId: string) {
  uni.showLoading({ title: 'Running...' })
  try {
    const result: any = await runAgent(agentId, 'default')
    uni.hideLoading()
    uni.showModal({ title: 'Agent Result', content: `Status: ${result.status}, Steps: ${result.steps_completed}` })
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Run failed', icon: 'none' })
  }
}

async function onInstall(agentId: string) {
  try {
    await installAgent(agentId, 'default')
    uni.showToast({ title: 'Installed!', icon: 'success' })
  } catch (err) {
    uni.showToast({ title: 'Install failed', icon: 'none' })
  }
}

async function onVibe() {
  if (!vibePrompt.value.trim()) return
  uni.showLoading({ title: 'Customizing...' })
  try {
    const result: any = await customizeLayout('default', vibePrompt.value)
    currentLayout.value = result?.layout
    vibePrompt.value = ''
    uni.hideLoading()
    uni.showToast({ title: 'Layout updated!', icon: 'success' })
  } catch (err) {
    uni.hideLoading()
    uni.showToast({ title: 'Failed', icon: 'none' })
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--dream-bg-primary); }
.header { padding: 100rpx 40rpx 20rpx; background: linear-gradient(180deg, var(--dream-bg-card-hover) 0%, var(--dream-bg-primary) 100%); }
.header-title { font-size: 44rpx; font-weight: 700; color: var(--dream-text-primary); display: block; }
.header-subtitle { font-size: 26rpx; color: var(--dream-text-muted); margin-top: 8rpx; display: block; }
.tabs { display: flex; border-bottom: 1px solid var(--dream-bg-input); }
.tab { flex: 1; padding: 20rpx 0; text-align: center; }
.tab-active { border-bottom: 3rpx solid var(--dream-primary-500); }
.tab-text { font-size: 26rpx; color: var(--dream-text-muted); }
.tab-active .tab-text { color: var(--dream-primary-500); font-weight: 600; }
.content { padding: 20rpx 30rpx; height: calc(100vh - 310rpx); }
.create-section, .vibe-section { margin-bottom: 24rpx; }
.section-label { font-size: 26rpx; color: var(--dream-text-primary); display: block; margin-bottom: 12rpx; }
.agent-input { width: 100%; background: var(--dream-bg-input); border-radius: 16rpx; padding: 20rpx; color: var(--dream-text-primary); font-size: 28rpx; min-height: 100rpx; margin-bottom: 16rpx; }
.btn { padding: 24rpx; border-radius: 16rpx; text-align: center; }
.btn-primary { background: linear-gradient(135deg, var(--dream-primary-600), var(--dream-primary-800)); }
.btn-secondary { background: var(--dream-bg-input); border: 1px solid #3b3b5c; }
.btn-text { color: var(--dream-text-primary); font-size: 28rpx; font-weight: 600; }
.agent-card { background: var(--dream-bg-card); border-radius: 16rpx; padding: 24rpx; margin-bottom: 16rpx; }
.agent-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8rpx; }
.agent-name { font-size: 30rpx; font-weight: 600; color: var(--dream-text-primary); }
.agent-status { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; }
.status-active { background: rgba(34,197,94,0.3); color: #22c55e; }
.status-draft { background: rgba(139,92,246,0.3); color: var(--dream-primary-500); }
.agent-installs { font-size: 22rpx; color: var(--dream-text-muted); }
.agent-desc { font-size: 26rpx; color: var(--dream-text-muted); line-height: 1.5; display: block; margin-bottom: 12rpx; }
.agent-actions { display: flex; gap: 12rpx; }
.btn-sm { padding: 12rpx 24rpx; border-radius: 12rpx; }
.btn-sm-text { color: var(--dream-text-primary); font-size: 24rpx; font-weight: 600; }
.current-layout { margin-top: 20rpx; }
.layout-json { font-size: 22rpx; color: var(--dream-text-muted); background: var(--dream-bg-input); padding: 16rpx; border-radius: 12rpx; white-space: pre-wrap; word-break: break-all; display: block; }
.empty { padding: 60rpx; text-align: center; }
.empty-text { color: var(--dream-text-muted); font-size: 26rpx; }
</style>
