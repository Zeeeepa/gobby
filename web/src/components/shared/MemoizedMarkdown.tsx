import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { marked } from "marked";
import { markdownComponents } from "./MarkdownComponents";

/**
 * A single memoized markdown block.
 * Once the content is finalized (not the last block during streaming),
 * it won't re-render even when later blocks change.
 */
const MemoizedBlock = memo(
  ({ content }: { content: string }) => (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  ),
  (prev, next) => prev.content === next.content,
);
MemoizedBlock.displayName = "MemoizedBlock";

/**
 * Split markdown into block-level tokens using marked's lexer,
 * then render each block as a memoized component.
 *
 * During streaming, only the last (incomplete) block re-renders;
 * all completed blocks are memoized and skip re-rendering.
 */
export function MemoizedMarkdown({
  content,
  id,
}: {
  content: string;
  id: string;
}) {
  const blocks = useMemo(() => {
    const tokens = marked.lexer(content);
    return tokens.map((token) => token.raw);
  }, [content]);

  return (
    <>
      {blocks.map((block, i) => (
        <MemoizedBlock key={`${id}-${i}`} content={block} />
      ))}
    </>
  );
}
