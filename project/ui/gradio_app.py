import html
import os
import time

import gradio as gr

import config
from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
APP_THEME = gr.themes.Base()
APP_CSS = """
:root {
  --page-bg: #f4f7f9;
  --surface: #ffffff;
  --surface-soft: #f8fafb;
  --surface-hover: #f0f4f5;
  --border: rgba(0, 0, 0, 0.06);
  --border-strong: rgba(0, 0, 0, 0.10);
  --text: #1a1d21;
  --text-secondary: #4a5568;
  --muted: #718096;
  --primary: #0d9488;
  --primary-strong: #0f766e;
  --primary-light: rgba(13, 148, 136, 0.08);
  --success: #059669;
  --warning: #d97706;
  --danger: #dc2626;
  --radius-xl: 24px;
  --radius-lg: 16px;
  --radius-md: 12px;
  --radius-sm: 8px;
}

/* ── Page ── */
.gradio-container {
  background: var(--page-bg) !important;
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.gradio-container,
.gradio-container .prose,
.gradio-container .prose p,
.gradio-container p,
.gradio-container span:not(.pill):not(.chip):not(.metric-label):not(.metric-value):not(.metric-note),
.gradio-container label,
.gradio-container li,
.gradio-container div { color: var(--text-secondary); }

.gradio-container .prose h1,
.gradio-container .prose h2,
.gradio-container .prose h3,
.gradio-container .prose h4,
.gradio-container .prose strong { color: var(--text) !important; }

.app-shell { max-width: 1280px; margin: 0 auto; padding: 0 8px; }

/* ── Hero ── */
.hero-panel {
  background: linear-gradient(135deg, #0f766e 0%, #0d9488 50%, #14b8a6 100%);
  color: #fff;
  border-radius: var(--radius-xl);
  padding: 24px 32px;
  margin-bottom: 16px;
  position: relative;
  overflow: hidden;
}

.hero-panel::before {
  content: "";
  position: absolute;
  top: -50%;
  right: -8%;
  width: 260px;
  height: 260px;
  background: rgba(255,255,255,0.06);
  border-radius: 50%;
  pointer-events: none;
}

.hero-kicker {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(255,255,255,0.18);
  backdrop-filter: blur(4px);
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #fff;
}

.hero-panel h1 { margin: 10px 0 6px; font-size: 1.5rem; line-height: 1.25; font-weight: 800; color: #fff !important; }
.hero-panel p { margin: 0; max-width: 640px; color: rgba(255,255,255,0.82); font-size: .88rem; line-height: 1.65; }

/* ── Cards & Shells ── */
.status-shell, .card-shell, .import-card, .doc-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.status-shell { padding: 20px 24px; margin-bottom: 14px; }
.status-shell h2 { margin: 0 0 10px; font-size: 1.15rem; font-weight: 700; color: var(--text) !important; }
.status-shell p, .card-shell p, .import-card p, .doc-card p { margin: 0; color: var(--muted); line-height: 1.7; font-size: .88rem; }

/* ── Pill Badges ── */
.pill {
  display: inline-flex; align-items: center;
  padding: 4px 11px; margin-right: 6px;
  border-radius: 999px; font-size: .73rem; font-weight: 600; letter-spacing: .02em;
}
.pill.ready, .pill.success { background: rgba(5,150,105,.10); color: #047857; }
.pill.pending, .pill.loading { background: rgba(13,148,136,.10); color: #0f766e; }
.pill.warning { background: rgba(217,119,6,.10); color: #b45309; }
.pill.error { background: rgba(220,38,38,.10); color: #b91c1c; }

/* ── Metrics ── */
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.metric {
  background: var(--surface-soft); border: 1px solid var(--border);
  border-radius: var(--radius-md); padding: 14px 16px; transition: box-shadow .15s ease;
}
.metric:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.metric-label { display:block; color: var(--muted); font-size: .73rem; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.metric-value { display:block; color: var(--text); font-size: 1.15rem; font-weight: 800; }
.metric-note  { display:block; color: var(--muted); font-size: .76rem; margin-top: 4px; line-height: 1.5; }

.card-shell, .import-card, .doc-card { padding: 20px; }
.card-shell h3, .import-card h3, .doc-card h3 { margin: 0 0 10px; color: var(--text) !important; font-size: 1rem; font-weight: 700; }

/* ── Item Lists ── */
.item-list { display:grid; gap:8px; max-height: 420px; overflow-y: auto; padding-right: 4px; }
.item-list.import-list { max-height: 300px; }
.item-list.document-list { max-height: 340px; }
.item-list::-webkit-scrollbar { width: 5px; }
.item-list::-webkit-scrollbar-track { background: transparent; }
.item-list::-webkit-scrollbar-thumb { background: rgba(0,0,0,.08); border-radius: 4px; }
.item {
  background: var(--surface-soft); border: 1px solid var(--border);
  border-radius: var(--radius-md); padding: 12px 14px; transition: background .15s ease;
}
.item:hover { background: var(--surface-hover); }
.item strong { color: var(--text) !important; font-size: .88rem; }
.item span  { display:block; margin-top: 3px; color: var(--muted); line-height: 1.5; font-size: .84rem; }
.chip-row { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.chip {
  display:inline-flex; align-items:center; padding: 4px 10px;
  border-radius: 999px; background: var(--primary-light);
  color: var(--primary-strong); font-size: .73rem; font-weight: 600;
}

/* ── Chatbot ── */
.gradio-container .chatbot {
  border-radius: var(--radius-lg) !important;
  border: 1px solid var(--border) !important;
  background: var(--surface) !important;
}

#chat-panel { overflow: visible !important; }
#medical-chatbot {
  height: min(620px, calc(100vh - 320px)) !important;
  min-height: 420px !important;
  max-height: min(620px, calc(100vh - 320px)) !important;
  overflow: hidden !important;
}
#medical-chatbot > div,
#medical-chatbot .wrap,
#medical-chatbot .bubble-wrap,
#medical-chatbot .messages,
#medical-chatbot [role="log"] {
  max-height: inherit !important;
  overflow-y: auto !important;
  overscroll-behavior: contain;
}

.gradio-container .gr-chatbot .user {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #fff !important; border: none !important;
  border-radius: var(--radius-md) var(--radius-md) 4px var(--radius-md) !important;
  box-shadow: 0 2px 8px rgba(15,118,110,0.15) !important;
}
.gradio-container .gr-chatbot .user *,
.gradio-container .gr-chatbot .user .md,
.gradio-container .gr-chatbot .user .md p,
.gradio-container .gr-chatbot .user .md strong,
.gradio-container .gr-chatbot .user .md li,
.gradio-container .gr-chatbot .user .md code { color: #fff !important; }

.gradio-container .gr-chatbot .assistant {
  background: var(--surface-soft) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) var(--radius-md) var(--radius-md) 4px !important;
  color: var(--text) !important;
}
.gradio-container .gr-chatbot .assistant *,
.gradio-container .gr-chatbot .assistant .md,
.gradio-container .gr-chatbot .assistant .md p,
.gradio-container .gr-chatbot .assistant .md li,
.gradio-container .gr-chatbot .assistant .md em,
.gradio-container .gr-chatbot .assistant .md code { color: var(--text-secondary) !important; }
.gradio-container .gr-chatbot .assistant .md strong,
.gradio-container .gr-chatbot .assistant .md h1,
.gradio-container .gr-chatbot .assistant .md h2,
.gradio-container .gr-chatbot .assistant .md h3,
.gradio-container .gr-chatbot .assistant .md h4 { color: var(--text) !important; }
.gradio-container .gr-chatbot .assistant details,
.gradio-container .gr-chatbot .assistant summary { color: var(--text-secondary) !important; }
.gradio-container .gr-chatbot .assistant details * { color: var(--text-secondary) !important; }
.gradio-container .gr-chatbot .assistant blockquote { color: var(--text-secondary) !important; border-left-color: var(--primary) !important; }

/* ── Inputs ── */
.gradio-container textarea,
.gradio-container input,
.gradio-container .gr-textbox textarea,
.gradio-container .gr-textbox input {
  color: var(--text) !important; background: var(--surface) !important;
  border: 1.5px solid var(--border-strong) !important;
  border-radius: var(--radius-md) !important; font-size: .93rem !important;
}
.gradio-container textarea:focus,
.gradio-container input:focus {
  border-color: var(--primary) !important; outline: none !important;
  box-shadow: 0 0 0 3px rgba(13,148,136,0.10) !important;
}
.gradio-container textarea::placeholder,
.gradio-container input::placeholder { color: #a0aec0 !important; }

/* ── Buttons (global) ── */
.gradio-container button { border-radius: var(--radius-md) !important; font-weight: 600 !important; transition: all .15s ease !important; }

.gradio-container .gr-button-primary {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #fff !important; border: none !important;
  padding: 10px 28px !important; font-size: .93rem !important;
  box-shadow: 0 2px 8px rgba(13,148,136,0.20) !important;
}
.gradio-container .gr-button-primary:hover { box-shadow: 0 4px 16px rgba(13,148,136,0.30) !important; }

/* ── Chat Send / Stop Buttons ── */
.gradio-container button.primary,
.gradio-container button[variant="primary"] {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #fff !important; border: none !important;
  min-width: 88px !important; min-height: 46px !important;
  font-size: .95rem !important; font-weight: 700 !important;
  border-radius: var(--radius-md) !important;
  box-shadow: 0 3px 12px rgba(13,148,136,0.24) !important;
  cursor: pointer !important;
  letter-spacing: .03em;
}
.gradio-container button.primary:hover,
.gradio-container button[variant="primary"]:hover {
  box-shadow: 0 5px 20px rgba(13,148,136,0.38) !important;
  transform: translateY(-1px);
}

.gradio-container .gr-button-secondary {
  background: var(--surface) !important; color: var(--primary-strong) !important;
  border: 1.5px solid rgba(13,148,136,.20) !important; padding: 10px 24px !important;
}
.gradio-container .gr-button-secondary:hover {
  background: var(--primary-light) !important; border-color: rgba(13,148,136,.35) !important;
}

.gradio-container .gr-button-stop,
.gradio-container button.stop {
  background: var(--surface) !important; color: var(--danger) !important;
  border: 1.5px solid rgba(220,38,38,.18) !important;
}
.gradio-container .gr-button-stop:hover,
.gradio-container button.stop:hover { background: rgba(220,38,38,.06) !important; }

/* ── Accordion ── */
.diagnostics-accordion { border-radius: var(--radius-md) !important; overflow: hidden; border: 1px solid var(--border) !important; }
.diagnostics-accordion > button, .diagnostics-accordion .label-wrap { color: var(--text) !important; font-weight: 600 !important; }
.diag-note { color: var(--muted) !important; line-height: 1.65; font-size: .86rem; }

/* ── File Upload ── */
.gradio-container .gr-file { border: 2px dashed rgba(0,0,0,0.10) !important; background: var(--surface-soft) !important; border-radius: var(--radius-md) !important; }
.gradio-container .gr-file:hover { border-color: var(--primary) !important; }

/* ── Dropdown / Checkbox ── */
.gradio-container .gr-dropdown select,
.gradio-container .gr-checkbox label { color: var(--text) !important; }

/* ── Tabs ── */
.gradio-container button[role="tab"] {
  color: var(--muted) !important; border-bottom: 2px solid transparent !important;
  font-weight: 600 !important; padding: 10px 20px !important; transition: all .2s ease !important;
}
.gradio-container button[role="tab"]:hover { color: var(--text) !important; }
.gradio-container button[role="tab"][aria-selected="true"] { color: var(--primary-strong) !important; border-bottom: 2.5px solid var(--primary) !important; }

/* ── Links ── */
.gradio-container a { color: var(--primary) !important; }
.gradio-container a:hover { color: var(--primary-strong) !important; }

/* ── Scrollbar ── */
.gr-chatbot::-webkit-scrollbar { width: 5px; }
.gr-chatbot::-webkit-scrollbar-track { background: transparent; }
.gr-chatbot::-webkit-scrollbar-thumb { background: rgba(0,0,0,.08); border-radius: 4px; }

/* ── Tooltips / toast should float above scrollable cards ── */
.gradio-container [role="tooltip"],
.gradio-container .tooltip,
.gradio-container .toast,
.gradio-container .toast-wrap,
.gradio-container .notification,
.toast-wrap {
  z-index: 9999 !important;
}
.status-shell, .card-shell, .import-card, .doc-card, #chat-panel {
  overflow: visible !important;
}

/* ── Quick-hints row ── */
.quick-hints { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0 4px; }
.quick-hints span {
  padding: 7px 14px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--border-strong);
  color: var(--text-secondary); font-size: .84rem; cursor: default; transition: all .15s ease;
}
.quick-hints span:hover { background: var(--primary-light); border-color: rgba(13,148,136,.25); color: var(--primary-strong); }

/* ── Footer ── */
footer { visibility: hidden; }

@media (max-width: 980px) {
  .hero-panel { padding: 20px; }
  .hero-panel h1 { font-size: 1.25rem; }
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""


def create_gradio_ui(rag_system=None, start_background_tasks=True):
    rag_system = rag_system or RAGSystem()
    if start_background_tasks:
        rag_system.start_background_initialize()

    doc_manager = DocumentManager(rag_system)
    chat_interface = ChatInterface(rag_system)

    def _badge(status: str):
        normalized = str(status or "").strip().lower()
        tone = {
            "ready": "ready",
            "completed": "success",
            "building": "loading",
            "preparing": "loading",
            "pending_rebuild": "pending",
            "not_checked": "pending",
            "no_documents": "warning",
            "failed": "error",
        }.get(normalized, "pending")
        return f'<span class="pill {tone}">{html.escape(normalized.replace("_", " ").title())}</span>'

    def _format_system_status():
        system_status = rag_system.get_system_status()
        step_order = ["database_check", "model_init", "graph_compile", "knowledge_base_bootstrap"]
        step_labels = {
            "database_check": "数据库检查",
            "model_init": "模型初始化",
            "graph_compile": "代理图构建",
            "knowledge_base_bootstrap": "知识库补建",
        }
        lines = [f"系统状态：{system_status['state']}", system_status["message"]]
        if system_status.get("last_error"):
            lines.append(f"最近错误：{system_status['last_error']}")
        for step_key in step_order:
            step = system_status["steps"].get(step_key)
            if not step:
                continue
            elapsed = f" ({step['elapsed_ms']} ms)" if step.get("elapsed_ms") is not None else ""
            lines.append(f"- {step_labels[step_key]}: {step['state']} - {step.get('message', '')}{elapsed}")
        return "\n".join(lines)

    def _format_knowledge_status():
        knowledge_status = rag_system.get_knowledge_base_status()
        stats = knowledge_status["stats"]
        lines = [
            f"知识库状态：{knowledge_status['status']}",
            knowledge_status["message"],
            f"本地 Markdown：{stats.get('local_markdown_files', 0)}",
            f"数据库文档：{stats.get('documents', 0)}",
            f"已下线文档：{stats.get('inactive_documents', 0)}",
            f"父块数：{stats.get('parent_chunks', 0)}",
            f"子块数：{stats.get('child_chunks', 0)}",
        ]
        if stats.get("last_bootstrap_result"):
            lines.append(f"最近补建结果：{stats['last_bootstrap_result']}")
        if stats.get("last_sync_result"):
            lines.append(f"最近同步结果：{stats['last_sync_result']}")
        if knowledge_status.get("last_error"):
            lines.append(f"最近错误：{knowledge_status['last_error']}")
        return "\n".join(lines)

    def _format_chat_status_panel():
        system_status = rag_system.get_system_status()
        knowledge_status = rag_system.get_knowledge_base_status()
        stats = knowledge_status["stats"]
        title = "现在可以直接开始咨询" if system_status["state"] == "ready" else "正在为你准备医疗助手"
        if system_status["state"] == "failed":
            title = "当前系统需要先处理一下异常"
        intro = {
            "ready": "你可以直接问症状、就诊建议、预约挂号或取消预约。",
            "failed": system_status.get("last_error") or "初始化出现异常，请稍后再试。",
        }.get(system_status["state"], system_status["message"])
        kb_note = {
            "ready": "资料库已经可检索，医学问题会优先结合导入资料回答。",
            "building": "资料库正在后台整理，预约/取消不受影响。",
            "pending_rebuild": "有资料还没整理完，系统会继续补建。",
            "no_documents": "当前还没有导入资料，医学资料问答建议先去 Documents 导入内容。",
            "failed": "资料库补建失败，文档型问答会受影响。",
        }.get(knowledge_status["status"], knowledge_status["message"])
        return f"""
