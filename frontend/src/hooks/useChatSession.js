import { useCallback, useEffect, useRef, useState } from "react";
import { THREAD_KEY } from "../constants/app";
import {
  chatStreamUrl,
  clearChatSession,
  createSession,
  fetchChatHistory,
} from "../lib/api";
import { openChatStream } from "../lib/sse";

const STREAMING_STATES = new Set(["connecting", "thinking", "generating"]);

export function useChatSession({
  apiBaseUrl,
  setApiBaseUrl,
  refreshStatus,
  setIsConnected,
}) {
  const [threadId, setThreadId] = useState(() => localStorage.getItem(THREAD_KEY) || "");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streamState, setStreamState] = useState("idle");
  const [error, setError] = useState("");
  const [lastUserMessage, setLastUserMessage] = useState("");
  const sourceRef = useRef(null);
  const streamDoneRef = useRef(false);

  const isStreaming = STREAMING_STATES.has(streamState);

  const loadHistory = useCallback(async (activeThreadId = threadId) => {
    if (!activeThreadId) return;
    try {
      const data = await fetchChatHistory(apiBaseUrl, setApiBaseUrl, activeThreadId);
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
  }, [apiBaseUrl, setApiBaseUrl, threadId]);

  const ensureSession = useCallback(async () => {
    try {
      const data = await createSession(apiBaseUrl, setApiBaseUrl, threadId);
      setThreadId(data.thread_id);
      localStorage.setItem(THREAD_KEY, data.thread_id);
      setIsConnected(true);
    } catch {
      setIsConnected(false);
      setError("无法连接后端服务，请确认 FastAPI 已启动。");
    }
  }, [apiBaseUrl, setApiBaseUrl, setIsConnected, threadId]);

  useEffect(() => {
    ensureSession();
    return () => sourceRef.current?.close();
  }, []);

  useEffect(() => {
    if (!threadId) return;
    localStorage.setItem(THREAD_KEY, threadId);
    loadHistory(threadId);
  }, [threadId, loadHistory]);

  const clearChat = useCallback(async () => {
    if (!threadId) return;
    sourceRef.current?.close();
    setStreamState("idle");
    try {
      await clearChatSession(apiBaseUrl, setApiBaseUrl, threadId);
      setMessages([]);
      setError("");
    } catch {
      setError("清空会话失败，请稍后再试。");
    }
  }, [apiBaseUrl, setApiBaseUrl, threadId]);

  const stopStreaming = useCallback(() => {
    sourceRef.current?.close();
    streamDoneRef.current = true;
    setStreamState("stopped");
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = {
          ...last,
          content: last.content || "已停止生成。",
          interrupted: true,
        };
      }
      return next;
    });
  }, []);

  const sendMessage = useCallback((text = input) => {
    const content = text.trim();
    if (!content || !threadId || isStreaming) return;

    sourceRef.current?.close();
    streamDoneRef.current = false;
    setError("");
    setInput("");
    setLastUserMessage(content);
    setStreamState("connecting");
    const now = Date.now();
    setMessages((prev) => [
      ...prev,
      { id: `u-${now}`, role: "user", content, timestamp: now },
      { id: `a-${now}`, role: "assistant", content: "", timestamp: now + 1 },
    ]);

    const url = chatStreamUrl(apiBaseUrl, threadId, content);
    const source = openChatStream({
      url,
      doneRef: streamDoneRef,
      onStatus: () => setStreamState("thinking"),
      onMessage: (payload) => {
        setStreamState("generating");
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            next[next.length - 1] = { ...last, content: payload.content };
          }
          return next;
        });
      },
      onFinal: (payload) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            next[next.length - 1] = { ...last, content: payload.content };
          }
          return next;
        });
        setStreamState("done");
        setIsConnected(true);
        refreshStatus?.();
      },
      onAppError: (payload) => {
        setError(payload.content || "聊天服务暂时不可用。");
        setStreamState("error");
      },
      onConnectionError: (event) => {
        if (event.data) {
          const payload = JSON.parse(event.data);
          setError(payload.content || "聊天服务暂时不可用。");
        } else {
          setError("聊天连接中断，请稍后重试。");
        }
        setStreamState("error");
        setIsConnected(false);
      },
    });
    sourceRef.current = source;
  }, [apiBaseUrl, input, isStreaming, refreshStatus, setIsConnected, threadId]);

  const retryLastMessage = useCallback(() => {
    if (lastUserMessage && !isStreaming) {
      sendMessage(lastUserMessage);
    }
  }, [isStreaming, lastUserMessage, sendMessage]);

  return {
    threadId,
    messages,
    input,
    setInput,
    streamState,
    isStreaming,
    error,
    setError,
    lastUserMessage,
    sendMessage,
    retryLastMessage,
    stopStreaming,
    clearChat,
  };
}
