import React from 'react'

/**
 * Single message row.
 * User messages: right-aligned blue bubble.
 * Assistant messages: left-aligned gray, pre-wrap for code/line breaks.
 * While streaming, `typing` is true and content may be empty (shows "...").
 */
export default function Message({ role, content, typing }) {
  const className = `message ${role}${typing ? ' typing' : ''}`
  return (
    <div className={className}>
      {typing && !content ? '...' : content}
    </div>
  )
}
