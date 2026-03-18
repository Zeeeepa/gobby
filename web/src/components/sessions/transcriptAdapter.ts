import type { ChatMessage, ToolCall } from '../../types/chat'
import type { SessionMessage } from '../../hooks/useSessionDetail'

function extractServerName(toolName: string): string {
  const parts = toolName.split('__')
  if (parts.length >= 3 && parts[0] === 'mcp') {
    return parts[1]
  }
  return ''
}

function tryParseJson(str: string | undefined): Record<string, unknown> | undefined {
  if (!str) return undefined
  try {
    const parsed = JSON.parse(str)
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

function tryParseResult(str: string | undefined): unknown {
  if (!str) return undefined
  try {
    return JSON.parse(str)
  } catch {
    return str
  }
}

/**
 * Detect if a user message is hook feedback (stop hook, rule enforcement, etc.)
 * These should be rendered as system messages, not "You" messages.
 */
function isHookFeedback(content: string): boolean {
  return /^Stop hook feedback:/.test(content) ||
    /^(Pre|Post)ToolUse hook/.test(content) ||
    /^UserPromptSubmit hook/.test(content)
}

/**
 * Convert Python repr single-quoted strings to JSON double-quoted strings.
 * Handles apostrophes inside values (e.g., "It's") by tracking string boundaries.
 */
function pythonReprToJson(s: string): string {
  let out = '', i = 0
  while (i < s.length) {
    if (s[i] === "'") {
      // Opening single-quote delimiter — convert to double quote
      out += '"'
      i++
      // Read string contents until closing single quote
      while (i < s.length && s[i] !== "'") {
        if (s[i] === '\\' && i + 1 < s.length && s[i + 1] === "'") {
          // Escaped apostrophe \' → just '
          out += "'"
          i += 2
        } else if (s[i] === '"') {
          // Escape existing double quotes inside the string
          out += '\\"'
          i++
        } else {
          out += s[i]
          i++
        }
      }
      out += '"' // closing quote
      i++ // skip closing '
    } else {
      out += s[i]
      i++
    }
  }
  return out
    .replace(/\bTrue\b/g, 'true')
    .replace(/\bFalse\b/g, 'false')
    .replace(/\bNone\b/g, 'null')
}

/**
 * Extract user-visible text from content that may be a serialized content block array.
 *
 * Claude API stores user messages as arrays of content blocks, e.g.:
 *   [{"type":"text","text":"actual prompt"}, {"type":"text","text":"<hook_context>..."}]
 * or Python repr:
 *   [{'text': 'actual prompt'}, {'text': '<hook_context>...'}]
 *
 * This extracts only the user-visible text, stripping hook_context, system-reminder,
 * and other injected blocks.
 */
function extractUserText(content: string): string | null {
  // Quick check: does this look like a serialized array?
  if (!content.startsWith('[') || !content.endsWith(']')) return null

  // Try JSON parse first
  let blocks: Array<{ type?: string; text?: string; content?: string }> | null = null
  try {
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) blocks = parsed
  } catch {
    // Try Python-style repr: single-quoted strings → double-quoted
    // Uses a character-by-character parser to handle apostrophes in values (e.g., "It's")
    try {
      const jsonified = pythonReprToJson(content)
      const parsed = JSON.parse(jsonified)
      if (Array.isArray(parsed)) blocks = parsed
    } catch {
      // Not a parseable content block array
    }
  }

  if (!blocks || blocks.length === 0) return null

  // Extract text from blocks, filtering out injected context
  const texts: string[] = []
  for (const block of blocks) {
    const text = block.text ?? block.content ?? ''
    if (!text) continue
    // Skip injected hook/system context
    if (text.includes('<hook_context>') || text.includes('</hook_context>')) continue
    if (text.includes('<system-reminder>') || text.includes('</system-reminder>')) continue
    if (text.includes('<system_instructions>') || text.includes('</system_instructions>')) continue
    texts.push(text)
  }

  // Return joined text, or empty string if all blocks were injected context.
  // null means "not a parseable content block array" (caller falls through).
  // Empty string means "parsed OK but nothing user-visible" (caller skips).
  return texts.length > 0 ? texts.join('\n\n') : ''
}

/** Helper: append a tool call to the current tool_chain block, or start a new one. */
function appendToolBlock(msg: ChatMessage, tc: ToolCall) {
  if (!msg.contentBlocks) msg.contentBlocks = []
  const last = msg.contentBlocks[msg.contentBlocks.length - 1]
  if (last?.type === 'tool_chain') {
    last.calls.push(tc)
  } else {
    msg.contentBlocks.push({ type: 'tool_chain', calls: [tc] })
  }
}

/**
 * Transforms SessionMessage[] from the session detail API into ChatMessage[]
 * compatible with the chat page's MessageItem component.
 *
 * Tool-use messages are grouped into the preceding assistant message's toolCalls array
 * rather than rendered as standalone entries.
 */
export function sessionMessagesToChatMessages(messages: SessionMessage[]): ChatMessage[] {
  const result: ChatMessage[] = []
  let lastAssistant: ChatMessage | null = null

  for (const msg of messages) {
    const content = msg.content?.trim() ?? ''

    // Tool-use messages: create ToolCall and attach to last assistant message
    if (msg.tool_name || msg.content_type === 'tool_use') {
      const toolName = msg.tool_name || 'unknown'
      const toolCall: ToolCall = {
        id: msg.tool_use_id || `tool-${msg.id}`,
        tool_name: toolName,
        server_name: extractServerName(toolName),
        status: 'completed',
        arguments: tryParseJson(msg.tool_input),
        result: tryParseResult(msg.tool_result),
      }
      if (lastAssistant) {
        lastAssistant.toolCalls = lastAssistant.toolCalls || []
        lastAssistant.toolCalls.push(toolCall)
        appendToolBlock(lastAssistant, toolCall)
      }
      continue
    }

    // Tool result messages: attach to the pending tool call on the last assistant
    if (msg.content_type === 'tool_result' || (msg.role === 'tool') || (msg.role === 'user' && msg.tool_use_id)) {
      if (lastAssistant?.toolCalls) {
        const match = msg.tool_use_id
          ? lastAssistant.toolCalls.find((tc) => tc.id === msg.tool_use_id)
          : lastAssistant.toolCalls.find((tc) => tc.status !== 'completed')
        if (match) {
          match.result = tryParseResult(content || msg.tool_result)
          match.status = 'completed'
          // Update in contentBlocks too
          if (lastAssistant.contentBlocks) {
            for (const block of lastAssistant.contentBlocks) {
              if (block.type === 'tool_chain') {
                const tcMatch = block.calls.find((c) => c.id === match.id)
                if (tcMatch) {
                  tcMatch.result = match.result
                  tcMatch.status = 'completed'
                }
              }
            }
          }
        }
      }
      continue
    }

    // Skip tool_result protocol messages (user-role messages containing tool_result JSON arrays)
    if (msg.role === 'user' && content.startsWith('[{') && content.includes('tool_result')) {
      continue
    }

    // Hook feedback messages → attach to last tool call if possible, else render as system
    if (msg.role === 'user' && isHookFeedback(content)) {
      if (lastAssistant?.toolCalls?.length) {
        const lastTc = lastAssistant.toolCalls[lastAssistant.toolCalls.length - 1]
        lastTc.error = content
        lastTc.status = 'error'
        // Update contentBlocks too
        if (lastAssistant.contentBlocks) {
          for (const block of lastAssistant.contentBlocks) {
            if (block.type === 'tool_chain') {
              const match = block.calls.find((c) => c.id === lastTc.id)
              if (match) {
                match.error = content
                match.status = 'error'
              }
            }
          }
        }
      } else {
        result.push({
          id: String(msg.id),
          role: 'system',
          content,
          timestamp: new Date(msg.timestamp),
        })
      }
      continue
    }

    // User messages with serialized content block arrays → extract user text
    if (msg.role === 'user' && content.startsWith('[')) {
      const extracted = extractUserText(content)
      if (extracted !== null) {
        if (!extracted.trim()) continue // All blocks were injected context, skip
        result.push({
          id: String(msg.id),
          role: 'user',
          content: extracted,
          timestamp: new Date(msg.timestamp),
        })
        continue
      }
    }

    // Assistant messages that are JSON arrays of tool_use blocks
    if (msg.role === 'assistant' && content.startsWith('[{') && content.includes('tool_use')) {
      try {
        const calls = JSON.parse(content) as Array<{
          type?: string
          id?: string
          name?: string
          input?: unknown
        }>
        const tools = calls.filter((c) => c.type === 'tool_use')
        if (tools.length > 0) {
          const toolCalls = tools.map((t) => ({
            id: t.id || `tool-${msg.id}-${t.name}`,
            tool_name: t.name || 'unknown',
            server_name: extractServerName(t.name || ''),
            status: 'completed' as const,
            arguments:
              typeof t.input === 'object' && t.input !== null
                ? (t.input as Record<string, unknown>)
                : undefined,
          }))
          const chatMsg: ChatMessage = {
            id: String(msg.id),
            role: 'assistant',
            content: '',
            timestamp: new Date(msg.timestamp),
            toolCalls,
            contentBlocks: [{ type: 'tool_chain', calls: [...toolCalls] }],
          }
          lastAssistant = chatMsg
          result.push(chatMsg)
          continue
        }
      } catch {
        // Fall through to normal message handling
      }
    }

    // Skip empty messages
    if (!content && msg.role === 'assistant') continue
    if (!content) continue

    const role: ChatMessage['role'] =
      msg.role === 'user' ? 'user' : msg.role === 'assistant' ? 'assistant' : 'system'

    const chatMsg: ChatMessage = {
      id: String(msg.id),
      role,
      content,
      timestamp: new Date(msg.timestamp),
    }

    if (role === 'assistant') {
      chatMsg.contentBlocks = [{ type: 'text', content }]
      lastAssistant = chatMsg
    }

    result.push(chatMsg)
  }

  return result
}
