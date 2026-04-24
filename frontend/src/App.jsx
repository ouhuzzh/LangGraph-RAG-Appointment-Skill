import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import ClearConfirmDialog from "./components/ClearConfirmDialog";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const browserApiBaseUrl =
  typeof window !== "undefined" && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://127.0.0.1:8000";
const fallbackApiBaseUrl = "http://127.0.0.1:8000";
const THREAD_KEY = "medical_assistant_thread_id";

async function readJson(response) {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export default function App() {
  const [threadId, setThreadId] = useState(() => localStorage.getItem(THREAD_KEY) || "");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState(configuredApiBaseUrl || browserApiBaseUrl);
  const [isConnected, setIsConnected] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const sourceRef = useRef(null);
  const streamDoneRef = useRef(false);

  useEffect(() => {
    ensureSession();
    refreshStatus();
    return () => sourceRef.current?.close();
  }, []);

  useEffect(() => {
    if (!threadId) return;
    localStorage.setItem(THREAD_KEY, threadId);
    loadHistory(threadId);
  }, [threadId]);

  async function ensureSession() {
    try {
      const payload = threadId ? { thread_id: threadId } : {};
      const data = await apiFetchJson("/api/chat/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setThreadId(data.thread_id);
      localStorage.setItem(THREAD_KEY, data.thread_id);
      setIsConnected(true);
    } catch {
      setIsConnected(false);
      setError("无法连接后端服务，请确认 FastAPI 已启动。");
    }
  }

  async function loadHistory(activeThreadId = threadId) {
    if (!activeThreadId) return;
    try {
      const data = await apiFetchJson(
        `/api/chat/history?thread_id=${encodeURIComponent(activeThreadId)}`
      );
      setMessages(
        (data.messages || []).map((m, i) => ({
          id: m.id ?? `hist-${i}`,
          timestamp: m.timestamp ?? Date.now() + i,
          ...m,
        }))
      );
    } catch {
      setError("历史会话暂时无法读取。");
    }
  }

  async function refreshStatus() {
    try {
      const data = await apiFetchJson("/api/system/status");
      setStatus(data);
      setIsConnected(true);
    } catch {
      setIsConnected(false);
      setError("系统状态暂时无法读取。");
    }
  }

  function handleClearClick() {
    setClearDialogOpen(true);
  }

  async function clearChat() {
    setClearDialogOpen(false);
    if (!threadId) return;
    sourceRef.current?.close();
    setIsStreaming(false);
    try {
      await apiFetchJson("/api/chat/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId }),
      });
      setMessages([]);
      setError("");
    } catch {
      setError("清空会话失败，请稍后再试。");
    }
  }

  function stopStreaming() {
    sourceRef.current?.close();
    streamDoneRef.current = true;
    setIsStreaming(false);
  }

  function sendMessage(text = input) {
    const content = text.trim();
    if (!content || !threadId || isStreaming) return;

    sourceRef.current?.close();
    streamDoneRef.current = false;
    setError("");
    setInput("");
    setIsStreaming(true);
    const now = Date.now();
    setMessages((prev) => [
      ...prev,
      { id: `u-${now}`, role: "user", content, timestamp: now },
      { id: `a-${now}`, role: "assistant", content: "", timestamp: now + 1 },
    ]);

    const url = `${apiBaseUrl}/api/chat/stream?thread_id=${encodeURIComponent(threadId)}&message=${encodeURIComponent(content)}`;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          next[next.length - 1] = { ...last, content: payload.content };
        }
        return next;
      });
    });

    source.addEventListener("final", (event) => {
      const payload = JSON.parse(event.data);
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          next[next.length - 1] = { ...last, content: payload.content };
        }
        return next;
      });
      setIsStreaming(false);
      streamDoneRef.current = true;
      source.close();
      refreshStatus();
    });

    source.addEventListener("app-error", (event) => {
      const payload = JSON.parse(event.data);
      streamDoneRef.current = true;
      setError(payload.content || "聊天服务暂时不可用。");
      setIsStreaming(false);
      source.close();
    });

    source.onerror = (event) => {
      if (streamDoneRef.current || source.readyState === EventSource.CLOSED) {
        source.close();
        return;
      }
      if (event.data) {
        const payload = JSON.parse(event.data);
        setError(payload.content || "聊天服务暂时不可用。");
      } else {
        setError("聊天连接中断，请稍后重试。");
      }
      setIsStreaming(false);
      source.close();
    };
  }

  async function apiFetchJson(path, options) {
    const firstUrl = `${apiBaseUrl}${path}`;
    try {
      return await readJson(await fetch(firstUrl, options));
    } catch (err) {
      if (configuredApiBaseUrl || apiBaseUrl === fallbackApiBaseUrl) {
        throw err;
      }
      const fallbackUrl = `${fallbackApiBaseUrl}${path}`;
      const data = await readJson(await fetch(fallbackUrl, options));
      setApiBaseUrl(fallbackApiBaseUrl);
      return data;
    }
  }

  return (
    <div className="app">
      <Sidebar
        status={status}
        onClear={handleClearClick}
        onRefresh={refreshStatus}
        mobileOpen={sidebarOpen}
        onMobileClose={() => setSidebarOpen(false)}
      />

      <section className="chat-shell">
        <ChatHeader
          threadId={threadId}
          isConnected={isConnected}
          onMenuClick={() => setSidebarOpen(true)}
        />

        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onSendMessage={sendMessage}
        />

        {error && (
          <div className="error-bar" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="error-bar__close"
              onClick={() => setError("")}
              aria-label="关闭错误提示"
            >
              ×
            </button>
          </div>
        )}

        <Composer
          input={input}
          onChange={setInput}
          onSubmit={sendMessage}
          onStop={stopStreaming}
          isStreaming={isStreaming}
          disabled={!threadId}
        />
      </section>

      <ClearConfirmDialog
        open={clearDialogOpen}
        onConfirm={clearChat}
        onCancel={() => setClearDialogOpen(false)}
      />
    </div>
  );
}
