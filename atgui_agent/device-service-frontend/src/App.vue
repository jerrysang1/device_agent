<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import ParticleField from './ParticleField.vue'

const workspaceRef = ref(null)

function onMagneticMove(event) {
  const target = event.currentTarget
  const rect = target.getBoundingClientRect()
  const x = event.clientX - rect.left - rect.width / 2
  const y = event.clientY - rect.top - rect.height / 2
  target.style.transform = `translate(${x * 0.12}px, ${y * 0.18}px)`
}

function onMagneticLeave(event) {
  event.currentTarget.style.transform = 'translate(0, 0)'
}

function onCardTilt(event) {
  const card = event.currentTarget
  const rect = card.getBoundingClientRect()
  const px = (event.clientX - rect.left) / rect.width
  const py = (event.clientY - rect.top) / rect.height
  const rx = (py - 0.5) * -4
  const ry = (px - 0.5) * 4
  card.style.transform = `perspective(700px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-2px)`
}

function onCardTiltLeave(event) {
  event.currentTarget.style.transform = ''
}

const senderId = ref('u1001')
const draftMessage = ref('')
const isSending = ref(false)
const errorMessage = ref('')
const messages = ref([])
const messagesContainer = ref(null)

const devices = ref([])
const tickets = ref([])
const isLoadingSidebar = ref(false)
const sidebarError = ref('')
const activeTab = ref('devices')

const customerService = {
  name: '小维',
  title: '设备售后助手',
  avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=devicecare&backgroundColor=0d9488',
  status: '在线',
}

const userProfile = {
  name: '你',
  avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=user&backgroundColor=c0aede',
}

const turns = computed(() => {
  const result = []
  let currentTurn = null
  let turnIndex = 0

  for (const message of messages.value) {
    if (message.type === 'divider') {
      if (currentTurn) {
        result.push(currentTurn)
        currentTurn = null
      }
      result.push({ type: 'divider', text: message.text })
      continue
    }

    if (message.role === 'user') {
      if (currentTurn) result.push(currentTurn)
      turnIndex++
      currentTurn = {
        type: 'turn',
        id: `turn-${turnIndex}`,
        index: turnIndex,
        userMessage: message,
        botMessages: [],
      }
    } else if (message.role === 'bot') {
      if (!currentTurn) {
        turnIndex++
        currentTurn = {
          type: 'turn',
          id: `turn-${turnIndex}`,
          index: turnIndex,
          userMessage: null,
          botMessages: [],
        }
      }
      currentTurn.botMessages.push(message)
    }
  }

  if (currentTurn) result.push(currentTurn)
  return result
})

const chatEndpoint = computed(() => '/api/chat')
const chatHistoryEndpoint = computed(
  () => `/api/chat/history?sender_id=${encodeURIComponent(senderId.value.trim())}`
)
const devicesEndpoint = computed(
  () => `/device/customers/${encodeURIComponent(senderId.value.trim())}/devices`
)
const ticketsEndpoint = computed(
  () => `/device/customers/${encodeURIComponent(senderId.value.trim())}/tickets`
)

function createBaseMessage(role) {
  return { id: crypto.randomUUID(), role, buttons: [] }
}

function appendUserText(text) {
  messages.value.push({ ...createBaseMessage('user'), type: 'text', text })
}

function appendUserObject(objectType, payload) {
  messages.value.push({
    ...createBaseMessage('user'),
    type: 'object',
    objectType,
    payload,
  })
}

function appendBotMessages(botMessages) {
  for (const message of botMessages) {
    appendMessage('bot', message)
  }
}

function appendMessage(role, message) {
  if (role === 'divider') {
    messages.value.push({
      ...createBaseMessage('divider'),
      type: 'divider',
      text: message.text ?? '以上为历史消息',
    })
    return
  }

  if (message.object) {
    messages.value.push({
      ...createBaseMessage(role),
      type: 'object',
      objectType: message.object.type,
      payload: message.object,
    })
  } else {
    messages.value.push({
      ...createBaseMessage(role),
      type: 'text',
      text: message.text ?? '',
      suggestions: message.suggestions ?? null,
      images: Array.isArray(message.images) ? message.images : null,
    })
  }
}

