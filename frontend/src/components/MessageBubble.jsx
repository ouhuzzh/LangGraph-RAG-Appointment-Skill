import React from "react";
import MarkdownContent from "./MarkdownContent";
import ActionButtons from "./ActionButtons";
import TypingDots from "./TypingDots";

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
}) {
  const { role, content, timestamp, interrupted } = message;
  const isUser = role === "user";
  const isAssistant = role === "assistant";

  const showTypingDots = isAssistant && isLastAssistant && isStreaming && !content;
  const showActionButtons = isAssistant && !isStreaming && content;
  const timeStr = formatTime(timestamp);

  return (
    <article className={`message message--${role}`}>
      {isAssistant && (
        <div className="message__avatar" aria-hidden="true">
          <span className="avatar-dot" />
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
        {timeStr && (
          <time className={`message__time message__time--${role}`} dateTime={new Date(timestamp).toISOString()}>
            {timeStr}{interrupted ? " · 已停止" : ""}
          </time>
        )}
        {showActionButtons && (
          <ActionButtons content={content} onAction={onAction} />
        )}
      </div>
    </article>
  );
});

export default MessageBubble;
