import { useCallback, useEffect, useRef, useReducer } from "react";
import { THREAD_KEY } from "../constants/app";
import {
  chatStreamUrl,
  clearChatSession,
  createSession,
  fetchChatHistory,
} from "../lib/api";
import { openChatStream } from "../lib/sse";

const STREAMING_STATES = new Set(["connecting", "thinking", "generating"]);

const initialState = {
  threadId: localStorage.getItem(THREAD_KEY) || "",
  messages: [],
  input: "",
  streamState: "idle",
  error: "",
  lastUserMessage: "",
  isLoadingHistory: false,
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_THREAD_ID":
      return { ...state, threadId: action.payload };
    case "SET_MESSAGES":
      return { ...state, messages: action.payload };
    case "ADD_MESSAGES":
      return { ...state, messages: [...state.messages, ...action.payload] };
    case "UPDATE_LAST_ASSISTANT": {
      const next = [...state.messages];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = { ...last, ...action.payload };
      }
      return { ...state, messages: next };
    }
    case "SET_INPUT":
      return { ...state, input: action.payload };
    case "SET_STREAM_STATE":
      return { ...state, streamState: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "SET_LAST_USER_MESSAGE":
      return { ...state, lastUserMessage: action.payload };
    case "SET_LOADING_HISTORY":
      return { ...state, isLoadingHistory: action.payload };
    case "CLEAR_MESSAGES":
      return { ...state, messages: [], error: "" };
    case "STOP_STREAMING": {
      const next = [...state.messages];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = {
          ...last,
          content: last.content || "已停止生成。",
          interrupted: true,
        };
      }
      return { ...state, messages: next, streamState: "stopped" };
    }
    default:
      return state;
  }
}

