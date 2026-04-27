import React, { useEffect, useRef, useCallback, useState } from "react";
import MessageBubble from "./MessageBubble";
import EmptyState from "./EmptyState";
import SkeletonLoader from "./SkeletonLoader";
import { ArrowDown } from "lucide-react";

const SCROLL_THRESHOLD = 80;

const MessageList = React.memo(function MessageList({ messages, isStreaming, isLoadingHistory, onSendMessage, searchQuery, currentMatchId }) {
  const containerRef = useRef(null);
  const endRef = useRef(null);
  const userScrolledUpRef = useRef(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback((behavior = "smooth") => {
    endRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const scrolledUp = !isAtBottom();
      userScrolledUpRef.current = scrolledUp;
      setShowScrollBtn(scrolledUp);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isAtBottom]);

  const prevLenRef = useRef(messages.length);
  useEffect(() => {
    const prevLen = prevLenRef.current;
    prevLenRef.current = messages.length;
    if (messages.length > prevLen) {
      userScrolledUpRef.current = false;
      setShowScrollBtn(false);
      scrollToBottom("smooth");
    }
  }, [messages.length, scrollToBottom]);

  useEffect(() => {
    if (!isStreaming) return;
    const raf = requestAnimationFrame(() => {
      if (!userScrolledUpRef.current) {
        scrollToBottom("instant");
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [isStreaming, messages, scrollToBottom]);

  const prevStreamingRef = useRef(isStreaming);
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      userScrolledUpRef.current = false;
      setShowScrollBtn(false);
      scrollToBottom("smooth");
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, scrollToBottom]);

  return (
    <div className="message-list-wrapper">
      <div className="message-list" ref={containerRef}>
        {isLoadingHistory && messages.length === 0 ? (
          <SkeletonLoader rows={3} />
        ) : messages.length === 0 ? (
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
                searchQuery={searchQuery}
                isSearchMatch={message.id === currentMatchId}
              />
            );
          })
        )}
        <div ref={endRef} style={{ height: 1 }} />
      </div>
      {showScrollBtn && (
        <button
          type="button"
          className="scroll-to-bottom"
          onClick={() => { userScrolledUpRef.current = false; setShowScrollBtn(false); scrollToBottom("smooth"); }}
          aria-label="滚动到底部"
        >
          <ArrowDown size={16} />
        </button>
      )}
    </div>
  );
});

export default MessageList;
