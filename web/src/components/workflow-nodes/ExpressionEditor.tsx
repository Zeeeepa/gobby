/**
 * ExpressionEditor — Lightweight CodeMirror wrapper for inline expression
 * and command editing in the workflow property panel.
 *
 * Supports single-line (expressions) and multi-line (commands/templates) modes
 * with dark theme, placeholder text, and basic variable autocompletion.
 */

import { useRef, useEffect, useCallback } from 'react'
import { EditorView, keymap, placeholder as cmPlaceholder } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { syntaxHighlighting, defaultHighlightStyle, bracketMatching } from '@codemirror/language'
import { oneDark } from '@codemirror/theme-one-dark'
import { autocompletion, type CompletionContext, type CompletionResult } from '@codemirror/autocomplete'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExpressionEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  /** Single-line mode suppresses Enter key (default: true) */
  singleLine?: boolean
  /** Language hint for syntax highlighting */
  language?: 'expression' | 'command' | 'template'
}

// ---------------------------------------------------------------------------
// Autocompletion
// ---------------------------------------------------------------------------

const WORKFLOW_VARIABLES = [
  { label: 'session.id', type: 'variable', detail: 'Current session ID' },
  { label: 'session.agent', type: 'variable', detail: 'Active agent name' },
  { label: 'session.source', type: 'variable', detail: 'Session source (cli/api)' },
  { label: 'task.id', type: 'variable', detail: 'Current task ID' },
  { label: 'task.title', type: 'variable', detail: 'Task title' },
  { label: 'task.status', type: 'variable', detail: 'Task status' },
  { label: 'workflow.name', type: 'variable', detail: 'Workflow name' },
  { label: 'workflow.type', type: 'variable', detail: 'Workflow or pipeline' },
  { label: 'workflow.step', type: 'variable', detail: 'Current step name' },
  { label: 'steps.all_complete', type: 'keyword', detail: 'All steps finished' },
  { label: 'steps.current', type: 'variable', detail: 'Current step object' },
  { label: 'tool.name', type: 'variable', detail: 'Last tool name' },
  { label: 'tool.result', type: 'variable', detail: 'Last tool result' },
  { label: 'event.type', type: 'variable', detail: 'Event type' },
]

function workflowCompletions(context: CompletionContext): CompletionResult | null {
  const word = context.matchBefore(/[\w.]*/)
  if (!word || (word.from === word.to && !context.explicit)) return null
  return {
    from: word.from,
    options: WORKFLOW_VARIABLES,
    validFor: /^[\w.]*$/,
  }
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

const compactTheme = EditorView.theme({
  '&': {
    fontSize: '12px',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: '4px',
  },
  '&.cm-focused': {
    outline: 'none',
    borderColor: 'var(--accent)',
  },
  '.cm-scroller': {
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
    overflow: 'auto',
    padding: '4px 8px',
  },
  '.cm-content': {
    caretColor: 'var(--text-primary)',
    padding: '0',
  },
  '.cm-line': {
    padding: '0',
  },
  '.cm-placeholder': {
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
  },
  '.cm-tooltip.cm-tooltip-autocomplete': {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    fontSize: '12px',
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li': {
    padding: '3px 8px',
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': {
    background: 'var(--accent)',
    color: '#fff',
  },
  '.cm-completionLabel': {
    color: 'var(--text-primary)',
  },
  '.cm-completionDetail': {
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
    marginLeft: '8px',
  },
})

// ---------------------------------------------------------------------------
// Single-line enforcement
// ---------------------------------------------------------------------------

const singleLineFilter = EditorState.transactionFilter.of((tr) => {
  if (!tr.docChanged) return tr
  const newDoc = tr.newDoc.toString()
  if (newDoc.includes('\n')) {
    // Replace newlines with spaces
    return {
      ...tr,
      changes: { from: 0, to: tr.startState.doc.length, insert: newDoc.replace(/\n/g, ' ') },
    }
  }
  return tr
})

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExpressionEditor({
  value,
  onChange,
  placeholder = '',
  singleLine = true,
  language: _language = 'expression',
}: ExpressionEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const createView = useCallback(() => {
    if (!containerRef.current) return

    const extensions = [
      history(),
      bracketMatching(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      oneDark,
      compactTheme,
      keymap.of([...defaultKeymap, ...historyKeymap]),
      autocompletion({ override: [workflowCompletions] }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          onChangeRef.current(update.state.doc.toString())
        }
      }),
    ]

    if (placeholder) {
      extensions.push(cmPlaceholder(placeholder))
    }

    if (singleLine) {
      extensions.push(singleLineFilter)
      // Suppress Enter key
      extensions.push(
        keymap.of([{ key: 'Enter', run: () => true }]),
      )
    }

    const state = EditorState.create({
      doc: value,
      extensions,
    })

    const view = new EditorView({
      state,
      parent: containerRef.current,
    })

    viewRef.current = view
  }, [placeholder, singleLine]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    createView()
    return () => {
      viewRef.current?.destroy()
      viewRef.current = null
    }
  }, [createView])

  // Sync external value changes
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current !== value) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      })
    }
  }, [value])

  return (
    <div
      ref={containerRef}
      className="expression-editor"
      style={singleLine ? { maxHeight: '28px', overflow: 'hidden' } : { minHeight: '60px' }}
    />
  )
}
