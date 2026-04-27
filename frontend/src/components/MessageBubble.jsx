import React, { useState, useCallback } from "react";
import MarkdownContent from "./MarkdownContent";
import ActionButtons from "./ActionButtons";
import TypingDots from "./TypingDots";
import XinyuLogo from "./XinyuLogo";
import UserAvatar from "./UserAvatar";
import { Copy, Check } from "lucide-react";

function formatTime(timestamp) {
  if (!timestamp) return "";
  const d = new Date(timestamp);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  return `${h}:${m}`;
}

const MessageBubble = React.memo(function MessageBubble({
  message,
  isStreaming,
  isLastAssistant,
  onAction,
  searchQuery,
  isSearchMatch,
}) {
  const { role, content, timestamp, interrupted } = message;
  const isUser = role === "user";
  const isAssistant = role === "assistant";

  const showTypingDots = isAssistant && isLastAssistant && isStreaming && !content;
  const showActionButtons = isAssistant && !isStreaming && content;
  const timeStr = formatTime(timestamp);
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }, [content]);

  return (
    <article className={`message message--${role}${isSearchMatch ? " message--search-match" : ""}`}>
      {isAssistant && (
        <div className="message__avatar" aria-hidden="true" title="心语医疗 AI">
          <XinyuLogo size={28} />
        </div>
      )}
      {isUser && (
        <div className="message__avatar message__avatar--user" aria-hidden="true" title="我">
          <UserAvatar size={28} />
        </div>
      )}
      <div className="message__column">
        <div className={`bubble bubble--${role}`}>
          {isUser && <span className="bubble__text">{content}</span>}
          {isAssistant && (
            showTypingDots
              ? <TypingDots />
              : <MarkdownContent content={content} isStreaming={isLastAssistant && isStreaming} />
          )}
        </div>

        <div className={`message__footer message__footer--${role}`}>
          {timeStr && (
            <time className={`message__time message__time--${role}`} dateTime={new Date(timestamp).toISOString()}>
              {timeStr}{interrupted ? " · 已停止" : ""}
            </time>
          )}
          {isAssistant && !isStreaming && content && (
            <button
              type="button"
              className="copy-btn"
              onClick={handleCopy}
              title={copied ? "已复制" : "复制回复"}
              aria-label={copied ? "已复制" : "复制回复"}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span>{copied ? "已复制" : "复制"}</span>
            </button>
          )}
        </div>

        {showActionButtons && (
          <ActionButtons content={content} onAction={onAction} />
        )}
      </div>
    </article>
  );
});

export default MessageBubble;
