import React from "react";
import { Stethoscope, Activity, Database, MessageCircle, Trash2, ExternalLink, X } from "lucide-react";
import StatusIndicator from "./StatusIndicator";

const Sidebar = React.memo(function Sidebar({
  status,
  activeView,
  onNavigate,
  onClear,
  onRefresh,
  mobileOpen,
  onMobileClose,
}) {
  const systemState = status?.state || "preparing";
  const kbState = status?.knowledge_base?.status || "not_checked";
  const stats = status?.knowledge_base?.stats || {};

  const systemMetrics = [
    { label: "状态", value: systemState },
  ];
  const kbMetrics = [
    { label: "文档", value: stats.documents ?? 0 },
    { label: "片段", value: stats.child_chunks ?? 0 },
  ];

  return (
    <>
      {mobileOpen && (
        <div className="sidebar-backdrop" onClick={onMobileClose} aria-hidden="true" />
      )}
      <aside className={`sidebar${mobileOpen ? " sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <div className="brand">
            <div className="brand-mark">
              <Stethoscope size={22} />
            </div>
            <div className="brand-text">
              <h1 className="brand-title">宁和医疗助手</h1>
              <p className="brand-sub">医疗咨询与预约挂号</p>
            </div>
          </div>
          <button
            type="button"
            className="sidebar-close icon-button"
            onClick={onMobileClose}
            aria-label="关闭侧边栏"
          >
            <X size={18} />
          </button>
        </div>

        <div className="sidebar__status-group">
          <nav className="sidebar-nav" aria-label="主导航">
            <button
              type="button"
              className={`sidebar-nav__item${activeView === "chat" ? " sidebar-nav__item--active" : ""}`}
              onClick={() => onNavigate("chat")}
            >
              <MessageCircle size={16} />
              聊天咨询
            </button>
            <button
              type="button"
              className={`sidebar-nav__item${activeView === "documents" ? " sidebar-nav__item--active" : ""}`}
              onClick={() => onNavigate("documents")}
            >
              <Database size={16} />
              知识库文档
            </button>
          </nav>

          <StatusIndicator
            icon={Activity}
            label="系统状态"
            value={systemState}
            message={status?.message || "正在读取系统状态。"}
            metrics={systemMetrics}
            onRefresh={onRefresh}
          />
          <StatusIndicator
            icon={Database}
            label="知识库"
            value={kbState}
            message={status?.knowledge_base?.message || "知识库状态读取中。"}
            metrics={kbMetrics}
          />
        </div>

        <div className="sidebar-actions">
          <a
            href="http://127.0.0.1:7860"
            target="_blank"
            rel="noreferrer"
            className="sidebar-link-icon"
            title="Gradio 后台"
          >
            <ExternalLink size={16} />
            <span>Gradio 后台</span>
          </a>
          <button type="button" className="sidebar-clear-btn" onClick={onClear}>
            <Trash2 size={15} />
            清空会话
          </button>
        </div>
      </aside>
    </>
  );
});

export default Sidebar;
