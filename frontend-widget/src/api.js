export const DEFAULT_CONFIG = {
  theme: 'dark',
  greeting: 'Hello! How can I help?',
  enabled_tools: ['retrieve_docs'],
}

/**
 * Fetch widget config from the API.
 * Returns DEFAULT_CONFIG on 404 or any network error so the widget is
 * always functional even before Phase 4.6 adds the widgets table.
 */
export async function fetchConfig(widgetId, apiBase) {
  try {
    const res = await fetch(`${apiBase}/widgets/${widgetId}/config`)
    if (!res.ok) return DEFAULT_CONFIG
    return await res.json()
  } catch {
    return DEFAULT_CONFIG
  }
}

/**
 * Open a POST SSE stream to /chat/send.
 * Returns the raw fetch Response so the caller can stream response.body.
 */
export async function createChatStream(widgetId, convId, message, apiBase) {
  return fetch(`${apiBase}/chat/send?widget_id=${widgetId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: convId, message }),
  })
}
