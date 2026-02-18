import { memo, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { marked } from 'marked'
import { codeBlockComponents } from './CodeBlock'

const MemoizedBlock = memo(
  ({ content }: { content: string }) => (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={codeBlockComponents}>
      {content}
    </ReactMarkdown>
  ),
  (prev, next) => prev.content === next.content
)
MemoizedBlock.displayName = 'MemoizedBlock'

export function Markdown({ content, id }: { content: string; id: string }) {
  const blocks = useMemo(() => {
    const tokens = marked.lexer(content)
    return tokens.map((token) => token.raw)
  }, [content])

  return (
    <>
      {blocks.map((block, i) => (
        <MemoizedBlock key={`${id}-${i}`} content={block} />
      ))}
    </>
  )
}
