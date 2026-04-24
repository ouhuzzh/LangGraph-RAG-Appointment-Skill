import React from "react";
import { Menu } from "lucide-react";

const ChatHeader = React.memo(function ChatHeader({
  threadId,
  isConnected,
  onMenuClick,
}) {
  return (
    <header className="chat-header">
      <button
        type="button"
        className="icon-button chat-header__menu"
        onClick={onMenuClick}
        aria-label="打开菜单"
      >
        <Menu size={20} />
      </button>

      <div className="chat-header__title">
        <span className="eyebrow">Medical AI</span>
        <h2>直接说你的问题</h2>
      </div>

      <div className="chat-header__meta">
        <span
          className={`conn-dot ${isConnected ? "conn-dot--on" : "conn-dot--off"}`}
          title={isConnected ? "后端已连接" : "后端连接失败"}
        />
        <div className="thread-chip" title={threadId}>
          {threadId ? `thread ${threadId.slice(0, 8)}` : "connecting…"}
        </div>
      </div>
    </header>
  );
});

export default ChatHeader;
