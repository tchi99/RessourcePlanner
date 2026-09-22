(() => {
  const HEARTBEAT_MS = 5000
  const STOP_SELECTORS = [
    '[data-testid="stop-button"]',
    '[data-testid="stop-generating-button"]',
    'button[aria-label="Stop generating"]',
    'button[aria-label="Stop response"]',
    'button[aria-label="Stop streaming"]',
    'button[aria-label="Arrêter la génération"]',
    'button[aria-label="Arrêter la réponse"]',
  ]

  let sendTimer = null

  function isVisible(element) {
    if (!(element instanceof HTMLElement)) return false
    const style = window.getComputedStyle(element)
    if (style.display === 'none' || style.visibility === 'hidden') return false
    const rect = element.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
  }

  function stopControlVisible() {
    for (const selector of STOP_SELECTORS) {
      const element = document.querySelector(selector)
      if (element && isVisible(element)) return true
    }

    for (const button of document.querySelectorAll('button[aria-label], button[title]')) {
      if (!isVisible(button)) continue
      const label = `${button.getAttribute('aria-label') || ''} ${button.getAttribute('title') || ''}`
        .trim()
        .toLowerCase()
      if (
        label.includes('stop generating') ||
        label.includes('stop response') ||
        label.includes('stop streaming') ||
        label.includes('arrêter la génération') ||
        label.includes('arrêter la réponse') ||
        label.includes('interrompre la génération')
      ) {
        return true
      }
    }

    return false
  }

  function heartbeatPayload() {
    const working = stopControlVisible()
    return {
      conversation_url: window.location.href,
      state: working ? 'working' : 'idle',
      page_visible: document.visibilityState === 'visible',
      page_focused: document.hasFocus(),
      ui_signal: working ? 'stop-control' : 'none',
    }
  }

  function sendHeartbeat() {
    if (window.location.hostname !== 'chatgpt.com') return
    void browser.runtime.sendMessage({
      type: 'dev-cockpit-heartbeat',
      payload: heartbeatPayload(),
    }).catch(() => undefined)
  }

  function scheduleImmediateHeartbeat() {
    if (sendTimer !== null) return
    sendTimer = window.setTimeout(() => {
      sendTimer = null
      sendHeartbeat()
    }, 250)
  }

  const observer = new MutationObserver(scheduleImmediateHeartbeat)
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['aria-label', 'data-testid', 'disabled'],
  })

  document.addEventListener('visibilitychange', scheduleImmediateHeartbeat)
  window.addEventListener('focus', scheduleImmediateHeartbeat)
  window.addEventListener('blur', scheduleImmediateHeartbeat)
  window.addEventListener('popstate', scheduleImmediateHeartbeat)

  window.setInterval(sendHeartbeat, HEARTBEAT_MS)
  sendHeartbeat()
})()