export function useChatSession({
  apiBaseUrl,
  setApiBaseUrl,
  refreshStatus,
  setIsConnected,
}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const sourceRef = useRef(null);
  const streamDoneRef = useRef(false);
  // Use refs to avoid stale closures in sendMessage
  const isStreamingRef = useRef(false);
  const inputRef = useRef(state.input);
  inputRef.current = state.input;

  const isStreaming = STREAMING_STATES.has(state.streamState);
  isStreamingRef.current = isStreaming;

  const loadHistory = useCallback(async (activeThreadId = state.threadId) => {
    if (!activeThreadId) return;
    dispatch({ type: "SET_LOADING_HISTORY", payload: true });
    try {
      const data = await fetchChatHistory(apiBaseUrl, setApiBaseUrl, activeThreadId);
      dispatch({
        type: "SET_MESSAGES",
        payload: (data.messages || []).map((m, i) => ({
          id: m.id ?? `hist-${i}`,
          timestamp: m.timestamp ?? Date.now() + i,
          ...m,
        })),
      });
    } catch {
      dispatch({ type: "SET_ERROR", payload: "历史会话暂时无法读取。" });
    } finally {
      dispatch({ type: "SET_LOADING_HISTORY", payload: false });
    }
  }, [apiBaseUrl, setApiBaseUrl, state.threadId]);

  const ensureSession = useCallback(async () => {
    try {
      const data = await createSession(apiBaseUrl, setApiBaseUrl, state.threadId);
      dispatch({ type: "SET_THREAD_ID", payload: data.thread_id });
      localStorage.setItem(THREAD_KEY, data.thread_id);
      setIsConnected(true);
    } catch {
      setIsConnected(false);
      dispatch({ type: "SET_ERROR", payload: "无法连接后端服务，请确认 FastAPI 已启动。" });
    }
  }, [apiBaseUrl, setApiBaseUrl, setIsConnected, state.threadId]);

  useEffect(() => {
    ensureSession();
    return () => sourceRef.current?.close();
  }, []);

  useEffect(() => {
    if (!state.threadId) return;
    localStorage.setItem(THREAD_KEY, state.threadId);
    loadHistory(state.threadId);
  }, [state.threadId, loadHistory]);

  const clearChat = useCallback(async () => {
    if (!state.threadId) return;
    sourceRef.current?.close();
    dispatch({ type: "SET_STREAM_STATE", payload: "idle" });
    try {
      await clearChatSession(apiBaseUrl, setApiBaseUrl, state.threadId);
      dispatch({ type: "CLEAR_MESSAGES" });
    } catch {
      dispatch({ type: "SET_ERROR", payload: "清空会话失败，请稍后再试。" });
    }
  }, [apiBaseUrl, setApiBaseUrl, state.threadId]);

  const stopStreaming = useCallback(() => {
    sourceRef.current?.close();
    streamDoneRef.current = true;
    dispatch({ type: "STOP_STREAMING" });
  }, []);

  const sendMessage = useCallback((text) => {
    const content = (text ?? inputRef.current).trim();
    if (!content || !state.threadId || isStreamingRef.current) return;

    sourceRef.current?.close();
    streamDoneRef.current = false;
    dispatch({ type: "SET_ERROR", payload: "" });
    dispatch({ type: "SET_INPUT", payload: "" });
    dispatch({ type: "SET_LAST_USER_MESSAGE", payload: content });
    dispatch({ type: "SET_STREAM_STATE", payload: "connecting" });

    const now = Date.now();
    dispatch({
      type: "ADD_MESSAGES",
      payload: [
        { id: `u-${now}`, role: "user", content, timestamp: now },
        { id: `a-${now}`, role: "assistant", content: "", timestamp: now + 1 },
      ],
    });

    const url = chatStreamUrl(apiBaseUrl, state.threadId, content);
    const source = openChatStream({
      url,
      doneRef: streamDoneRef,
      onStatus: () => dispatch({ type: "SET_STREAM_STATE", payload: "thinking" }),
      onMessage: (payload) => {
        dispatch({ type: "SET_STREAM_STATE", payload: "generating" });
        dispatch({ type: "UPDATE_LAST_ASSISTANT", payload: { content: payload.content } });
      },
      onFinal: (payload) => {
        dispatch({ type: "UPDATE_LAST_ASSISTANT", payload: { content: payload.content } });
        dispatch({ type: "SET_STREAM_STATE", payload: "done" });
        setIsConnected(true);
        refreshStatus?.();
      },
      onAppError: (payload) => {
        dispatch({ type: "SET_ERROR", payload: payload.content || "聊天服务暂时不可用。" });
        dispatch({ type: "SET_STREAM_STATE", payload: "error" });
      },
      onConnectionError: (event) => {
        if (event.data) {
          try {
            const payload = JSON.parse(event.data);
            dispatch({ type: "SET_ERROR", payload: payload.content || "聊天服务暂时不可用。" });
          } catch {
            dispatch({ type: "SET_ERROR", payload: "聊天服务暂时不可用。" });
          }
        } else {
          dispatch({ type: "SET_ERROR", payload: "聊天连接中断，请稍后重试。" });
        }
        dispatch({ type: "SET_STREAM_STATE", payload: "error" });
        setIsConnected(false);
      },
    });
    sourceRef.current = source;
  }, [apiBaseUrl, state.threadId, refreshStatus, setIsConnected]);

  const retryLastMessage = useCallback(() => {
    if (state.lastUserMessage && !isStreamingRef.current) {
      sendMessage(state.lastUserMessage);
    }
  }, [state.lastUserMessage, sendMessage]);

  return {
    threadId: state.threadId,
    messages: state.messages,
    input: state.input,
    setInput: (v) => dispatch({ type: "SET_INPUT", payload: v }),
    streamState: state.streamState,
    isStreaming,
    isLoadingHistory: state.isLoadingHistory,
    error: state.error,
    setError: (v) => dispatch({ type: "SET_ERROR", payload: v }),
    lastUserMessage: state.lastUserMessage,
    sendMessage,
    retryLastMessage,
    stopStreaming,
    clearChat,
  };
}