function setHistoryMessages(historyMessages) {
  messages.value = []
  for (const message of historyMessages) {
    const role = ['user', 'bot', 'divider'].includes(message.role) ? message.role : 'bot'
    appendMessage(role, message)
  }
}

async function scrollToBottom() {
  await nextTick()
  const container = messagesContainer.value
  if (!container) return
  container.scrollTop = container.scrollHeight
}

watch(
  () => messages.value.length,
  async () => {
    await scrollToBottom()
  }
)

function resetConversation() {
  messages.value = []
  errorMessage.value = ''
}

const TICKET_STATUS_CLASS = {
  submitted: 'status-warning',
  accepted: 'status-info',
  diagnosing: 'status-info',
  repairing: 'status-info',
  shipping: 'status-info',
  completed: 'status-success',
  cancelled: 'status-muted',
  transferred: 'status-danger',
}

const DEVICE_STATUS_CLASS = {
  in_use: 'status-success',
  repairing: 'status-warning',
  retired: 'status-muted',
}

const WARRANTY_STATUS_CLASS = {
  in_warranty: 'status-success',
  expired: 'status-danger',
}

function getTicketStatusClass(status) {
  return TICKET_STATUS_CLASS[status] || 'status-muted'
}

function getDeviceStatusClass(status) {
  return DEVICE_STATUS_CLASS[status] || 'status-muted'
}

function getWarrantyStatusClass(status) {
  return WARRANTY_STATUS_CLASS[status] || 'status-muted'
}

function formatWarrantyLabel(status) {
  return status === 'in_warranty' ? '保修中' : status === 'expired' ? '已过保' : status || '—'
}

function formatDeviceStatusLabel(status) {
  const map = { in_use: '使用中', repairing: '维修中', retired: '已退役' }
  return map[status] || status || '—'
}

function formatTicketStatusLabel(status) {
  const map = {
    submitted: '已提交',
    accepted: '已受理',
    diagnosing: '诊断中',
    repairing: '维修中',
    shipping: '寄送中',
    completed: '已完成',
    cancelled: '已取消',
    transferred: '已转人工',
  }
  return map[status] || status || '—'
}

function getObjectTitle(message) {
  const payload = message.payload ?? {}
  if (payload.title) return payload.title
  return message.objectType === 'device' ? '设备对象' : '工单对象'
}

function getObjectIdentifier(message) {
  const payload = message.payload ?? {}
  const id = payload.device_id ?? payload.ticket_id ?? payload.id
  const label = message.objectType === 'device' ? '设备编号' : '工单号'
  return id ? `${label}：${id}` : label
}

function getObjectSummary(message) {
  const payload = message.payload ?? {}
  if (message.objectType === 'device') {
    return `型号：${payload.model || '—'} · ${formatWarrantyLabel(payload.warranty_status)}`
  }
  return payload.status_desc || formatTicketStatusLabel(payload.status)
}

function getObjectStatus(message) {
  const payload = message.payload ?? {}
  return message.objectType === 'device'
    ? formatWarrantyLabel(payload.warranty_status)
    : formatTicketStatusLabel(payload.status)
}

function getObjectStatusClass(message) {
  const payload = message.payload ?? {}
  return message.objectType === 'device'
    ? getWarrantyStatusClass(payload.warranty_status)
    : getTicketStatusClass(payload.status)
}

async function fetchSidebarData() {
  const currentSenderId = senderId.value.trim()
  devices.value = []
  tickets.value = []
  sidebarError.value = ''

  if (!currentSenderId) return

  isLoadingSidebar.value = true
  try {
    const [devicesResponse, ticketsResponse] = await Promise.all([
      fetch(devicesEndpoint.value),
      fetch(ticketsEndpoint.value),
    ])

    const devicesText = await devicesResponse.text()
    const ticketsText = await ticketsResponse.text()
    let devicesPayload = {}
    let ticketsPayload = {}
    try {
      devicesPayload = devicesText ? JSON.parse(devicesText) : {}
    } catch {
      throw new Error(`加载设备列表失败（HTTP ${devicesResponse.status}）。请检查中台 192.168.10.15:18082。`)
    }
    try {
      ticketsPayload = ticketsText ? JSON.parse(ticketsText) : {}
    } catch {
      throw new Error(`加载工单列表失败（HTTP ${ticketsResponse.status}）。请检查中台 192.168.10.15:18082。`)
    }

    if (!devicesResponse.ok) {
      throw new Error(devicesPayload.detail || `加载设备列表失败（HTTP ${devicesResponse.status}）。`)
    }
    if (!ticketsResponse.ok) {
      throw new Error(ticketsPayload.detail || `加载工单列表失败（HTTP ${ticketsResponse.status}）。`)
    }

    devices.value = Array.isArray(devicesPayload?.data?.devices) ? devicesPayload.data.devices : []
    tickets.value = Array.isArray(ticketsPayload?.data?.tickets) ? ticketsPayload.data.tickets : []
  } catch (error) {
    sidebarError.value = error instanceof Error ? error.message : '加载右侧列表失败。'
  } finally {
    isLoadingSidebar.value = false
  }
}

