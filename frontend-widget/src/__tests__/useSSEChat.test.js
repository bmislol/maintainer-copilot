import { renderHook, act } from '@testing-library/preact'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { useSSEChat } from '../useSSEChat.js'

vi.mock('../api.js', () => ({
  createChatStream: vi.fn(),
}))

describe('useSSEChat', () => {
  afterEach(() => vi.restoreAllMocks())

  it('starts with empty messages and not loading', () => {
    const { result } = renderHook(() =>
      useSSEChat('widget-id', 'http://localhost:8000')
    )
    expect(result.current.messages).toEqual([])
    expect(result.current.isLoading).toBe(false)
  })

  it('appends user message and streams assistant tokens', async () => {
    const { createChatStream } = await import('../api.js')

    // Two SSE lines: a text chunk then [DONE]
    const sseLines = ['data: Hello\n', 'data: [DONE]\n']
    let idx = 0
    const mockReader = {
      read: vi.fn().mockImplementation(async () => {
        if (idx < sseLines.length) {
          const value = new TextEncoder().encode(sseLines[idx++])
          return { done: false, value }
        }
        return { done: true, value: undefined }
      }),
      cancel: vi.fn(),
    }

    createChatStream.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    })

    const { result } = renderHook(() =>
      useSSEChat('widget-id', 'http://localhost:8000')
    )

    await act(async () => {
      await result.current.sendMessage('test message')
    })

    const msgs = result.current.messages
    expect(msgs[0]).toMatchObject({ role: 'user', content: 'test message' })
    expect(msgs[1]).toMatchObject({ role: 'assistant', content: 'Hello' })
  })

  it('sets error message on HTTP failure', async () => {
    const { createChatStream } = await import('../api.js')
    createChatStream.mockResolvedValue({ ok: false, status: 500 })

    const { result } = renderHook(() =>
      useSSEChat('widget-id', 'http://localhost:8000')
    )

    await act(async () => {
      await result.current.sendMessage('hi')
    })

    const msgs = result.current.messages
    expect(msgs[1].content).toMatch(/Unable to connect/)
    expect(result.current.isLoading).toBe(false)
  })
})
