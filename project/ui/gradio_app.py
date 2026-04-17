import gradio as gr
import config
import time
from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
APP_THEME = gr.themes.Soft()
APP_CSS = """
:root {
  --app-bg: #f4f8f7;
  --app-surface: #ffffff;
  --app-surface-alt: #eef6f4;
  --app-border: #cfe0db;
  --app-primary: #0f766e;
  --app-primary-strong: #0b5f59;
  --app-text: #16324a;
  --app-text-muted: #4a657d;
  --app-danger: #b42318;
  --app-warning: #b54708;
}

.gradio-container {
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 28%),
    linear-gradient(180deg, #f8fcfb 0%, var(--app-bg) 100%);
  color: var(--app-text);
  font-family: "Noto Sans SC", "Segoe UI", "PingFang SC", sans-serif;
}

.gradio-container .block {
  border: 1px solid rgba(207, 224, 219, 0.9);
}

.hero-card {
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.08), rgba(255, 255, 255, 0.95));
  border: 1px solid var(--app-border);
  border-radius: 22px;
  padding: 22px 24px;
  box-shadow: 0 18px 48px rgba(22, 50, 74, 0.08);
  margin-bottom: 10px;
}

.hero-card h1,
.hero-card h2,
.hero-card p,
.hero-card li,
.status-card h3,
.status-card p,
.status-card li,
.chat-overview-card h3,
.chat-overview-card p {
  color: var(--app-text) !important;
}

.hero-eyebrow {
  color: var(--app-primary-strong);
  font-size: 0.86rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.hero-card h1 {
  margin: 0 0 8px;
  font-size: 2rem;
  line-height: 1.15;
}

.hero-card p {
  margin: 0;
  font-size: 1rem;
  line-height: 1.7;
  color: var(--app-text-muted) !important;
}

.chat-overview-card,
.status-card {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--app-border);
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: 0 12px 28px rgba(22, 50, 74, 0.06);
}

.chat-overview-card {
  margin-bottom: 10px;
}

.chat-overview-card p,
.status-card p {
  margin: 0;
  color: var(--app-text-muted) !important;
  line-height: 1.65;
}

.status-card strong,
.chat-overview-card strong,
.hero-card strong {
  color: var(--app-text) !important;
}

.compact-accordion {
  border-radius: 18px !important;
  overflow: hidden;
}

.compact-accordion > button,
.compact-accordion .label-wrap {
  color: var(--app-text) !important;
  font-weight: 700 !important;
}

.compact-accordion .label-wrap {
  background: rgba(255, 255, 255, 0.92) !important;
}

#doc-management-tab .gr-textbox,
.chat-status-box .gr-textbox {
  background: rgba(255, 255, 255, 0.96) !important;
}

.gradio-container .gr-button-primary,
.gradio-container .gr-button-secondary,
.gradio-container button {
  border-radius: 999px !important;
  font-weight: 700 !important;
}

.gradio-container .gr-button-primary {
  background: linear-gradient(135deg, var(--app-primary), #14b8a6) !important;
  color: #ffffff !important;
}

.gradio-container .gr-button-secondary {
  background: #e6f4f1 !important;
  color: var(--app-primary-strong) !important;
  border-color: rgba(15, 118, 110, 0.2) !important;
}

.gradio-container .gr-button-stop {
  background: #fff1f0 !important;
  color: var(--app-danger) !important;
  border-color: rgba(180, 35, 24, 0.16) !important;
}

.gradio-container .gr-chatbot,
.gradio-container .gr-chatbot .message-wrap,
.gradio-container .gr-chatbot .bubble {
  color: var(--app-text) !important;
}

.gradio-container .gr-chatbot {
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid var(--app-border) !important;
  border-radius: 22px !important;
  box-shadow: 0 16px 38px rgba(22, 50, 74, 0.07);
}

.gradio-container .gr-chatbot .user {
  background: #e7f6f2 !important;
}

.gradio-container .gr-chatbot .assistant {
  background: #ffffff !important;
}

.gradio-container textarea,
.gradio-container input,
.gradio-container .wrap,
.gradio-container .gr-textbox textarea {
  color: var(--app-text) !important;
}

.gradio-container textarea::placeholder,
.gradio-container input::placeholder {
  color: #6c8397 !important;
}

.support-note {
  color: var(--app-text-muted) !important;
  font-size: 0.96rem;
}

@media (max-width: 768px) {
  .hero-card {
    padding: 18px;
    border-radius: 18px;
  }

  .hero-card h1 {
    font-size: 1.6rem;
  }
}
"""

