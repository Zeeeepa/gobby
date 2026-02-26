/**
 * Buffers streaming text and emits complete sentences for TTS.
 *
 * Splits on sentence-ending punctuation (.!?\n) followed by whitespace.
 * Ported from src/gobby/voice/sentence_buffer.py (now deleted).
 */
export class SentenceBuffer {
  private buffer = ''

  /** Add streaming text. Returns any complete sentences found. */
  add(text: string): string[] {
    this.buffer += text
    const sentences: string[] = []

    // Split on sentence boundaries: punctuation followed by whitespace
    const re = /(?<=[.!?\n])\s+/
    let match: RegExpExecArray | null
    while ((match = re.exec(this.buffer)) !== null) {
      const sentence = this.buffer.slice(0, match.index).trim()
      if (sentence) {
        sentences.push(sentence)
      }
      this.buffer = this.buffer.slice(match.index + match[0].length)
    }

    return sentences
  }

  /** Flush remaining buffered text. Returns null if empty. */
  flush(): string | null {
    const text = this.buffer.trim()
    this.buffer = ''
    return text || null
  }

  /** Reset the buffer without returning content. */
  clear(): void {
    this.buffer = ''
  }
}
