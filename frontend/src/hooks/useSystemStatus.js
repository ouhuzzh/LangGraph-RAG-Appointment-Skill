import { useCallback, useEffect, useState } from "react";
import { fetchSystemStatus, initialApiBaseUrl } from "../lib/api";

export function useSystemStatus() {
  const [status, setStatus] = useState(null);
  const [apiBaseUrl, setApiBaseUrl] = useState(initialApiBaseUrl);
  const [isConnected, setIsConnected] = useState(true);
  const [statusError, setStatusError] = useState("");

  const refreshStatus = useCallback(async () => {
    try {
      const data = await fetchSystemStatus(apiBaseUrl, setApiBaseUrl);
      setStatus(data);
      setIsConnected(true);
      setStatusError("");
      return data;
    } catch {
      setIsConnected(false);
      setStatusError("系统状态暂时无法读取。");
      return null;
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  return {
    status,
    apiBaseUrl,
    setApiBaseUrl,
    isConnected,
    setIsConnected,
    statusError,
    clearStatusError: () => setStatusError(""),
    refreshStatus,
  };
}
