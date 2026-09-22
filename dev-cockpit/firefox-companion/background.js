const DEFAULT_COCKPIT_URL = 'http://127.0.0.1:8081'

function normalizeCockpitUrl(value) {
  const parsed = new URL((value || DEFAULT_COCKPIT_URL).trim())
  const allowedHosts = new Set(['127.0.0.1', 'localhost'])
  if (!['http:', 'https:'].includes(parsed.protocol) || !allowedHosts.has(parsed.hostname)) {
    throw new Error('Le Dev Cockpit doit être une adresse loopback locale.')
  }
  parsed.pathname = ''
  parsed.search = ''
  parsed.hash = ''
  return parsed.toString().replace(/\/$/, '')
}

async function cockpitUrl() {
  const stored = await browser.storage.local.get('cockpitUrl')
  return normalizeCockpitUrl(stored.cockpitUrl || DEFAULT_COCKPIT_URL)
}

async function forwardHeartbeat(payload) {
  const baseUrl = await cockpitUrl()
  const response = await fetch(`${baseUrl}/api/chat-status/heartbeat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
    }
  }

  return {
    ok: true,
    status: response.status,
  }
}

browser.runtime.onMessage.addListener((message) => {
  if (!message || message.type !== 'dev-cockpit-heartbeat') {
    return undefined
  }
  return forwardHeartbeat(message.payload).catch(() => ({
    ok: false,
    status: 0,
  }))
})

browser.action.onClicked.addListener(() => {
  void browser.runtime.openOptionsPage()
})