async function fetchChatHistory() {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    messages.value = []
    return
  }

  try {
    const response = await fetch(chatHistoryEndpoint.value)
    const text = await response.text()
    if (!response.ok || !text) {
      console.warn('chat history unavailable:', response.status)
      return
    }
    const data = JSON.parse(text)
    if (currentSenderId === senderId.value.trim()) {
      setHistoryMessages(Array.isArray(data?.messages) ? data.messages : [])
    }
  } catch (error) {
    // Agent 网关未启动时静默，侧边栏仍可用
    console.warn('chat history unavailable:', error)
  }
}

async function sendPayload(payload) {
  if (isSending.value) return

  errorMessage.value = ''
  isSending.value = true

  try {
    const response = await fetch(chatEndpoint.value, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender_id: senderId.value.trim(),
        ...payload,
      }),
    })

    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.detail || '请求失败。')
    }

    appendBotMessages(data.messages ?? [])
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? `${error.message}（Agent 网关未启动时可先使用中台侧边栏查询设备/工单）`
        : '请求失败。'
  } finally {
    isSending.value = false
  }
}

async function sendSuggestion(text) {
  appendUserText(text)
  await sendPayload({ text })
}

async function sendQuickText(text) {
  draftMessage.value = text
  await sendTextMessage()
}

async function sendTextMessage() {
  const text = draftMessage.value.trim()
  const currentSenderId = senderId.value.trim()

  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }
  if (!text) return

  draftMessage.value = ''
  appendUserText(text)
  await sendPayload({ text })
}

async function sendDevice(device) {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }

  appendUserObject('device', { ...device, title: device.model })
  await sendPayload({
    object: {
      type: 'device',
      id: device.device_id,
      title: device.model,
      attributes: {
        device_id: device.device_id,
        model: device.model,
        category: device.category,
        status: device.status,
        warranty_status: device.warranty_status,
        purchase_date: device.purchase_date,
      },
    },
  })
}

async function sendTicket(ticket) {
  const currentSenderId = senderId.value.trim()
  if (!currentSenderId) {
    errorMessage.value = '请先输入 sender_id。'
    return
  }

  appendUserObject('ticket', {
    ...ticket,
    title: `${ticket.model || '设备'} · ${ticket.problem_type}`,
  })
  await sendPayload({
    object: {
      type: 'ticket',
      id: ticket.ticket_id,
      title: `${ticket.model || '设备'} · ${ticket.problem_type}`,
      attributes: {
        ticket_id: ticket.ticket_id,
        device_id: ticket.device_id,
        model: ticket.model,
        problem_type: ticket.problem_type,
        problem_desc: ticket.problem_desc,
        status: ticket.status,
        status_desc: ticket.status_desc,
        priority: ticket.priority,
        created_at: ticket.created_at,
      },
    },
  })
}

watch(
  () => senderId.value.trim(),
  async (value, previousValue) => {
    if (value === previousValue) return

    resetConversation()
    if (!value) {
      devices.value = []
      tickets.value = []
      return
    }
    await Promise.all([fetchSidebarData(), fetchChatHistory()])
  }
)

onMounted(async () => {
  await Promise.all([fetchSidebarData(), fetchChatHistory()])
})
</script>

