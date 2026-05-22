import React from 'react'
import { render, screen } from '@testing-library/preact'
import { describe, it, expect, vi } from 'vitest'
import Widget from '../Widget.jsx'

vi.mock('../api.js', () => ({
  DEFAULT_CONFIG: {
    theme: 'dark',
    greeting: 'Hello! How can I help?',
    enabled_tools: ['retrieve_docs'],
  },
  fetchConfig: vi.fn().mockResolvedValue({
    theme: 'dark',
    greeting: 'Hello! How can I help?',
    enabled_tools: ['retrieve_docs'],
  }),
}))

describe('Widget', () => {
  it('renders the chat bubble in closed state', () => {
    render(<Widget widgetId="test-id" apiBase="http://localhost:8000" />)
    expect(screen.getByRole('button', { name: /open chat/i })).toBeInTheDocument()
  })

  it('does not render the chat panel when closed', () => {
    render(<Widget widgetId="test-id" apiBase="http://localhost:8000" />)
    expect(screen.queryByRole('button', { name: /close/i })).not.toBeInTheDocument()
  })
})
