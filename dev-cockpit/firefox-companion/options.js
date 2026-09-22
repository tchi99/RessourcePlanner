const DEFAULT_COCKPIT_URL = 'http://127.0.0.1:8081'

const input = document.querySelector('#cockpit-url')
const status = document.querySelector('#status')

function normalizeCockpitUrl(value) {
  const parsed = new URL((value || DEFAULT_COCKPIT_URL).trim())
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Le protocole doit être http ou https.')
  }
  if (!['127.0.0.1', 'localhost'].includes(parsed.hostname)) {
    throw new Error('Seules les adresses 127.0.0.1 et localhost sont permises.')
  }
  parsed.pathname = ''
  parsed.search = ''
  parsed.hash = ''
  return parsed.toString().replace(/\/$/, '')
}

async function restore() {
  const stored = await browser.storage.local.get('cockpitUrl')
  input.value = stored.cockpitUrl || DEFAULT_COCKPIT_URL
}

async function save() {
  try {
    const value = normalizeCockpitUrl(input.value)
    await browser.storage.local.set({ cockpitUrl: value })
    input.value = value
    status.textContent = 'Configuration enregistrée.'
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'Configuration invalide.'
  }
}

async function testConnection() {
  try {
    const value = normalizeCockpitUrl(input.value)
    const response = await fetch(`${value}/api/health`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    status.textContent = 'Dev Cockpit joignable.'
  } catch {
    status.textContent = 'Dev Cockpit non joignable à cette adresse.'
  }
}

document.querySelector('#save').addEventListener('click', () => void save())
document.querySelector('#test').addEventListener('click', () => void testConnection())

void restore()
