import React from 'react'
import { createRoot } from 'react-dom/client'
import Widget from './Widget.jsx'

// document.currentScript is only available synchronously at IIFE execution
// time (the built bundle). In Vite dev mode the script runs as an ES module
// where currentScript is null — fall back to window.__WIDGET_DEV_CONFIG__.
const scriptTag = document.currentScript
const devConfig = window.__WIDGET_DEV_CONFIG__

const widgetId =
  scriptTag?.getAttribute('data-widget-id') || devConfig?.widgetId || ''
const apiBase =
  scriptTag?.getAttribute('data-api-base') ||
  devConfig?.apiBase ||
  'http://localhost:8000'

if (widgetId) {
  // Mount into a Shadow DOM so host-page CSS cannot leak into the widget.
  const host = document.createElement('div')
  host.id = 'maintainer-copilot-widget-host'
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'open' })
  const mountPoint = document.createElement('div')
  shadow.appendChild(mountPoint)

  const root = createRoot(mountPoint)
  root.render(<Widget widgetId={widgetId} apiBase={apiBase} />)
} else {
  console.warn('[Maintainer Copilot] data-widget-id attribute is required.')
}