<div class="status-shell">
  <h2>{html.escape(title)}</h2>
  {_badge(system_status['state'])}{_badge(knowledge_status['status'])}
  <p style="margin-top:12px;">{html.escape(intro)}</p>
  <p style="margin-top:8px;">{html.escape(kb_note)}</p>
    <div class="metric-grid">
    <div class="metric"><span class="metric-label">知识库资料</span><span class="metric-value">{stats.get('documents', 0)}</span><span class="metric-note">已登记文档</span></div>
    <div class="metric"><span class="metric-label">可检索片段</span><span class="metric-value">{stats.get('child_chunks', 0)}</span><span class="metric-note">用于回答的内容块</span></div>
    <div class="metric"><span class="metric-label">最近补建</span><span class="metric-value">{html.escape(knowledge_status['status'])}</span><span class="metric-note">{html.escape(stats.get('last_bootstrap_result') or '暂无新的补建记录')}</span></div>
    <div class="metric"><span class="metric-label">当前会话</span><span class="metric-value">强记忆</span><span class="metric-note">会尽量保留最近话题、科室建议和预约状态</span></div>
  </div>
  <p style="margin-top:12px;">{html.escape(stats.get('last_sync_result') or '最近还没有新的同步结果。')}</p>
</div>
""".strip()

    def _format_docs_status_panel():
        knowledge_status = rag_system.get_knowledge_base_status()
        stats = knowledge_status["stats"]
        note = {
            "ready": "资料已经整理完成，可以继续追加新资料或查看最近导入记录。",
            "building": "系统正在后台整理资料，界面会自动刷新状态。",
            "pending_rebuild": "检测到有资料尚未完成索引，系统会继续补建。",
            "no_documents": "现在还是空知识库，适合先导入一批官方资料做基础底座。",
            "failed": "资料整理失败了，建议查看最近任务记录和高级诊断。",
        }.get(knowledge_status["status"], knowledge_status["message"])
        return f"""