def create_gradio_ui(rag_system=None, start_background_tasks=True):
    rag_system = rag_system or RAGSystem()
    if start_background_tasks:
        rag_system.start_background_initialize()

    doc_manager = DocumentManager(rag_system)
    chat_interface = ChatInterface(rag_system)

    def format_file_list():
        files = doc_manager.get_markdown_files()
        if not files:
            return "当前知识库里还没有可用文档。"
        return "\n".join([f"{f}" for f in files])

    def format_system_status():
        system_status = rag_system.get_system_status()
        step_order = ["database_check", "model_init", "graph_compile", "knowledge_base_bootstrap"]
        step_labels = {
            "database_check": "数据库检查",
            "model_init": "模型初始化",
            "graph_compile": "代理图构建",
            "knowledge_base_bootstrap": "知识库补建",
        }
        lines = [
            f"系统状态：{system_status['state']}",
            system_status["message"],
        ]
        if system_status.get("last_error"):
            lines.append(f"最近错误：{system_status['last_error']}")
        for step_key in step_order:
            step = system_status["steps"].get(step_key)
            if not step:
                continue
            elapsed = f" ({step['elapsed_ms']} ms)" if step.get("elapsed_ms") is not None else ""
            lines.append(f"- {step_labels[step_key]}: {step['state']} - {step.get('message', '')}{elapsed}")
        return "\n".join(lines)

    def format_knowledge_base_status():
        knowledge_status = rag_system.get_knowledge_base_status()
        stats = knowledge_status["stats"]
        lines = [
            f"知识库状态：{knowledge_status['status']}",
            knowledge_status["message"],
            f"本地 Markdown：{stats.get('local_markdown_files', 0)}",
            f"数据库文档：{stats.get('documents', 0)}",
            f"父块数：{stats.get('parent_chunks', 0)}",
            f"子块数：{stats.get('child_chunks', 0)}",
        ]
        if stats.get("last_bootstrap_result"):
            lines.append(f"最近补建结果：{stats['last_bootstrap_result']}")
        if knowledge_status.get("last_error"):
            lines.append(f"最近错误：{knowledge_status['last_error']}")
        return "\n".join(lines)

    def format_recent_import_tasks():
        knowledge_status = rag_system.get_knowledge_base_status()
        recent_imports = knowledge_status["stats"].get("recent_imports") or []
        if not recent_imports:
            return "暂无导入任务记录。"

        lines = []
        for item in recent_imports[:6]:
            lines.extend(
                [
                    f"[{item.get('timestamp', '-')}] {item.get('label', item.get('source', 'manual_upload'))}",
                    (
                        f"status={item.get('status', 'completed')} duration={item.get('duration_ms', 0)} ms "
                        f"written={item.get('written', 0)} skipped={item.get('skipped', 0)} failed={item.get('failed', 0)} "
                        f"index_added={item.get('index_added', 0)}"
                    ),
                ]
            )
            if item.get("downloaded") is not None:
                lines.append(f"downloaded={item.get('downloaded', 0)}")
            if item.get("conversion_details"):
                lines.append(f"conversion: {' | '.join(item['conversion_details'][:2])}")
            if item.get("failure_details"):
                lines.append(f"failures: {' | '.join(item['failure_details'][:2])}")
            if item.get("note"):
                lines.append(f"note: {item['note']}")
            lines.append("")
        return "\n".join(lines).strip()

    def format_chat_overview():
        system_status = rag_system.get_system_status()
        knowledge_status = rag_system.get_knowledge_base_status()
        if system_status["state"] == "ready":
            readiness = "系统已就绪，可以直接提问、预约或取消预约。"
        elif system_status["state"] == "failed":
            readiness = f"系统初始化失败：{system_status.get('last_error', '未知错误')}"
        else:
            readiness = f"系统正在准备中：{system_status['message']}"

        knowledge_hint = {
            "ready": "知识库已可检索，医学问题会优先结合导入资料回答。",
            "building": "知识库正在后台补建，预约/取消不受影响。",
            "pending_rebuild": "知识库正在等待补建，部分资料问答可能暂时不完整。",
            "no_documents": "当前还没有导入资料，医学问答会提示你先导入文档。",
            "failed": "知识库补建失败，医学资料问答暂时受影响。",
        }.get(knowledge_status["status"], knowledge_status["message"])

        return f"""
<div class="chat-overview-card">
  <h3>当前会话</h3>
  <p><strong>{readiness}</strong></p>
  <p>{knowledge_hint}</p>
  <p>我会尽量记住这轮会话里的最近话题、推荐科室、预约上下文和待确认操作。</p>
</div>
""".strip()

    def refresh_status_panel():
        return (
            format_system_status(),
            format_knowledge_base_status(),
            format_recent_import_tasks(),
            format_chat_overview(),
            format_system_status(),
            format_knowledge_base_status(),
            format_file_list(),
        )

    def upload_handler(files, progress=gr.Progress()):
        if not files:
            system_status, knowledge_status, import_tasks, chat_overview, _, _, file_list_value = refresh_status_panel()
            return None, file_list_value, system_status, knowledge_status, import_tasks, chat_overview, system_status, knowledge_status

        started_at = time.perf_counter()
        report = doc_manager.add_documents_with_report(
            files,
            progress_callback=lambda p, desc: progress(p, desc=desc)
        )

        rag_system.refresh_knowledge_base_status()
        rag_system.record_import_event(
            {
                "source": "manual_upload",
                "label": "Manual Upload",
                "status": "completed" if report["skipped"] == 0 else "completed_with_skips",
                "written": report["added"],
                "skipped": report["skipped"],
                "failed": 0,
                "downloaded": report["processed"],
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "note": "Uploaded PDF/Markdown files from the local workspace.",
                "index_added": report["added"],
                "failure_details": report["skipped_details"],
            }
        )
        rag_system.start_knowledge_base_bootstrap()
        gr.Info(f"已处理 {report['processed']} 个文件：新增 {report['added']}，跳过 {report['skipped']}。")
        system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        return None, file_list_value, system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status

    def clear_handler():
        doc_manager.clear_all()
        rag_system.refresh_knowledge_base_status()
        gr.Info("已清空知识库文档。")
        system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        return file_list_value, system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status

    def official_import_handler(source, limit, overwrite):
        started_at = time.perf_counter()
        result, index_result = doc_manager.import_official_source(
            source=source,
            limit=int(limit),
            overwrite=bool(overwrite),
            index_after_import=True,
        )
        rag_system.refresh_knowledge_base_status()
        rag_system.start_knowledge_base_bootstrap()
        rag_system.record_import_event(
            {
                "source": source,
                "label": {
                    "medlineplus": "MedlinePlus Import",
                    "nhc": "NHC PDF Import",
                    "who": "WHO Fact Sheet Import",
                }.get(source, source),
                "status": "completed" if result.failed == 0 else "completed_with_failures",
                "downloaded": result.downloaded,
                "written": result.written,
                "skipped": result.skipped,
                "failed": result.failed,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "index_added": index_result["added"],
                "index_skipped": index_result["skipped"],
                "conversion_details": list(result.conversion_details),
                "failure_details": list(result.failure_details),
                "note": f"Origin: {result.discovered_url}",
            }
        )
        gr.Info(
            f"官方导入完成：来源 {source}，写入 {result.written}，跳过 {result.skipped}，失败 {result.failed}，索引新增 {index_result['added']}。"
        )
        system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        summary = (
            f"Source: {source}\n"
            f"Downloaded: {result.downloaded}\n"
            f"Written: {result.written}\n"
            f"Skipped: {result.skipped}\n"
            f"Failed: {result.failed}\n"
            f"Index processed: {index_result['processed']}\n"
            f"Index added: {index_result['added']}\n"
            f"Index skipped: {index_result['skipped']}\n"
            f"Manifest/Origin: {result.discovered_url}\n"
            f"Duration: {round((time.perf_counter() - started_at) * 1000, 2)} ms"
        )
        if result.conversion_details:
            summary += "\nConversion details:\n- " + "\n- ".join(result.conversion_details[:3])
        if result.failure_details:
            summary += "\nFailure details:\n- " + "\n- ".join(result.failure_details[:3])
        return summary, file_list_value, system_status, knowledge_status, import_tasks, chat_overview, chat_system_status, chat_knowledge_status

    def chat_handler(msg, hist):
        for chunk in chat_interface.chat(msg, hist):
            yield chunk

    def clear_chat_handler():
        chat_interface.clear_session()

    with gr.Blocks(title="Agentic RAG", theme=APP_THEME, css=APP_CSS) as demo:

        with gr.Tab("Documents", elem_id="doc-management-tab"):
            gr.Markdown(
                """
<div class="hero-card">
  <div class="hero-eyebrow">Knowledge Base</div>
  <h1>整理你的医学资料</h1>
  <p>上传 PDF 或 Markdown，或直接导入官方来源。系统会自动索引并保留最近的导入任务记录，方便你随时查看结果。</p>
</div>
""".strip()
            )
            docs_system_status = gr.Textbox(
                value=format_system_status(),
                label="System Status",
                interactive=False,
                lines=5,
                elem_classes=["chat-status-box"],
            )
            docs_knowledge_status = gr.Textbox(
                value=format_knowledge_base_status(),
                label="Knowledge Base Status",
                interactive=False,
                lines=7,
                elem_classes=["chat-status-box"],
            )
            docs_import_tasks = gr.Textbox(
                value=format_recent_import_tasks(),
                label="Recent Import Tasks",
                interactive=False,
                lines=10,
                elem_classes=["chat-status-box"],
            )
            gr.Markdown("## Add New Documents")
            gr.Markdown('<p class="support-note">上传 PDF 或 Markdown。遇到同名文件时系统会明确提示，而不是静默覆盖。</p>')

            files_input = gr.File(
                label="Drop PDF or Markdown files here",
                file_count="multiple",
                type="filepath",
                height=200,
                show_label=False
            )
            
            add_btn = gr.Button("Add Documents", variant="primary", size="md")

            gr.Markdown("## Import Official Medical Sources")
            with gr.Row():
                official_source = gr.Dropdown(
                    choices=[
                        ("MedlinePlus", "medlineplus"),
                        ("国家卫健委", "nhc"),
                        ("WHO Fact Sheets", "who"),
                    ],
                    value="medlineplus",
                    label="Official Source",
                )
                official_limit = gr.Number(value=5, precision=0, minimum=1, maximum=100, label="Limit")
                official_overwrite = gr.Checkbox(value=False, label="Overwrite Existing Markdown")
            official_import_btn = gr.Button("Import Official Docs", variant="secondary", size="md")
            official_import_result = gr.Textbox(
                value="",
                label="Official Import Result",
                interactive=False,
                lines=8,
            )
            
            gr.Markdown("## Current Documents in the Knowledge Base")
            file_list = gr.Textbox(
                value=format_file_list(),
                interactive=False,
                lines=7,
                max_lines=10,
                elem_id="file-list-box",
                show_label=False
            )

            with gr.Row():
                refresh_btn = gr.Button("Refresh", size="md")
                clear_btn = gr.Button("Clear All", variant="stop", size="md")

        with gr.Tab("Chat"):
            gr.Markdown(
                """
<div class="hero-card">
  <div class="hero-eyebrow">Medical Assistant</div>
  <h1>更轻一点，也更像在对话</h1>
  <p>我会尽量直接回答常见医学问题；只有在预约、取消或分诊必须补关键信息时，才会继续追问。</p>
</div>
""".strip()
            )
            chat_overview = gr.Markdown(value=format_chat_overview())
            with gr.Accordion("查看系统详情", open=False, elem_classes=["compact-accordion"]):
                chat_system_status = gr.Textbox(
                    value=format_system_status(),
                    label="System Status",
                    interactive=False,
                    lines=5,
                    elem_classes=["chat-status-box"],
                )
                chat_knowledge_status = gr.Textbox(
                    value=format_knowledge_base_status(),
                    label="Knowledge Base Status",
                    interactive=False,
                    lines=7,
                    elem_classes=["chat-status-box"],
                )
            chatbot = gr.Chatbot(
                height=720,
                placeholder="<strong>可以直接问医学问题、预约挂号或取消预约</strong><br><em>我会尽量记住这轮会话里的上下文，并把回答说得更清楚。</em>",
                show_label=False,
                avatar_images=(None, os.path.join(ASSETS_DIR, "chatbot_avatar.png")),
                layout="bubble"
            )
            chatbot.clear(clear_chat_handler)

            gr.ChatInterface(fn=chat_handler, chatbot=chatbot)

        add_btn.click(
            upload_handler,
            [files_input],
            [files_input, file_list, docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status],
            show_progress="corner",
        )
        official_import_btn.click(
            official_import_handler,
            [official_source, official_limit, official_overwrite],
            [official_import_result, file_list, docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status],
            show_progress="corner",
        )
        refresh_btn.click(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list],
        )
        clear_btn.click(
            clear_handler,
            None,
            [file_list, docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status],
        )

        demo.load(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list],
        )
        status_timer = gr.Timer(config.STATUS_REFRESH_SECONDS)
        status_timer.tick(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, docs_import_tasks, chat_overview, chat_system_status, chat_knowledge_status, file_list],
        )

    return demo
