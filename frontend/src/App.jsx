import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Database,
  Loader2,
  MessageCircle,
  RefreshCw,
  Send,
  Stethoscope,
  Trash2,
} from "lucide-react";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const browserApiBaseUrl =
  typeof window !== "undefined" && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://127.0.0.1:8000";
const fallbackApiBaseUrl = "http://127.0.0.1:8000";
const THREAD_KEY = "medical_assistant_thread_id";

const starterPrompts = [
  "高血压应该注意什么？",
  "我咳嗽三天了，挂什么科？",
  "我想挂呼吸内科的号",
  "取消刚才的预约",
];

function statusTone(value) {
  if (["ready", "completed"].includes(value)) return "good";
  if (["failed", "error"].includes(value)) return "bad";
  if (["no_documents", "pending_rebuild"].includes(value)) return "warn";
  return "info";
}

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
  const chatEndRef = useRef(null);
  const sourceRef = useRef(null);
  const streamDoneRef = useRef(false);

  useEffect(() => {
    ensureSession();
    refreshStatus();
    return () => sourceRef.current?.close();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isStreaming]);

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
    } catch (err) {
      setError("无法连接后端服务，请确认 FastAPI 已启动。");
    }
  }

  async function loadHistory(activeThreadId = threadId) {
    if (!activeThreadId) return;
    try {
      const data = await apiFetchJson(`/api/chat/history?thread_id=${encodeURIComponent(activeThreadId)}`);
      setMessages(data.messages || []);
    } catch (err) {
      setError("历史会话暂时无法读取。");
    }
  }

  async function refreshStatus() {
    try {
      const data = await apiFetchJson("/api/system/status");
      setStatus(data);
    } catch (err) {
      setError("系统状态暂时无法读取。");
    }
  }

  async function clearChat() {
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
    } catch (err) {
      setError("清空会话失败，请稍后再试。");
    }
  }

  function sendMessage(text = input) {
    const content = text.trim();
    if (!content || !threadId || isStreaming) return;

    sourceRef.current?.close();
    streamDoneRef.current = false;
    setError("");
    setInput("");
    setIsStreaming(true);
    setMessages((prev) => [...prev, { role: "user", content }, { role: "assistant", content: "" }]);

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

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
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

  const systemState = status?.state || "preparing";
  const kbState = status?.knowledge_base?.status || "not_checked";
  const stats = status?.knowledge_base?.stats || {};

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Stethoscope size={24} />
          </div>
          <div>
            <h1>宁和医疗助手</h1>
            <p>医疗咨询与预约挂号</p>
          </div>
        </div>

        <section className="status-panel">
          <div className="section-title">
            <Activity size={18} />
            <span>系统状态</span>
            <button className="icon-button" type="button" title="刷新状态" onClick={refreshStatus}>
              <RefreshCw size={16} />
            </button>
          </div>
          <div className={`status-pill ${statusTone(systemState)}`}>{systemState}</div>
          <p>{status?.message || "正在读取系统状态。"}</p>
        </section>

        <section className="status-panel">
          <div className="section-title">
            <Database size={18} />
            <span>知识库</span>
          </div>
          <div className={`status-pill ${statusTone(kbState)}`}>{kbState}</div>
          <div className="metric-row">
            <span>文档</span>
            <strong>{stats.documents ?? 0}</strong>
          </div>
          <div className="metric-row">
            <span>片段</span>
            <strong>{stats.child_chunks ?? 0}</strong>
          </div>
          <p>{status?.knowledge_base?.message || "知识库状态读取中。"}</p>
        </section>

        <div className="sidebar-actions">
          <a href="http://127.0.0.1:7860" target="_blank" rel="noreferrer">
            Gradio 后台
          </a>
          <button type="button" onClick={clearChat}>
            <Trash2 size={16} />
            清空会话
          </button>
        </div>
      </aside>

      <section className="chat-shell">
        <header className="chat-header">
          <div>
            <span className="eyebrow">User Chat</span>
            <h2>直接说你的问题</h2>
          </div>
          <div className="thread-chip" title={threadId}>
            {threadId ? `thread ${threadId.slice(0, 8)}` : "creating"}
          </div>
        </header>

        <div className="message-list">
          {messages.length === 0 ? (
            <div className="empty-state">
              <MessageCircle size={38} />
              <p>可以问医学常识、症状分诊，也可以直接说挂号或取消预约。</p>
              <div className="prompt-grid">
                {starterPrompts.map((prompt) => (
                  <button key={prompt} type="button" onClick={() => sendMessage(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="bubble">
                  {message.content || (message.role === "assistant" && isStreaming ? <Loader2 className="spin" size={18} /> : "")}
                </div>
              </article>
            ))
          )}
          <div ref={chatEndRef} />
        </div>

        {error ? <div className="error-bar">{error}</div> : null}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            placeholder="输入症状、医学问题或挂号需求..."
            rows={1}
          />
          <button type="submit" disabled={!input.trim() || isStreaming || !threadId} title="发送">
            {isStreaming ? <Loader2 className="spin" size={20} /> : <Send size={20} />}
          </button>
        </form>
      </section>
    </main>
  );
}