<div class="status-shell">
  <h2>把资料导进来，也要让状态一眼能看懂</h2>
  {_badge(knowledge_status['status'])}
  <p style="margin-top:12px;">{html.escape(note)}</p>
    <div class="metric-grid">
    <div class="metric"><span class="metric-label">本地 Markdown</span><span class="metric-value">{stats.get('local_markdown_files', 0)}</span><span class="metric-note">已经落在本地目录里的资料</span></div>
    <div class="metric"><span class="metric-label">数据库文档</span><span class="metric-value">{stats.get('documents', 0)}</span><span class="metric-note">已经登记进知识库</span></div>
    <div class="metric"><span class="metric-label">父块 / 子块</span><span class="metric-value">{stats.get('parent_chunks', 0)} / {stats.get('child_chunks', 0)}</span><span class="metric-note">索引结构</span></div>
    <div class="metric"><span class="metric-label">最近任务数</span><span class="metric-value">{len(stats.get('recent_imports') or [])}</span><span class="metric-note">包含导入和补建记录</span></div>
  </div>
  <p style="margin-top:12px;">{html.escape(stats.get('last_sync_result') or '最近还没有新的同步结果。')}</p>
</div>
""".strip()

    def _format_recent_imports():
        recent_imports = rag_system.get_knowledge_base_status()["stats"].get("recent_imports") or []
        if not recent_imports:
            return """
