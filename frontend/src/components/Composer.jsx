import React, { useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";

const Composer = React.memo(function Composer({
  input,
  onChange,
  onSubmit,
  onStop,
  isStreaming,
  disabled,
}) {
  const textareaRef = useRef(null);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = 24;
    const minH = lineHeight + 26;
    const maxH = lineHeight * 4 + 26;
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minH), maxH)}px`;
  }

  useEffect(() => {
    autoResize();
  }, [input]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && input.trim() && !disabled) onSubmit();
    }
  }

  // Only accept plain text on paste (strip HTML/images)
  function handlePaste(e) {
    e.preventDefault();
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;
    const el = e.target;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const newVal = input.slice(0, start) + text + input.slice(end);
    onChange(newVal);
    // restore cursor after state update
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        const pos = start + text.length;
        textareaRef.current.selectionStart = pos;
        textareaRef.current.selectionEnd = pos;
      }
    });
  }

  const placeholder = isStreaming
    ? "AI 正在回复…"
    : "输入症状、医学问题或挂号需求… (Shift+Enter 换行)";

  return (
    <form
      className="composer"
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      aria-label="消息输入区"
    >
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => { onChange(e.target.value); }}
        onInput={autoResize}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={placeholder}
        rows={1}
        disabled={disabled}
        aria-label="输入消息"
      />
      {isStreaming ? (
        <button
          type="button"
          className="composer__btn composer__btn--stop"
          title="停止生成"
          aria-label="停止 AI 生成"
          onClick={onStop}
        >
          <Square size={18} />
        </button>
      ) : (
        <button
          type="submit"
          className="composer__btn composer__btn--send"
          disabled={!input.trim() || disabled}
          title="发送 (Enter)"
          aria-label="发送消息"
        >
          <Send size={18} />
        </button>
      )}
    </form>
  );
});

export default Composer;
