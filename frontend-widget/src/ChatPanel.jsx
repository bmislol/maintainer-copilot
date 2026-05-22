import React, { useEffect, useRef, useState } from 'react'
import Message from './Message.jsx'
import { useSSEChat } from './useSSEChat.js'

/**
 * Expanded chat panel: header + scrollable message list + input row.
 * Greeting is injected as the first assistant message so it appears
 * immediately without a network round-trip.
 */
export default function ChatPanel({ widgetId, apiBase, config, onClose }) {
  const [input, setInput] = useState('')
  const { messages, sendMessage, isLoading } = useSSEChat(widgetId, apiBase)
  const messagesEndRef = useRef(null)

  // Auto-scroll to latest message.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Show greeting until the user sends the first message.
  const displayMessages =
    messages.length === 0
      ? [{ id: 'greeting', role: 'assistant', content: config.greeting }]
      : messages

  const handleSend = () => {
    const text = input.trim()
    if (text && !isLoading) {
      sendMessage(text)
      setInput('')
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Maintainer's Copilot</h3>
        <button className="close-btn" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      <div className="messages">
        {displayMessages.map((msg, i) => (
          <Message
            key={msg.id ?? i}
            role={msg.role}
            content={msg.content}
            typing={msg.typing}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-row">
        <input
          type="text"
          placeholder="Ask about an issue…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          aria-label="Message input"
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  )
}