<div class="import-card">
  <h3>最近任务</h3>
  <p>还没有导入任务记录。第一次导入后，这里会直接告诉你写入了多少、跳过了多少、哪里失败了。</p>
</div>
""".strip()
        items = []
        for item in recent_imports[:6]:
            bits = [
                f"新增 {item.get('written', 0)}",
                f"更新 {item.get('updated', 0)}",
                f"下线 {item.get('deactivated', 0)}",
                f"未变化 {item.get('unchanged', 0)}",
                f"失败 {item.get('failed', 0)}",
                f"索引新增 {item.get('index_added', 0)}",
            ]
            if item.get("downloaded") is not None:
                bits.insert(0, f"下载 {item.get('downloaded', 0)}")
            extra = ""
            if item.get("failure_details"):
                extra += f"<span>问题摘要：{html.escape(' | '.join(item['failure_details'][:2]))}</span>"
            if item.get("note"):
                extra += f"<span>{html.escape(item['note'])}</span>"
            items.append(
                f"""
<div class="item">
  <strong>{html.escape(item.get('label', item.get('source', 'manual_upload')))}</strong>
  <span>{html.escape(item.get('timestamp', '-'))}</span>
  <div class="chip-row">
    {_badge(item.get('status', 'completed'))}
    <span class="chip">{html.escape(' · '.join(bits))}</span>
    <span class="chip">{html.escape(str(item.get('duration_ms', 0)))} ms</span>
  </div>
  {extra}
