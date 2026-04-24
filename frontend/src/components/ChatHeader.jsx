import React from "react";
import { Menu } from "lucide-react";

const ChatHeader = React.memo(function ChatHeader({
  threadId,
  isConnected,
  streamState,
  onMenuClick,
}) {
  const stateText = {
    connecting: "连接中",
    thinking: "思考中",
    generating: "生成中",
    stopped: "已停止",
    error: "需重试",
    done: "已完成",
    idle: "待命",
  }[streamState || "idle"];

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
        <div className="stream-chip">{stateText}</div>
        <div className="thread-chip" title={threadId}>
          {threadId ? `thread ${threadId.slice(0, 8)}` : "connecting…"}
        </div>
      </div>
    </header>
  );
});

export default ChatHeader;