<template>
  <div class="app-shell">
    <ParticleField />
    <div ref="workspaceRef" class="workspace">
      <div class="chat-card">
        <header class="chat-header">
          <div class="header-content">
            <div class="header-info">
              <h1>设备售后协同工作台</h1>
              <div class="service-info">
                <div class="service-avatar-wrapper">
                  <img :src="customerService.avatar" class="service-avatar" alt="小维" />
                  <span class="status-indicator"></span>
                </div>
                <div class="service-details">
                  <span class="service-name">{{ customerService.name }}</span>
                  <span class="service-status">{{ customerService.status }}</span>
                </div>
              </div>
            </div>
            <button
              type="button"
              class="clear-button"
              title="清空对话"
              @click="resetConversation"
              @mousemove="onMagneticMove"
              @mouseleave="onMagneticLeave"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 12a9 9 0 1 0 3-6.7" />
                <path d="M3 4v5h5" />
              </svg>
              <span>新对话</span>
            </button>
          </div>
        </header>

        <section class="controls">
          <label class="field">
            <span>sender_id / customer_id</span>
            <div class="field-row">
              <input v-model="senderId" type="text" placeholder="u1001" />
              <button
                type="button"
                class="secondary-button"
                :disabled="isLoadingSidebar"
                @click="fetchSidebarData"
                @mousemove="onMagneticMove"
                @mouseleave="onMagneticLeave"
              >
                {{ isLoadingSidebar ? '加载中...' : '刷新对象列表' }}
              </button>
            </div>
          </label>
        </section>

        <section ref="messagesContainer" class="messages">
          <div v-if="turns.length === 0" class="welcome">
            <div class="welcome-card">
              <h2 class="welcome-greeting">Hi，我是 {{ customerService.name }}</h2>
              <p class="welcome-subtitle">设备手册问答 · 保修查询 · 工单创建 · 转人工</p>
              <div class="welcome-chips">
                <button
                  v-for="chip in [
                    '设备 DEV-2026-0001 还在保修期吗？',
                    'H3C LA2608 怎么配置业务 VLAN？',
                    '我的 LA2608 连不上无线控制器，帮我报修',
                    '转人工',
                  ]"
                  :key="chip"
                  type="button"
                  class="welcome-chip"
                  :disabled="isSending"
                  @click="sendQuickText(chip)"
                  @mousemove="onMagneticMove"
                  @mouseleave="onMagneticLeave"
                >{{ chip }}</button>
              </div>
              <div class="welcome-features">
                <span class="feature-item">设备档案</span>
                <span class="feature-item">保修查询</span>
                <span class="feature-item">售后工单</span>
                <span class="feature-item">转人工</span>
              </div>
            </div>
          </div>

          <template v-for="(item, index) in turns" :key="item.id || index">
            <div v-if="item.type === 'divider'" class="history-divider">
              <span>{{ item.text }}</span>
            </div>

            <div v-else class="turn-card">
              <div class="turn-header">
                <span class="turn-badge">Turn {{ item.index }}</span>
                <span class="turn-label">对话轮次</span>
              </div>

              <div v-if="item.userMessage" class="turn-section user-section">
                <div class="section-header">
                  <div class="avatar-wrapper user-avatar">
                    <img :src="userProfile.avatar" class="avatar" alt="用户" />
                  </div>
                  <div class="agent-info">
                    <span class="agent-name">{{ userProfile.name }}</span>
                    <span class="agent-label">用户</span>
                  </div>
                </div>
                <div class="turn-bubble user-bubble">
                  <template v-if="item.userMessage.type === 'object'">
                    <div class="object-card">
                      <div class="object-card-badge">
                        {{ item.userMessage.objectType === 'device' ? '设备对象' : '工单对象' }}
                      </div>
                      <div class="object-card-title">{{ getObjectTitle(item.userMessage) }}</div>
                      <div class="object-card-meta">{{ getObjectIdentifier(item.userMessage) }}</div>
                      <div class="object-card-meta">
                        <span class="status-badge" :class="getObjectStatusClass(item.userMessage)">
                          {{ getObjectStatus(item.userMessage) }}
                        </span>
                      </div>
                      <div class="object-card-meta">{{ getObjectSummary(item.userMessage) }}</div>
                    </div>
                  </template>
                  <template v-else>
                    <p>{{ item.userMessage.text }}</p>
                  </template>
                </div>
              </div>

              <div v-if="item.botMessages.length > 0" class="turn-section bot-section">
                <div class="section-header">
                  <div class="avatar-wrapper service-avatar">
                    <img :src="customerService.avatar" class="avatar" alt="小维" />
                    <span class="status-dot"></span>
                  </div>
                  <div class="agent-info">
                    <span class="agent-name">{{ customerService.name }}</span>
                    <span class="agent-label">{{ customerService.title }}</span>
                  </div>
                </div>
                <div class="bot-messages">
                  <div
                    v-for="(botMsg, msgIndex) in item.botMessages"
                    :key="msgIndex"
                    class="turn-bubble bot-bubble"
                  >
                    <template v-if="botMsg.type === 'object'">
                      <div class="object-card">
                        <div class="object-card-badge">
                          {{ botMsg.objectType === 'device' ? '设备对象' : '工单对象' }}
                        </div>
                        <div class="object-card-title">{{ getObjectTitle(botMsg) }}</div>
                        <div class="object-card-meta">{{ getObjectIdentifier(botMsg) }}</div>
                        <div class="object-card-meta">
                          <span class="status-badge" :class="getObjectStatusClass(botMsg)">
                            {{ getObjectStatus(botMsg) }}
                          </span>
                        </div>
                        <div class="object-card-meta">{{ getObjectSummary(botMsg) }}</div>
                      </div>
                    </template>
                    <template v-else>
                      <p>{{ botMsg.text }}</p>
                      <div v-if="botMsg.images && botMsg.images.length" class="message-images">
                        <a
                          v-for="(img, imgIndex) in botMsg.images"
                          :key="imgIndex"
                          :href="img"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="message-image-link"
                        >
                          <img :src="img" :alt="`手册截图 ${imgIndex + 1}`" class="message-image" loading="lazy" />
                        </a>
                      </div>
                    </template>
                    <div v-if="botMsg.suggestions && botMsg.suggestions.length > 0" class="suggestion-chips">
                      <button
                        v-for="sug in botMsg.suggestions"
                        :key="sug"
                        type="button"
                        class="suggestion-chip"
                        :disabled="isSending"
                        @click.stop="sendSuggestion(sug)"
                        @mousemove="onMagneticMove"
                        @mouseleave="onMagneticLeave"
                      >{{ sug }}</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </section>

        <div v-if="isSending" class="typing-indicator">
          <div class="typing-avatar">
            <img :src="customerService.avatar" class="avatar-small" alt="小维" />
          </div>
          <div class="typing-bubble">
            <span class="typing-dots"><span></span><span></span><span></span></span>
            <span class="typing-label">小维正在处理...</span>
          </div>
        </div>

        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <form class="composer" @submit.prevent="sendTextMessage">
          <input
            v-model="draftMessage"
            type="text"
            placeholder="请输入设备咨询 / 报修 / 保修问题..."
            :disabled="isSending"
          />
          <button type="submit" :disabled="isSending || !draftMessage.trim()">
            {{ isSending ? '发送中...' : '发送' }}
          </button>
        </form>
      </div>

      <aside class="sidebar">
        <div class="sidebar-header">
          <h2>业务对象</h2>
        </div>

        <div class="tabs">
          <button
            type="button"
            class="tab-button"
            :class="{ active: activeTab === 'devices' }"
            @click="activeTab = 'devices'"
          >
            设备
          </button>
          <button
            type="button"
            class="tab-button"
            :class="{ active: activeTab === 'tickets' }"
            @click="activeTab = 'tickets'"
          >
            工单
          </button>
        </div>

        <p v-if="sidebarError" class="sidebar-error">{{ sidebarError }}</p>

        <div v-if="activeTab === 'devices'" class="sidebar-list">
          <div v-if="!devices.length && !isLoadingSidebar" class="sidebar-empty">
            暂无设备数据
          </div>

          <article
            v-for="device in devices"
            :key="device.device_id"
            class="sidebar-card interactive-card"
            @mousemove="onCardTilt"
            @mouseleave="onCardTiltLeave"
          >
            <div class="card-top">
              <div class="card-title">{{ device.model }}</div>
              <span class="status-badge" :class="getWarrantyStatusClass(device.warranty_status)">
                {{ formatWarrantyLabel(device.warranty_status) }}
              </span>
            </div>
            <div class="card-meta">设备编号：{{ device.device_id }}</div>
            <div class="card-meta">类别：{{ device.category }}</div>
            <div class="card-meta">
              <span class="status-badge" :class="getDeviceStatusClass(device.status)">
                {{ formatDeviceStatusLabel(device.status) }}
              </span>
            </div>
            <button
              type="button"
              class="secondary-button full-width"
              :disabled="isSending"
              @click="sendDevice(device)"
              @mousemove="onMagneticMove"
              @mouseleave="onMagneticLeave"
            >
              发送设备
            </button>
          </article>
        </div>

        <div v-else class="sidebar-list">
          <div v-if="!tickets.length && !isLoadingSidebar" class="sidebar-empty">
            暂无工单数据
          </div>

          <article
            v-for="ticket in tickets"
            :key="ticket.ticket_id"
            class="sidebar-card interactive-card"
            @mousemove="onCardTilt"
            @mouseleave="onCardTiltLeave"
          >
            <div class="card-top">
              <div class="card-title">{{ ticket.model || '设备' }} · {{ ticket.problem_type }}</div>
              <span class="status-badge" :class="getTicketStatusClass(ticket.status)">
                {{ formatTicketStatusLabel(ticket.status) }}
              </span>
            </div>
            <div class="card-meta">工单号：{{ ticket.ticket_id }}</div>
            <div class="card-meta">设备：{{ ticket.device_id }}</div>
            <div class="card-meta">{{ ticket.problem_desc }}</div>
            <button
              type="button"
              class="secondary-button full-width"
              :disabled="isSending"
              @click="sendTicket(ticket)"
              @mousemove="onMagneticMove"
              @mouseleave="onMagneticLeave"
            >
              发送工单
            </button>
          </article>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(:root) {
  --color-bg: #f4f6f9;
  --color-surface: #ffffff;
  --color-surface-subtle: #f8fafc;
  --color-surface-muted: #f1f5f9;
  --color-text-primary: #0f172a;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;
  --color-accent: #0d9488;
  --color-accent-strong: #0f766e;
  --color-accent-soft: #f0fdfa;
  --color-accent-border: #99f6e4;
  --color-warm: #d97706;
  --color-warm-soft: #fffbeb;
  --color-warm-border: #fde68a;
  --color-success: #059669;
  --color-success-soft: #ecfdf5;
  --color-success-border: #a7f3d0;
  --color-info: #0284c7;
  --color-info-soft: #f0f9ff;
  --color-info-border: #bae6fd;
  --color-danger: #e11d48;
  --color-danger-soft: #fff1f2;
  --color-danger-border: #fecdd3;
  --color-border: #e2e8f0;
  --color-border-light: #f1f5f9;
  --color-border-strong: #cbd5e1;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-full: 9999px;
  --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 4px 12px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 4px 16px rgba(15, 23, 42, 0.08);
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --duration-fast: 150ms;
  --duration-base: 220ms;
}