</div>
""".strip()
            )
        return f"""
<div class="import-card">
  <h3>最近任务</h3>
  <p>这里会保留最近的导入和补建结果，方便你确认系统有没有真的把资料整理好。</p>
  <div class="item-list import-list">{''.join(items)}</div>
</div>
""".strip()

    def _format_files():
        files = doc_manager.get_markdown_files()
        if not files:
            return """
<div class="doc-card">
  <h3>当前资料</h3>
  <p>现在还没有可用资料。你可以上传 PDF / Markdown，或者直接导入官方来源。</p>
</div>
""".strip()
        items = []
        for name in files[:12]:
            extension = os.path.splitext(name)[1].lower().lstrip(".") or "md"
            items.append(
                f"""
<div class="item">
  <strong>{html.escape(name)}</strong>
  <div class="chip-row">
    <span class="chip">{extension.upper()}</span>
    <span class="chip">已纳入知识库</span>
  </div>
</div>
""".strip()
            )
        overflow = f"<p style='margin-top:10px;'>还有 {len(files) - 12} 份资料未展开显示。</p>" if len(files) > 12 else ""
        return f"""
<div class="doc-card">
  <h3>当前资料</h3>
  <p>知识库里一共整理了 <strong>{len(files)}</strong> 份本地 Markdown 资料。</p>
  <div class="item-list document-list">{''.join(items)}</div>
  {overflow}
