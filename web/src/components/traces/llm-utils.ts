import type { SpanRecord } from '../../hooks/useTraces'

export interface LLMAttributes {
  system: string
  model: string
  promptTokens: number
  completionTokens: number
  prompt?: string
  completion?: string
}

export function isLLMSpan(span: SpanRecord): boolean {
  if (!span.attributes_json) return false
  try {
    const attrs = JSON.parse(span.attributes_json)
    return !!attrs['gen_ai.system']
  } catch {
    return false
  }
}

export function parseLLMAttributes(attributesJson: string | null): LLMAttributes | null {
  if (!attributesJson) return null
  try {
    const attrs = JSON.parse(attributesJson)
    if (!attrs['gen_ai.system']) return null
    return {
      system: attrs['gen_ai.system'],
      model: attrs['gen_ai.request.model'] || 'unknown',
      promptTokens: Number(attrs['gen_ai.usage.prompt_tokens'] || 0),
      completionTokens: Number(attrs['gen_ai.usage.completion_tokens'] || 0),
      prompt: attrs['gen_ai.prompt'] || undefined,
      completion: attrs['gen_ai.completion'] || undefined,
    }
  } catch {
    return null
  }
}

export function formatTokenCount(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '0'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