:global(body) {
  margin: 0;
  font-family: "Inter", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  background: var(--color-bg);
  color: var(--color-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

:global(button),
:global(input) {
  font: inherit;
}

:global(#app) {
  min-height: 100vh;
}

.app-shell {
  position: relative;
  min-height: 100vh;
  padding: 20px;
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(13, 148, 136, 0.06), transparent),
    var(--color-bg);
}

.workspace {
  position: relative;
  z-index: 1;
  width: min(1680px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
}

.chat-card,
.sidebar {
  min-height: calc(100vh - 40px);
  height: calc(100vh - 40px);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(10px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.chat-card {
  display: flex;
  flex-direction: column;
}

.sidebar {
  display: flex;
  flex-direction: column;
}

.chat-header,
.sidebar-header {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--color-border-light);
  background: rgba(255, 255, 255, 0.72);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 20px;
  flex: 1;
  min-width: 0;
}

.chat-header h1,
.sidebar-header h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--color-text-primary);
}

.sidebar-header h2 {
  font-size: 16px;
}

.service-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px 6px 6px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  width: fit-content;
}

.service-avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.service-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--color-accent-soft);
  border: 2px solid var(--color-surface);
  box-shadow: 0 0 0 1px var(--color-accent-border);
}

.status-indicator {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 10px;
  height: 10px;
  background: var(--color-success);
  border: 2px solid var(--color-surface);
  border-radius: 50%;
}