</div>
""".strip()

    def _format_debug_snapshot():
        return "### 系统诊断\n```text\n" + _format_system_status() + "\n```\n\n### 知识库诊断\n```text\n" + _format_knowledge_status() + "\n```"

    def refresh_status_panel():
        return (
            _format_chat_status_panel(),
            _format_docs_status_panel(),
            _format_recent_imports(),
            _format_files(),
            _format_debug_snapshot(),
            _format_debug_snapshot(),
        )

    def upload_handler(files, progress=gr.Progress()):
        if not files:
            return (None,) + refresh_status_panel()

        report = doc_manager.add_documents_with_report(
            files,
            progress_callback=lambda p, desc: progress(p, desc=desc),
        )

        rag_system.refresh_knowledge_base_status()
        sync_event = report.get("sync_event")
        if sync_event:
            rag_system.record_import_event(sync_event)
            rag_system.start_knowledge_base_bootstrap()
        gr.Info(
            f"已处理 {report['processed']} 个文件：新增 {report['added']}，更新 {report['updated']}，"
            f"未变化 {report['unchanged']}，失败 {report['failed']}。"
        )
        return (None,) + refresh_status_panel()

    def clear_handler():
        doc_manager.clear_all()
        rag_system.refresh_knowledge_base_status()
        gr.Info("已清空知识库文档。")
        return refresh_status_panel()

    def official_import_handler(source, limit, overwrite):
        result = doc_manager.sync_official_source(
            source=source,
            limit=int(limit),
            trigger_type="manual",
        )
        rag_system.refresh_knowledge_base_status()
        rag_system.start_knowledge_base_bootstrap()
        rag_system.record_import_event(result.to_event())
        gr.Info(
            f"官方同步完成：来源 {source}，新增 {result.written}，更新 {result.updated}，下线 {result.deactivated}，未变化 {result.unchanged}。"
        )
        summary = (
            f"来源：{source}\n"
            f"下载：{result.downloaded}\n"
            f"新增：{result.written}\n"
            f"更新：{result.updated}\n"
            f"下线：{result.deactivated}\n"
            f"未变化：{result.unchanged}\n"
            f"失败：{result.failed}\n"
            f"索引新增：{result.index_added}\n"
            f"索引跳过：{result.index_skipped}\n"
            f"范围：{result.scope}\n"
            f"耗时：{result.duration_ms} ms"
        )
        if result.conversion_details:
            summary += "\n转换详情：\n- " + "\n- ".join(result.conversion_details[:3])
        if result.failure_details:
            summary += "\n失败详情：\n- " + "\n- ".join(result.failure_details[:3])
        return (summary,) + refresh_status_panel()

    def _append_user_message(msg, hist):
        user_message = (msg or "").strip()
        history = _normalize_chat_history(hist)
        if not user_message:
            return "", history
        history.append({"role": "user", "content": user_message})
        return "", history

    def _extract_chat_message_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "".join(parts).strip()
        if isinstance(content, dict):
            return str(content.get("text") or content.get("value") or "").strip()
        return str(content or "").strip()

    def _normalize_chat_history(hist):
        if isinstance(hist, str):
            content = hist.strip()
            return [{"role": "assistant", "content": content}] if content else []
        if hasattr(hist, "get"):
            hist = [hist]
        normalized = []
        for item in list(hist or []):
            if hasattr(item, "get"):
                role = item.get("role") or "assistant"
                content = _extract_chat_message_text(item.get("content"))
            else:
                role = getattr(item, "role", "assistant")
                content = _extract_chat_message_text(getattr(item, "content", ""))
            if not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    def chat_handler(hist):
        history = _normalize_chat_history(hist)
        if not history:
            return history

        last_message = history[-1]
        user_message = _extract_chat_message_text(last_message.get("content"))
        if not user_message:
            return history

        base_history = history[:-1]
        user_entry = {"role": "user", "content": user_message}
        resolved_history = [*base_history, user_entry]
        for chunk in chat_interface.chat(user_message, base_history, reveal_diagnostics=False):
            resolved_history = [*base_history, user_entry, *_normalize_chat_history(chunk)]
        return resolved_history

    def clear_chat_handler():
        chat_interface.clear_session()
        return []

    with gr.Blocks(title="宁和医疗助手", theme=APP_THEME, css=APP_CSS, fill_height=True) as demo:
        with gr.Column(elem_classes=["app-shell"]):
            with gr.Tab("Chat"):
                gr.HTML(
                    """
