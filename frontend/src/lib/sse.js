const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_MS = 1000;

export function openChatStream({
  url,
  onMessage,
  onStatus,
  onFinal,
  onAppError,
  onConnectionError,
  doneRef,
  reconnectAttempt = 0,
}) {
  const source = new EventSource(url);

  source.addEventListener("status", (event) => {
    onStatus?.(JSON.parse(event.data));
  });

  source.addEventListener("message", (event) => {
    onMessage(JSON.parse(event.data));
  });

  source.addEventListener("final", (event) => {
    doneRef.current = true;
    onFinal(JSON.parse(event.data));
    source.close();
  });

  source.addEventListener("app-error", (event) => {
    doneRef.current = true;
    onAppError(JSON.parse(event.data));
    source.close();
  });

  source.onerror = (event) => {
    if (doneRef.current || source.readyState === EventSource.CLOSED) {
      source.close();
      return;
    }

    // Attempt reconnection with exponential backoff
    if (reconnectAttempt < MAX_RECONNECT_ATTEMPTS) {
      source.close();
      const delay = RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt);
      setTimeout(() => {
        if (doneRef.current) return;
        openChatStream({
          url,
          onMessage,
          onStatus,
          onFinal,
          onAppError,
          onConnectionError,
          doneRef,
          reconnectAttempt: reconnectAttempt + 1,
        });
      }, delay);
      return;
    }

    onConnectionError(event);
    source.close();
  };

  return source;
}
