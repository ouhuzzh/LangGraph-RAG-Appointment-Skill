import { useEffect, useCallback } from "react";

/**
 * Global keyboard shortcuts for the app.
 *
 * Ctrl/Cmd + K  → Focus composer input
 * Ctrl/Cmd + Shift + C → Copy last AI reply
 * Escape       → Stop streaming (if active) or close search
 * Ctrl/Cmd + F → Open search
 * Ctrl/Cmd + E → Export chat
 */
export function useKeyboardShortcuts({
  isStreaming,
  onStop,
  composerRef,
  lastAssistantMessage,
  onOpenSearch,
  onExport,
}) {
  const handleKeyDown = useCallback(
    (e) => {
      const mod = e.metaKey || e.ctrlKey;

      // Ctrl/Cmd + K → Focus composer
      if (mod && e.key === "k") {
        e.preventDefault();
        composerRef?.current?.focus();
        return;
      }

      // Ctrl/Cmd + Shift + C → Copy last AI reply
      if (mod && e.shiftKey && e.key === "C") {
        e.preventDefault();
        if (lastAssistantMessage?.content) {
          navigator.clipboard.writeText(lastAssistantMessage.content);
        }
        return;
      }

      // Ctrl/Cmd + F → Open search
      if (mod && e.key === "f") {
        e.preventDefault();
        onOpenSearch?.();
        return;
      }

      // Ctrl/Cmd + E → Export chat
      if (mod && e.key === "e") {
        e.preventDefault();
        onExport?.();
        return;
      }

      // Escape → Stop streaming
      if (e.key === "Escape" && isStreaming) {
        e.preventDefault();
        onStop?.();
        return;
      }
    },
    [isStreaming, onStop, composerRef, lastAssistantMessage, onOpenSearch, onExport],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
