import gradio as gr
import config
from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

def create_gradio_ui(rag_system=None, start_background_tasks=True):
    rag_system = rag_system or RAGSystem()
    if start_background_tasks:
        rag_system.start_background_initialize()

    doc_manager = DocumentManager(rag_system)
    chat_interface = ChatInterface(rag_system)

    def format_file_list():
        files = doc_manager.get_markdown_files()
        if not files:
            return "📭 No documents available in the knowledge base"
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

    def refresh_status_panel():
        return (
            format_system_status(),
            format_knowledge_base_status(),
            format_system_status(),
            format_knowledge_base_status(),
            format_file_list(),
        )

    def upload_handler(files, progress=gr.Progress()):
        if not files:
            system_status, knowledge_status, _, _, file_list_value = refresh_status_panel()
            return None, file_list_value, system_status, knowledge_status, system_status, knowledge_status

        added, skipped = doc_manager.add_documents(
            files,
            progress_callback=lambda p, desc: progress(p, desc=desc)
        )

        rag_system.refresh_knowledge_base_status()
        rag_system.start_knowledge_base_bootstrap()
        gr.Info(f"✅ Added: {added} | Skipped: {skipped}")
        system_status, knowledge_status, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        return None, file_list_value, system_status, knowledge_status, chat_system_status, chat_knowledge_status

    def clear_handler():
        doc_manager.clear_all()
        rag_system.refresh_knowledge_base_status()
        gr.Info(f"🗑️ Removed all documents")
        system_status, knowledge_status, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        return file_list_value, system_status, knowledge_status, chat_system_status, chat_knowledge_status

    def official_import_handler(source, limit, overwrite):
        result, index_result = doc_manager.import_official_source(
            source=source,
            limit=int(limit),
            overwrite=bool(overwrite),
            index_after_import=True,
        )
        rag_system.refresh_knowledge_base_status()
        rag_system.start_knowledge_base_bootstrap()
        gr.Info(
            f"官方导入完成：source={source} downloaded={result.downloaded} written={result.written} "
            f"skipped={result.skipped} failed={result.failed} | "
            f"index added={index_result['added']} skipped={index_result['skipped']}"
        )
        system_status, knowledge_status, chat_system_status, chat_knowledge_status, file_list_value = refresh_status_panel()
        summary = (
            f"Source: {source}\n"
            f"Downloaded: {result.downloaded}\n"
            f"Written: {result.written}\n"
            f"Skipped: {result.skipped}\n"
            f"Failed: {result.failed}\n"
            f"Index processed: {index_result['processed']}\n"
            f"Index added: {index_result['added']}\n"
            f"Index skipped: {index_result['skipped']}\n"
            f"Manifest/Origin: {result.discovered_url}"
        )
        return summary, file_list_value, system_status, knowledge_status, chat_system_status, chat_knowledge_status

    def chat_handler(msg, hist):
        for chunk in chat_interface.chat(msg, hist):
            yield chunk

    def clear_chat_handler():
        chat_interface.clear_session()

    with gr.Blocks(title="Agentic RAG") as demo:

        with gr.Tab("Documents", elem_id="doc-management-tab"):
            docs_system_status = gr.Textbox(
                value=format_system_status(),
                label="System Status",
                interactive=False,
                lines=5,
            )
            docs_knowledge_status = gr.Textbox(
                value=format_knowledge_base_status(),
                label="Knowledge Base Status",
                interactive=False,
                lines=7,
            )
            gr.Markdown("## Add New Documents")
            gr.Markdown("Upload PDF or Markdown files. Duplicates will be automatically skipped.")

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
            chat_system_status = gr.Textbox(
                value=format_system_status(),
                label="System Status",
                interactive=False,
                lines=5,
            )
            chat_knowledge_status = gr.Textbox(
                value=format_knowledge_base_status(),
                label="Knowledge Base Status",
                interactive=False,
                lines=7,
            )
            chatbot = gr.Chatbot(
                height=720,
                placeholder="<strong>Ask me anything!</strong><br><em>I'll search, reason, and act to give you the best answer :)</em>",
                show_label=False,
                avatar_images=(None, os.path.join(ASSETS_DIR, "chatbot_avatar.png")),
                layout="bubble"
            )
            chatbot.clear(clear_chat_handler)

            gr.ChatInterface(fn=chat_handler, chatbot=chatbot)

        add_btn.click(
            upload_handler,
            [files_input],
            [files_input, file_list, docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status],
            show_progress="corner",
        )
        official_import_btn.click(
            official_import_handler,
            [official_source, official_limit, official_overwrite],
            [official_import_result, file_list, docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status],
            show_progress="corner",
        )
        refresh_btn.click(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status, file_list],
        )
        clear_btn.click(
            clear_handler,
            None,
            [file_list, docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status],
        )

        demo.load(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status, file_list],
        )
        status_timer = gr.Timer(config.STATUS_REFRESH_SECONDS)
        status_timer.tick(
            refresh_status_panel,
            None,
            [docs_system_status, docs_knowledge_status, chat_system_status, chat_knowledge_status, file_list],
        )

    return demo
