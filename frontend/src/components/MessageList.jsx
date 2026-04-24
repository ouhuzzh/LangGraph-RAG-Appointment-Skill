import React, { useEffect, useRef, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import EmptyState from "./EmptyState";

const SCROLL_THRESHOLD = 80; // px from bottom to count as "at bottom"

const MessageList = React.memo(function MessageList({ messages, isStreaming, onSendMessage }) {
  const containerRef = useRef(null);
  const endRef = useRef(null);
  const userScrolledUpRef = useRef(false);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback((behavior = "smooth") => {
    endRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  // Detect manual scroll up
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      userScrolledUpRef.current = !isAtBottom();
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isAtBottom]);

  // When new message arrives (user sends) — always jump
  const prevLenRef = useRef(messages.length);
  useEffect(() => {
    const prevLen = prevLenRef.current;
    prevLenRef.current = messages.length;
    if (messages.length > prevLen) {
      // New message added — always scroll (instant for user msg, smooth for AI)
      userScrolledUpRef.current = false;
      scrollToBottom("smooth");
    }
  }, [messages.length, scrollToBottom]);

  // During streaming — follow bottom only if user hasn't scrolled up
  useEffect(() => {
    if (!isStreaming) return;
    if (!userScrolledUpRef.current) {
      scrollToBottom("instant");
    }
  });

  // When streaming ends — scroll to bottom once
  const prevStreamingRef = useRef(isStreaming);
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      userScrolledUpRef.current = false;
      scrollToBottom("smooth");
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, scrollToBottom]);

  return (
    <div className="message-list" ref={containerRef}>
      {messages.length === 0 ? (
        <EmptyState onSendMessage={onSendMessage} />
      ) : (
        messages.map((message, index) => {
          const isLastAssistant =
            message.role === "assistant" && index === messages.length - 1;
          return (
            <MessageBubble
              key={message.id ?? `${message.role}-${index}`}
              message={message}
              isStreaming={isStreaming}
              isLastAssistant={isLastAssistant}
              onAction={onSendMessage}
            />
          );
        })
      )}
      <div ref={endRef} style={{ height: 1 }} />
    </div>
  );
});

export default MessageList;