<div class="hero-panel">
  <div class="hero-kicker">Medical Assistant</div>
  <h1>宁和医疗助手</h1>
  <p>问症状、查建议、预约挂号，直接输入即可开始对话。</p>
</div>
""".strip()
                )
                chat_status_panel = gr.HTML(value=_format_chat_status_panel())
                chatbot = gr.Chatbot(
                    height=620,
                    elem_id="medical-chatbot",
                    show_label=False,
                    avatar_images=(None, os.path.join(ASSETS_DIR, "chatbot_avatar.png")),
                    placeholder="<strong>直接输入你的问题就可以。</strong><br><em>比如：高血压要注意什么、咳嗽挂什么科、帮我预约明天下午呼吸内科。</em>",
                    layout="bubble",
                )
                chat_input = gr.Textbox(
                    placeholder="输入症状、医学问题或挂号需求 …",
                    lines=1,
                    max_lines=4,
                    show_label=False,
                    autofocus=True,
                )
                with gr.Row():
                    send_btn = gr.Button("发送", variant="primary")
                    clear_chat_btn = gr.Button("清空对话", variant="secondary")

                submit_event = chat_input.submit(
                    _append_user_message,
                    [chat_input, chatbot],
                    [chat_input, chatbot],
                    show_progress="hidden",
                ).then(
                    chat_handler,
                    [chatbot],
                    [chatbot],
                    show_progress="minimal",
                )
                send_btn.click(
                    _append_user_message,
                    [chat_input, chatbot],
                    [chat_input, chatbot],
                    show_progress="hidden",
                ).then(
                    chat_handler,
                    [chatbot],
                    [chatbot],
                    show_progress="minimal",
                )
                clear_chat_btn.click(clear_chat_handler, None, [chatbot], show_progress="hidden")
                gr.HTML(
                    """