.service-details {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-right: 4px;
}

.service-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.service-status {
  font-size: 11px;
  color: var(--color-success);
  font-weight: 500;
  line-height: 1.3;
}

.clear-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--duration-fast) ease, border-color var(--duration-fast) ease, background var(--duration-fast) ease, transform var(--duration-base) var(--ease-out), box-shadow var(--duration-base) ease;
  will-change: transform;
}

.clear-button:hover {
  border-color: var(--color-danger-border);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.controls {
  display: grid;
  gap: 10px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--color-border-light);
  background: rgba(248, 250, 252, 0.78);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field > span {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.field-row {
  display: flex;
  gap: 10px;
}

.field input,
.composer input {
  width: 100%;
  min-width: 0;
  min-height: 40px;
  padding: 9px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: 14px;
  transition: border-color var(--duration-fast) ease, box-shadow var(--duration-fast) ease;
}

.field input::placeholder,
.composer input::placeholder {
  color: var(--color-text-muted);
}

.field input:focus,
.composer input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: rgba(255, 255, 255, 0.55);
}

.messages::-webkit-scrollbar {
  width: 6px;
}

.messages::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
  border-radius: 999px;
}

.messages::-webkit-scrollbar-track {
  background: transparent;
}

.turn-card {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
}

.turn-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--color-border-light);
}

