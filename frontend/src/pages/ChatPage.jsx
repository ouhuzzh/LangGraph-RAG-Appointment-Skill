import ChatHeader from "../components/ChatHeader";
import MessageList from "../components/MessageList";
import Composer from "../components/Composer";

export default function ChatPage({
  chat,
  isConnected,
  onMenuClick,
}) {
  return (
    <section className="chat-shell">
      <ChatHeader
        threadId={chat.threadId}
        isConnected={isConnected}
        streamState={chat.streamState}
        onMenuClick={onMenuClick}
      />

      <MessageList
        messages={chat.messages}
        isStreaming={chat.isStreaming}
        onSendMessage={chat.sendMessage}
      />

      {chat.error && (
        <div className="error-bar" role="alert">
          <span>{chat.error}</span>
          <div className="error-bar__actions">
            {chat.lastUserMessage && (
              <button
                type="button"
                className="error-bar__retry"
                onClick={chat.retryLastMessage}
                disabled={chat.isStreaming}
              >
                重试
              </button>
            )}
            <button
              type="button"
              className="error-bar__close"
              onClick={() => chat.setError("")}
              aria-label="关闭错误提示"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <Composer
        input={chat.input}
        onChange={chat.setInput}
        onSubmit={chat.sendMessage}
        onStop={chat.stopStreaming}
        isStreaming={chat.isStreaming}
        disabled={!chat.threadId}
        streamState={chat.streamState}
      />
    </section>
  );
}
