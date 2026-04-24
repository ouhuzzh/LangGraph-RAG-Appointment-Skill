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