.turn-badge {
  display: inline-flex;
  padding: 2px 8px;
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  font-size: 11px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-accent-border);
}

.turn-label {
  font-size: 11px;
  color: var(--color-text-muted);
  font-weight: 500;
}

.turn-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  font-weight: 600;
}

.avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--color-border);
  background: var(--color-surface-muted);
}

.user-avatar .avatar {
  border-color: var(--color-info-border);
}

.service-avatar .avatar {
  border-color: var(--color-accent-border);
}

.status-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 9px;
  height: 9px;
  background: var(--color-success);
  border: 2px solid var(--color-surface);
  border-radius: 50%;
}

.agent-info {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.agent-label {
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.3;
}

.user-section .agent-name {
  color: var(--color-info);
}

.bot-section .agent-name {
  color: var(--color-accent-strong);
}

.turn-bubble {
  padding: 12px 14px;
  border-radius: var(--radius-md);
  font-size: 14px;
  line-height: 1.65;
}

.user-bubble {
  background: var(--color-accent);
  color: #ffffff;
  margin-left: auto;
  max-width: 85%;
  border-bottom-right-radius: 4px;
}

.bot-bubble {
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: 4px;
}

.bot-messages {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.turn-bubble p {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.message-image-link {
  display: block;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: #fff;
  max-width: 160px;
}

.message-image {
  display: block;
  width: 160px;
  height: 120px;
  object-fit: cover;
  cursor: zoom-in;
}

.history-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--color-text-muted);
  font-size: 12px;
  padding: 4px 0;
}

.history-divider::before,
.history-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--color-border);
}

.welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.welcome-card {
  max-width: 480px;
  width: 100%;
  padding: 36px 32px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(8px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  text-align: center;
  box-shadow: var(--shadow-sm);
}

.welcome-greeting {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-text-primary);
}

.welcome-subtitle {
  margin: 0 0 24px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.welcome-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-bottom: 24px;
}

.welcome-chip {
  padding: 8px 14px;
  border: 1px solid var(--color-accent-border);
  border-radius: var(--radius-full);
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-fast) ease, border-color var(--duration-fast) ease, transform var(--duration-base) var(--ease-out), box-shadow var(--duration-base) ease;
  will-change: transform;
}

.welcome-chip:hover:not(:disabled) {
  background: #ccfbf1;
  border-color: var(--color-accent);
  box-shadow: 0 6px 18px rgba(13, 148, 136, 0.16);
}

.welcome-chip:active:not(:disabled) {
  transform: scale(0.98);
}

.welcome-chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.welcome-features {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin: 0;
}

.feature-item {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.typing-indicator {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 0 18px 8px;
}

.avatar-small {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--color-accent-border);
  background: var(--color-accent-soft);
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: 14px 14px 14px 4px;
}

