import { useState } from "react";
import { ToolCallDisplay } from "./ToolCallDisplay";
import { MemoizedMarkdown } from "./MemoizedMarkdown";

export interface ToolCall {
  id: string;
  tool_name: string;
  server_name: string;
  status: "calling" | "completed" | "error";
  arguments?: Record<string, unknown>;
  result?: unknown;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  thinkingContent?: string;
}

interface MessageProps {
  message: ChatMessage;
  isStreaming?: boolean;
  isThinking?: boolean;
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void;
}

export function Message({
  message,
  isStreaming = false,
  isThinking = false,
  onRespondToQuestion,
}: MessageProps) {
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const isCommandResult =
    message.role === "system" && message.toolCalls?.length && !message.content;
  const isModelSwitch =
    message.role === "system" && message.id.startsWith("model-switch-");

  return (
    <div
      className={`message message-${message.role}${isCommandResult ? " message-command" : ""}${isModelSwitch ? " message-model-switch" : ""}`}
    >
      <div className="message-header">
        <span className="message-role">
          {message.role === "assistant" && (
            <img src="/logo.png" alt="" className="message-role-logo" />
          )}
          {message.role === "user"
            ? "You"
            : message.role === "assistant"
              ? "Gobby"
              : "System"}
        </span>
        <span className="message-time">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
      {isThinking && !message.content && (
        <div className="thinking-indicator">
          <span className="thinking-spinner" />
          <span className="thinking-text">Gobby is thinking...</span>
        </div>
      )}
      {message.thinkingContent && (
        <div
          className="thinking-block"
          onClick={() => setThinkingExpanded(!thinkingExpanded)}
        >
          <div className="thinking-block-header">
            <span className="thinking-block-expand">
              {thinkingExpanded ? "\u25bc" : "\u25b6"}
            </span>
            <span className="thinking-block-label">Thinking</span>
          </div>
          {thinkingExpanded && (
            <div
              className="thinking-block-content"
              onClick={(e) => e.stopPropagation()}
            >
              <MemoizedMarkdown
                content={message.thinkingContent}
                id={`${message.id}-thinking`}
              />
            </div>
          )}
        </div>
      )}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <ToolCallDisplay toolCalls={message.toolCalls} onRespond={onRespondToQuestion} />
      )}
      <div className="message-content">
        <MemoizedMarkdown content={message.content} id={message.id} />
        {isStreaming && <span className="cursor" />}
      </div>
    </div>
  );
}
