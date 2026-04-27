import ChatHeader from "../components/ChatHeader";
import MessageList from "../components/MessageList";
import Composer from "../components/Composer";
import SearchBar from "../components/SearchBar";

export default function ChatPage({
  chat,
  isConnected,
  onMenuClick,
}) {
  const { search, onExport } = chat;

  return (
    <section className="chat-shell">
      <ChatHeader
        threadId={chat.threadId}
        isConnected={isConnected}
        streamState={chat.streamState}
        onMenuClick={onMenuClick}
        onOpenSearch={search.openSearch}
        onExport={onExport}
      />

      {search.isOpen && (
        <SearchBar
          query={search.query}
          matchCount={search.matchCount}
          currentIndex={search.currentIndex}
          onQueryChange={search.setQuery}
          onClose={search.closeSearch}
          onNext={search.goNext}
          onPrev={search.goPrev}
        />
      )}

      <MessageList
        messages={chat.messages}
        isStreaming={chat.isStreaming}
        isLoadingHistory={chat.isLoadingHistory}
        onSendMessage={chat.sendMessage}
        searchQuery={search.query}
        currentMatchId={search.currentMatch?.messageId}
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
        ref={chat.composerRef}
        input={chat.input}
        onChange={chat.setInput}
        onSubmit={() => chat.sendMessage(chat.input)}
        onStop={chat.stopStreaming}
        isStreaming={chat.isStreaming}
        disabled={!chat.threadId}
        streamState={chat.streamState}
      />
    </section>
  );
}