.typing-dots {
  display: flex;
  gap: 3px;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: dotBounce 1.2s ease-in-out infinite;
}

.typing-dots span:nth-child(1) { animation-delay: 0s; }
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dotBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30% { transform: translateY(-5px); opacity: 1; }
}

.typing-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
  flex-shrink: 0;
}

.status-warning {
  background: var(--color-warm-soft);
  color: var(--color-warm);
  border: 1px solid var(--color-warm-border);
}

.status-info {
  background: var(--color-info-soft);
  color: var(--color-info);
  border: 1px solid var(--color-info-border);
}

.status-success {
  background: var(--color-success-soft);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.status-muted {
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.status-danger {
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border: 1px solid var(--color-danger-border);
}

.object-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}

.object-card-badge {
  display: inline-flex;
  width: fit-content;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  border: 1px solid var(--color-accent-border);
}

.user-bubble .object-card-badge {
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.28);
}

.object-card-title {
  font-size: 14px;
  font-weight: 600;
}

.object-card-meta {
  font-size: 12px;
  opacity: 0.92;
}

.error-message,
.sidebar-error {
  margin: 0;
  padding: 0 22px 12px;
  color: var(--color-danger);
  font-size: 12px;
  font-weight: 500;
}

.composer {
  display: flex;
  gap: 10px;
  padding: 14px 22px;
  border-top: 1px solid var(--color-border-light);
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
}

.composer button,
.secondary-button,
.tab-button {
  min-height: 40px;
  padding: 8px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  transition: background var(--duration-fast) ease, border-color var(--duration-fast) ease, color var(--duration-fast) ease, box-shadow var(--duration-base) ease, transform var(--duration-base) var(--ease-out);
  will-change: transform;
}

.composer button {
  min-width: 88px;
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #ffffff;
}

.composer button:hover:not(:disabled) {
  background: var(--color-accent-strong);
  border-color: var(--color-accent-strong);
}

.secondary-button:hover:not(:disabled),
.tab-button:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  background: var(--color-surface-subtle);
}

.composer button:disabled,
.secondary-button:disabled,
.tab-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tabs {
  display: flex;
  gap: 6px;
  padding: 12px 22px 10px;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-surface);
}

.tab-button {
  min-width: 72px;
  min-height: 34px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
}

.tab-button.active {
  background: var(--color-accent-soft);
  border-color: var(--color-accent-border);
  color: var(--color-accent-strong);
}

.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: rgba(248, 250, 252, 0.62);
}

.sidebar-list::-webkit-scrollbar {
  width: 6px;
}

.sidebar-list::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
  border-radius: 999px;
}

.sidebar-card {
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(6px);
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: var(--shadow-xs);
  transition: border-color var(--duration-fast) ease, box-shadow var(--duration-base) ease, transform var(--duration-base) var(--ease-out);
  will-change: transform;
}

.sidebar-card:hover {
  border-color: var(--color-accent-border);
  box-shadow: var(--shadow-md);
}

.interactive-card {
  transform-style: preserve-3d;
}

.card-top {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  align-items: flex-start;
}

.card-title {
  font-size: 13px;
  line-height: 1.45;
  font-weight: 600;
  color: var(--color-text-primary);
}

.card-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}

.suggestion-chip {
  padding: 5px 12px;
  border: 1px solid var(--color-accent-border);
  border-radius: var(--radius-full);
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-fast) ease, border-color var(--duration-fast) ease, transform var(--duration-base) var(--ease-out), box-shadow var(--duration-base) ease;
  will-change: transform;
}

.suggestion-chip:hover:not(:disabled) {
  background: #ccfbf1;
  border-color: var(--color-accent);
  box-shadow: 0 4px 14px rgba(13, 148, 136, 0.14);
}

.suggestion-chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.full-width {
  width: 100%;
}

.sidebar-empty {
  margin: auto;
  color: var(--color-text-muted);
  text-align: center;
  font-size: 13px;
  padding: 32px 12px;
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .sidebar {
    min-height: auto;
    height: auto;
    max-height: 50vh;
  }

  .chat-card {
    min-height: 70vh;
    height: 70vh;
  }

  .header-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
