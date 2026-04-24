import { useRef, useState } from "react";
import { Database, FileText, RefreshCw, UploadCloud } from "lucide-react";
import { statusTone } from "../constants/app";
import StatusIndicator from "../components/StatusIndicator";

const OFFICIAL_SOURCES = [
  { value: "medlineplus", label: "MedlinePlus" },
  { value: "nhc", label: "国家卫健委" },
  { value: "who", label: "WHO" },
];

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocumentsPage({
  documentsState,
  onMenuClick,
}) {
  const fileRef = useRef(null);
  const [source, setSource] = useState("nhc");
  const [limit, setLimit] = useState(5);
  const {
    documents,
    tasks,
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
  } = documentsState;

  const stats = documentStatus?.stats || {};
  const statusValue = documentStatus?.status || "not_checked";
  const metrics = [
    { label: "文档", value: stats.documents ?? documents.length },
    { label: "片段", value: stats.child_chunks ?? 0 },
    { label: "本地文件", value: stats.local_markdown_files ?? documents.length },
  ];

  async function handleUpload(event) {
    const files = event.target.files;
    await upload(files);
    event.target.value = "";
  }

  return (
    <section className="documents-shell">
      <header className="documents-header">
        <button
          type="button"
          className="icon-button chat-header__menu"
          onClick={onMenuClick}
          aria-label="打开菜单"
        >
          ☰
        </button>
        <div>
          <span className="eyebrow">Knowledge Base</span>
          <h2>知识库文档</h2>
          <p>这里先提供用户友好的状态、上传和官方同步入口；高级诊断继续放在 Gradio 后台。</p>
        </div>
        <button
          type="button"
          className="secondary-btn"
          onClick={refreshDocuments}
          disabled={isLoading || isWorking}
        >
          <RefreshCw size={16} />
          刷新
        </button>
      </header>

      <div className="documents-grid">
        <div className="document-card document-card--status">
          <StatusIndicator
            icon={Database}
            label="知识库状态"
            value={statusValue}
            message={documentStatus?.message || "正在读取知识库状态。"}
            metrics={metrics}
          />
          <div className={`status-banner status-banner--${statusTone(statusValue)}`}>
            {documentStatus?.message || "知识库状态读取中。"}
          </div>
        </div>

        <div className="document-card">
          <div className="document-card__title">
            <UploadCloud size={18} />
            <h3>上传本地资料</h3>
          </div>
          <p className="document-card__desc">
            支持 Markdown、PDF、Office、HTML 等格式。上传后会自动转换并同步到知识库。
          </p>
          <input
            ref={fileRef}
            type="file"
            multiple
            className="visually-hidden"
            onChange={handleUpload}
            accept=".md,.pdf,.txt,.html,.htm,.doc,.docx,.ppt,.pptx,.xls,.xlsx"
          />
          <button
            type="button"
            className="primary-btn"
            onClick={() => fileRef.current?.click()}
            disabled={isWorking}
          >
            <UploadCloud size={17} />
            选择并上传
          </button>
        </div>

        <div className="document-card">
          <div className="document-card__title">
            <RefreshCw size={18} />
            <h3>同步官方资料</h3>
          </div>
          <p className="document-card__desc">
            手动拉取官方来源的当前资料，适合面试演示“知识库可更新化”。
          </p>
          <div className="sync-form">
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {OFFICIAL_SOURCES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <input
              type="number"
              min="1"
              max="50"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
            <button
              type="button"
              className="secondary-btn"
              onClick={() => syncOfficial(source, limit)}
              disabled={isWorking}
            >
              同步
            </button>
          </div>
        </div>
      </div>

      {(message || error) && (
        <div className={`document-alert ${error ? "document-alert--error" : "document-alert--ok"}`}>
          <span>{error || message}</span>
          <button type="button" onClick={() => { setError(""); setMessage(""); }}>×</button>
        </div>
      )}

      <div className="document-section">
        <div className="document-section__head">
          <h3>已同步文档</h3>
          <span>{documents.length} 个文件</span>
        </div>
        {documents.length === 0 ? (
          <div className="empty-panel">还没有可展示的本地 Markdown 文档，可以先上传或同步官方资料。</div>
        ) : (
          <div className="document-list">
            {documents.map((doc) => (
              <article className="document-row" key={doc.name}>
                <div className="document-row__icon"><FileText size={17} /></div>
                <div>
                  <strong>{doc.name}</strong>
                  <p>{doc.file_type.toUpperCase()} · {formatBytes(doc.size_bytes)} · {doc.modified_at || "未知时间"}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="document-section">
        <div className="document-section__head">
          <h3>最近同步任务</h3>
          <span>{tasks.length} 条</span>
        </div>
        {tasks.length === 0 ? (
          <div className="empty-panel">暂无同步任务记录。</div>
        ) : (
          <div className="task-list">
            {tasks.slice(0, 8).map((task, index) => (
              <article className="task-row" key={`${task.timestamp || "task"}-${index}`}>
                <strong>{task.label || task.source || "同步任务"}</strong>
                <p>
                  {task.timestamp || ""} · 新增 {task.written ?? 0} · 更新 {task.updated ?? 0} ·
                  下线 {task.deactivated ?? 0} · 失败 {task.failed ?? 0}
                </p>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
