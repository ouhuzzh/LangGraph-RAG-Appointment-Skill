const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const browserApiBaseUrl =
  typeof window !== "undefined" && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://127.0.0.1:8000";
const fallbackApiBaseUrl = "http://127.0.0.1:8000";

export function initialApiBaseUrl() {
  return configuredApiBaseUrl || browserApiBaseUrl;
}

async function readJson(response) {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function apiFetchJson(path, options, apiBaseUrl, onFallback) {
  const firstUrl = `${apiBaseUrl}${path}`;
  try {
    return await readJson(await fetch(firstUrl, options));
  } catch (err) {
    if (configuredApiBaseUrl || apiBaseUrl === fallbackApiBaseUrl) {
      throw err;
    }
    const fallbackUrl = `${fallbackApiBaseUrl}${path}`;
    const data = await readJson(await fetch(fallbackUrl, options));
    onFallback?.(fallbackApiBaseUrl);
    return data;
  }
}

export function chatStreamUrl(apiBaseUrl, threadId, message) {
  return `${apiBaseUrl}/api/chat/stream?thread_id=${encodeURIComponent(threadId)}&message=${encodeURIComponent(message)}`;
}

export function createSession(apiBaseUrl, onFallback, threadId) {
  return apiFetchJson(
    "/api/chat/session",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(threadId ? { thread_id: threadId } : {}),
    },
    apiBaseUrl,
    onFallback,
  );
}

export function fetchChatHistory(apiBaseUrl, onFallback, threadId) {
  return apiFetchJson(
    `/api/chat/history?thread_id=${encodeURIComponent(threadId)}`,
    undefined,
    apiBaseUrl,
    onFallback,
  );
}

export function clearChatSession(apiBaseUrl, onFallback, threadId) {
  return apiFetchJson(
    "/api/chat/clear",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId }),
    },
    apiBaseUrl,
    onFallback,
  );
}

export function fetchSystemStatus(apiBaseUrl, onFallback) {
  return apiFetchJson("/api/system/status", undefined, apiBaseUrl, onFallback);
}

export function fetchDocumentsStatus(apiBaseUrl, onFallback) {
  return apiFetchJson("/api/documents/status", undefined, apiBaseUrl, onFallback);
}

export function fetchDocumentList(apiBaseUrl, onFallback) {
  return apiFetchJson("/api/documents/list", undefined, apiBaseUrl, onFallback);
}

export function fetchDocumentTasks(apiBaseUrl, onFallback) {
  return apiFetchJson("/api/documents/tasks", undefined, apiBaseUrl, onFallback);
}

export function fetchDocumentSources(apiBaseUrl, onFallback) {
  return apiFetchJson("/api/documents/sources", undefined, apiBaseUrl, onFallback);
}

export function uploadDocuments(apiBaseUrl, onFallback, files) {
  const formData = new FormData();
  Array.from(files || []).forEach((file) => formData.append("files", file));
  return apiFetchJson(
    "/api/documents/upload",
    {
      method: "POST",
      body: formData,
    },
    apiBaseUrl,
    onFallback,
  );
}

export function syncOfficialDocuments(apiBaseUrl, onFallback, source, limit) {
  return apiFetchJson(
    "/api/documents/sync-official",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, limit }),
    },
    apiBaseUrl,
    onFallback,
  );
}
