/**
 * WebSocket client with auto-reconnect for FTB live streaming.
 */

type MessageHandler = (msg: any) => void

let ws: WebSocket | null = null
let handlers: Set<MessageHandler> = new Set()
let reconnectTimer: number | null = null
let connectionState: 'disconnected' | 'connecting' | 'connected' = 'disconnected'
let stateChangeCallbacks: Set<(state: string) => void> = new Set()

function getWsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws/live`
}

export function connect() {
  if (ws && ws.readyState <= 1) return

  connectionState = 'connecting'
  notifyStateChange()

  ws = new WebSocket(getWsUrl())

  ws.onopen = () => {
    connectionState = 'connected'
    notifyStateChange()
    console.log('[ws] connected')
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      handlers.forEach(h => {
        try { h(msg) } catch (e) { console.error('[ws] handler error:', e) }
      })
    } catch (e) {
      console.error('[ws] parse error:', e)
    }
  }

  ws.onclose = () => {
    connectionState = 'disconnected'
    notifyStateChange()
    console.log('[ws] disconnected, reconnecting in 2s...')
    scheduleReconnect()
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connect()
  }, 2000)
}

function notifyStateChange() {
  stateChangeCallbacks.forEach(cb => cb(connectionState))
}

export function onMessage(handler: MessageHandler): () => void {
  handlers.add(handler)
  return () => handlers.delete(handler)
}

export function onConnectionChange(cb: (state: string) => void): () => void {
  stateChangeCallbacks.add(cb)
  return () => stateChangeCallbacks.delete(cb)
}

export function sendCommand(cmd: Record<string, any>) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'command', data: cmd }))
  }
}

export function sendUiCommand(action: string, payload: any = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ui_command', action, payload }))
  }
}

export function requestState() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'get_state' }))
  }
}

export function ping() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }))
  }
}

export function getConnectionState() { return connectionState }

export function disconnect() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  ws?.close()
  ws = null
}
