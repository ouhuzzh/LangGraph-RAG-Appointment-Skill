import React, { useEffect, useRef } from "react";
import { Search, X, ChevronUp, ChevronDown } from "lucide-react";

const SearchBar = React.memo(function SearchBar({
  query,
  matchCount,
  currentIndex,
  onQueryChange,
  onClose,
  onNext,
  onPrev,
}) {
  const inputRef = useRef(null);

  useEffect(() => {
    if (inputRef.current) inputRef.current.focus();
  }, []);

  function handleKeyDown(e) {
    if (e.key === "Enter") {
      if (e.shiftKey) onPrev();
      else onNext();
    }
    if (e.key === "Escape") onClose();
  }

  return (
    <div className="search-bar">
      <Search size={16} className="search-bar__icon" />
      <input
        ref={inputRef}
        type="text"
        className="search-bar__input"
        placeholder="搜索聊天记录…"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="搜索聊天记录"
      />
      {query && (
        <span className="search-bar__count">
          {matchCount > 0 ? `${currentIndex + 1} / ${matchCount}` : "无结果"}
        </span>
      )}
      {matchCount > 0 && (
        <>
          <button
            type="button"
            className="search-bar__nav"
            onClick={onPrev}
            title="上一个 (Shift+Enter)"
            aria-label="上一个匹配"
          >
            <ChevronUp size={16} />
          </button>
          <button
            type="button"
            className="search-bar__nav"
            onClick={onNext}
            title="下一个 (Enter)"
            aria-label="下一个匹配"
          >
            <ChevronDown size={16} />
          </button>
        </>
      )}
      <button
        type="button"
        className="search-bar__close"
        onClick={onClose}
        title="关闭 (Escape)"
        aria-label="关闭搜索"
      >
        <X size={16} />
      </button>
    </div>
  );
});

export default SearchBar;
