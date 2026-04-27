import { useState, useCallback, useMemo } from "react";

export function useSearch(messages = []) {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);

  const normalizedQuery = query.trim().toLowerCase();

  const matches = useMemo(() => {
    if (!normalizedQuery) return [];
    const results = [];
    messages.forEach((msg, idx) => {
      if (msg.content && msg.content.toLowerCase().includes(normalizedQuery)) {
        results.push({ messageId: msg.id, index: idx, role: msg.role });
      }
    });
    return results;
  }, [messages, normalizedQuery]);

  const matchCount = matches.length;

  const currentMatch = useMemo(() => {
    if (matchCount === 0) return null;
    return matches[Math.min(currentIndex, matchCount - 1)];
  }, [matches, currentIndex, matchCount]);

  const openSearch = useCallback(() => {
    setIsOpen(true);
    setQuery("");
    setCurrentIndex(0);
  }, []);

  const closeSearch = useCallback(() => {
    setIsOpen(false);
    setQuery("");
    setCurrentIndex(0);
  }, []);

  const goNext = useCallback(() => {
    if (matchCount === 0) return;
    setCurrentIndex((prev) => (prev + 1) % matchCount);
  }, [matchCount]);

  const goPrev = useCallback(() => {
    if (matchCount === 0) return;
    setCurrentIndex((prev) => (prev - 1 + matchCount) % matchCount);
  }, [matchCount]);

  const handleQueryChange = useCallback((value) => {
    setQuery(value);
    setCurrentIndex(0);
  }, []);

  return {
    query,
    isOpen,
    matchCount,
    currentIndex,
    currentMatch,
    openSearch,
    closeSearch,
    goNext,
    goPrev,
    setQuery: handleQueryChange,
  };
}
