import { useState, useEffect, useCallback } from 'react'
import type { Channel, CommsMessage, MessageFilters } from '../../hooks/useIntegrations'
import { PlatformIcon } from './IntegrationsPage'
import type { ChannelType } from '../../hooks/useIntegrations'
import './IntegrationsPage.css'

interface MessageListProps {
  channels: Channel[]
  messages: CommsMessage[]
  filters: MessageFilters
  onFiltersChange: (filters: Partial<MessageFilters>) => void
  onFetchMessages: (filters?: Partial<MessageFilters>) => void
}

export function MessageList({ channels, messages, filters, onFiltersChange, onFetchMessages }: MessageListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Fetch on mount and when filters change
  useEffect(() => {
    onFetchMessages()
  }, [filters.channelId, filters.direction, filters.offset, onFetchMessages])

  const handleFilterChange = useCallback((update: Partial<MessageFilters>) => {
    onFiltersChange({ ...update, offset: 0 })
  }, [onFiltersChange])

  const channelMap = new Map(channels.map(c => [c.id, c]))

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso)
      const now = new Date()
      const diff = now.getTime() - d.getTime()
      const mins = Math.floor(diff / 60000)
      if (mins < 1) return 'just now'
      if (mins < 60) return `${mins}m ago`
      const hours = Math.floor(mins / 60)
      if (hours < 24) return `${hours}h ago`
      const days = Math.floor(hours / 24)
      return `${days}d ago`
    } catch {
      return iso
    }
  }

  const hasMore = messages.length >= filters.limit

  return (
    <div className="intg-msg-container">
      {/* Filter bar */}
      <div className="intg-msg-filter-bar">
        <select
          className="intg-msg-select"
          value={filters.channelId || ''}
          onChange={e => handleFilterChange({ channelId: e.target.value || null })}
        >
          <option value="">All Channels</option>
          {channels.map(ch => (
            <option key={ch.id} value={ch.id}>{ch.name}</option>
          ))}
        </select>
        <select
          className="intg-msg-select"
          value={filters.direction || ''}
          onChange={e => handleFilterChange({ direction: (e.target.value || null) as MessageFilters['direction'] })}
        >
          <option value="">All Directions</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
        </select>
      </div>

      {/* Message list */}
      {messages.length === 0 ? (
        <div className="intg-msg-empty">No messages yet</div>
      ) : (
        <div className="intg-msg-list">
          {messages.map(msg => {
            const ch = channelMap.get(msg.channel_id)
            const isExpanded = expandedId === msg.id

            return (
              <div
                key={msg.id}
                className={`intg-msg-row ${isExpanded ? 'intg-msg-row--expanded' : ''}`}
                onClick={() => setExpandedId(isExpanded ? null : msg.id)}
              >
                <div className="intg-msg-summary">
                  <span className="intg-msg-timestamp">{formatTime(msg.created_at)}</span>
                  {ch && (
                    <span className="intg-msg-channel">
                      <PlatformIcon type={ch.channel_type as ChannelType} size={12} />
                      {' '}{ch.name}
                    </span>
                  )}
                  <span className={`intg-msg-direction intg-msg-direction--${msg.direction}`}>
                    {msg.direction === 'inbound' ? '\u2193' : '\u2191'}
                  </span>
                  <span className="intg-msg-content">
                    {msg.content.length > 120 ? msg.content.slice(0, 120) + '...' : msg.content}
                  </span>
                  <span className={`intg-msg-status-badge intg-msg-status--${msg.status}`}>
                    {msg.status}
                  </span>
                </div>

                {isExpanded && (
                  <div className="intg-msg-detail">
                    <pre className="intg-msg-full-content">{msg.content}</pre>
                    {msg.error && (
                      <div className="intg-msg-error">Error: {msg.error}</div>
                    )}
                    <div className="intg-msg-meta">
                      {msg.platform_message_id && (
                        <span>Platform ID: {msg.platform_message_id}</span>
                      )}
                      {msg.platform_thread_id && (
                        <span>Thread: {msg.platform_thread_id}</span>
                      )}
                      {msg.session_id && (
                        <span>Session: {msg.session_id}</span>
                      )}
                      {Object.keys(msg.metadata_json).length > 0 && (
                        <details>
                          <summary>Metadata</summary>
                          <pre className="intg-msg-metadata-json">
                            {JSON.stringify(msg.metadata_json, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {(filters.offset > 0 || hasMore) && (
        <div className="intg-msg-pagination">
          <button
            className="intg-form-cancel"
            disabled={filters.offset === 0}
            onClick={() => onFiltersChange({ offset: Math.max(0, filters.offset - filters.limit) })}
          >
            Previous
          </button>
          <span className="intg-msg-page-info">
            Showing {filters.offset + 1}-{filters.offset + messages.length} messages
          </span>
          <button
            className="intg-form-cancel"
            disabled={!hasMore}
            onClick={() => onFiltersChange({ offset: filters.offset + filters.limit })}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
