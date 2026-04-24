export function openChatStream({
  url,
  onMessage,
  onStatus,
  onFinal,
  onAppError,
  onConnectionError,
  doneRef,
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
    onConnectionError(event);
    source.close();
  };

  return source;
}