<div class="quick-hints">
  <span>高血压要注意什么？</span>
  <span>咳嗽挂什么科？</span>
  <span>帮我预约明天下午呼吸内科</span>
  <span>取消刚才的预约</span>
</div>
""".strip()
                )

                with gr.Accordion("高级诊断", open=False, elem_classes=["diagnostics-accordion"]):
                    chat_debug_panel = gr.Markdown(value=_format_debug_snapshot())

            with gr.Tab("Documents"):
                gr.HTML(
                    """
<div class="hero-panel">
  <div class="hero-kicker">Knowledge Base</div>
  <h1>知识库管理</h1>
  <p>上传本地资料、导入官方来源，确认资料是否已整理进知识库。</p>
</div>
""".strip()
                )
                docs_status_panel = gr.HTML(value=_format_docs_status_panel())
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["card-shell"]):
                            gr.Markdown("### 上传你自己的资料")
                            gr.Markdown('<p class="diag-note">支持 PDF、Markdown、TXT、HTML；安装 unstructured 后可扩展 DOCX、PPTX、XLSX 等格式。同名文件默认按更新处理。</p>')
                            files_input = gr.File(
                                label="选择文档",
                                file_count="multiple",
                                type="filepath",
                                height=180,
                            )
                            add_btn = gr.Button("同步到知识库", variant="primary")
                            
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["card-shell"]):
                            gr.Markdown("### 一键导入官方资料")
                            gr.Markdown('<p class="diag-note">适合先快速搭一个可靠底座。系统会比对内容变化，并对失效来源做下线处理。</p>')
                            with gr.Row():
                                official_source = gr.Dropdown(
                                    choices=[
                                        ("MedlinePlus", "medlineplus"),
                                        ("国家卫健委", "nhc"),
                                        ("WHO Fact Sheets", "who"),
                                    ],
                                    value="medlineplus",
                                    label="官方来源",
                                )
                                official_limit = gr.Number(value=5, precision=0, minimum=1, maximum=100, label="数量")
                            official_overwrite = gr.Checkbox(value=False, label="保留此开关占位（当前默认按同步替换）")
                            official_import_btn = gr.Button("同步官方资料", variant="secondary")
                            official_import_result = gr.Textbox(value="", label="同步结果", interactive=False, lines=2)

                with gr.Row():
                    with gr.Column(scale=1):
                        docs_import_tasks = gr.HTML(value=_format_recent_imports())
                    with gr.Column(scale=1):
                        file_list = gr.HTML(value=_format_files())
                        
                with gr.Row():
                    with gr.Column():
                        refresh_btn = gr.Button("刷新状态", variant="secondary")
                    with gr.Column():
                        clear_btn = gr.Button("清空知识库", variant="stop")

                with gr.Accordion("高级诊断", open=False, elem_classes=["diagnostics-accordion"]):
                    docs_debug_panel = gr.Markdown(value=_format_debug_snapshot())

        add_btn.click(
            upload_handler,
            [files_input],
            [files_input, chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel],
            show_progress="corner",
        )
        official_import_btn.click(
            official_import_handler,
            [official_source, official_limit, official_overwrite],
            [official_import_result, chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel],
            show_progress="corner",
        )
        refresh_btn.click(refresh_status_panel, None, [chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel])
        clear_btn.click(clear_handler, None, [chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel])

        demo.load(refresh_status_panel, None, [chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel])
        status_timer = gr.Timer(config.STATUS_REFRESH_SECONDS)
        status_timer.tick(refresh_status_panel, None, [chat_status_panel, docs_status_panel, docs_import_tasks, file_list, chat_debug_panel, docs_debug_panel])

    return demo
