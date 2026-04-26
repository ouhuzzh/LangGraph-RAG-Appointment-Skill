import { useCallback, useEffect, useState } from "react";
import {
  fetchDocumentList,
  fetchDocumentSources,
  fetchDocumentTasks,
  fetchDocumentsStatus,
  syncOfficialDocuments,
  uploadDocuments,
} from "../lib/api";

export function useDocuments({ apiBaseUrl, setApiBaseUrl, refreshStatus }) {
  const [documents, setDocuments] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [sourceCoverage, setSourceCoverage] = useState([]);
  const [documentStatus, setDocumentStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refreshDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const [statusData, listData, taskData, sourceData] = await Promise.all([
        fetchDocumentsStatus(apiBaseUrl, setApiBaseUrl),
        fetchDocumentList(apiBaseUrl, setApiBaseUrl),
        fetchDocumentTasks(apiBaseUrl, setApiBaseUrl),
        fetchDocumentSources(apiBaseUrl, setApiBaseUrl),
      ]);
      setDocumentStatus(statusData.knowledge_base);
      setDocuments(listData.documents || []);
      setTasks(taskData.tasks || statusData.recent_tasks || []);
      setSourceCoverage(sourceData.sources || statusData.source_coverage || []);
      setError("");
    } catch {
      setError("知识库信息暂时无法读取。");
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, setApiBaseUrl]);

  useEffect(() => {
    refreshDocuments();
  }, [refreshDocuments]);

  const upload = useCallback(async (files) => {
    if (!files || files.length === 0) return;
    setIsWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await uploadDocuments(apiBaseUrl, setApiBaseUrl, files);
      setMessage(data.message || "文档上传完成。");
      await refreshDocuments();
      refreshStatus?.();
    } catch (err) {
      setError(err.message || "文档上传失败。");
    } finally {
      setIsWorking(false);
    }
  }, [apiBaseUrl, refreshDocuments, refreshStatus, setApiBaseUrl]);

  const syncOfficial = useCallback(async (source, limit) => {
    setIsWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await syncOfficialDocuments(apiBaseUrl, setApiBaseUrl, source, limit);
      setMessage(data.message || "官方资料同步完成。");
      await refreshDocuments();
      refreshStatus?.();
    } catch (err) {
      setError(err.message || "官方资料同步失败。");
    } finally {
      setIsWorking(false);
    }
  }, [apiBaseUrl, refreshDocuments, refreshStatus, setApiBaseUrl]);

  return {
    documents,
    tasks,
    sourceCoverage,
    documentStatus,
    isLoading,
    isWorking,
    message,
    error,
    setMessage,
    setError,
    refreshDocuments,
    upload,
    syncOfficial,
  };
}
