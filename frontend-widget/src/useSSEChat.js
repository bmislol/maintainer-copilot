import { useCallback, useState } from 'react'
import { createChatStream } from './api.js'

/**
 * Manages chat state and SSE streaming for one widget session.
 *
 * SSE with POST requires fetch + ReadableStream.
 * EventSource only supports GET, so it can't carry the JSON request body.
 *
 * Returns { messages, sendMessage, isLoading }.
 */
export function useSSEChat(widgetId, apiBase) {
  const [messages, setMessages] = useState([])
  const [convId, setConvId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return

    // Generate conversation_id on the first turn and keep it stable.
    const currentConvId = convId || crypto.randomUUID()
    if (!convId) setConvId(currentConvId)

    setMessages(prev => [...prev, { role: 'user', content: text }])
    setIsLoading(true)

    // Add a typing placeholder that we'll replace token-by-token.
    const typingId = 'typing-' + Date.now()
    setMessages(prev => [
      ...prev,
      { id: typingId, role: 'assistant', content: '', typing: true },
    ])

    try {
      const response = await createChatStream(widgetId, currentConvId, text, apiBase)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assistantText = ''

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep the incomplete trailing fragment

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const chunk = line.slice(6)
          if (chunk === '[DONE]') {
            reader.cancel()
            break
          }
          assistantText += chunk
          setMessages(prev =>
            prev.map(m =>
              m.id === typingId
                ? { ...m, content: assistantText, typing: false }
                : m
            )
          )
        }
      }
    } catch (err) {
      setMessages(prev =>
        prev.map(m =>
          m.id === typingId
            ? { ...m, content: 'Unable to connect. Please try again.', typing: false }
            : m
        )
      )
    } finally {
      setIsLoading(false)
    }
  }, [widgetId, apiBase, convId, isLoading])

  return { messages, sendMessage, isLoading }
}
