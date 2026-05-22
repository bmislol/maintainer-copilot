import React, { useEffect, useState } from 'react'
import ChatPanel from './ChatPanel.jsx'
import { DEFAULT_CONFIG, fetchConfig } from './api.js'
import stylesText from './styles.css?inline'

/**
 * Root widget component.
 * Fetches config at mount time; falls back to DEFAULT_CONFIG on any error.
 * Toggles between bubble (closed) and ChatPanel (open).
 *
 * The <style> tag is rendered into the shadow root by React so host-page
 * CSS never bleeds in.
 */
export default function Widget({ widgetId, apiBase }) {
  const [isOpen, setIsOpen] = useState(false)
  const [config, setConfig] = useState(DEFAULT_CONFIG)

  useEffect(() => {
    fetchConfig(widgetId, apiBase).then(setConfig)
  }, [widgetId, apiBase])

  return (
    <>
      <style>{stylesText}</style>
      {isOpen ? (
        <ChatPanel
          widgetId={widgetId}
          apiBase={apiBase}
          config={config}
          onClose={() => setIsOpen(false)}
        />
      ) : (
        <button
          className="widget-bubble"
          onClick={() => setIsOpen(true)}
          aria-label="Open chat"
        >
          🤖
        </button>
      )}
    </>
  )
}
