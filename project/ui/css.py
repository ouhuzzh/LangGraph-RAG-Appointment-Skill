custom_css = """
    :root {
        --bg-page: #0b1220;
        --bg-panel: #121a2b;
        --bg-panel-soft: #182235;
        --bg-panel-muted: #1d2940;
        --border-strong: #31415f;
        --text-primary: #f5f7fb;
        --text-secondary: #d8e0ef;
        --text-muted: #9fb0cd;
        --accent: #4f8cff;
        --accent-hover: #3d79e6;
        --danger: #ef5a5a;
        --danger-hover: #dc4444;
    }

    /* ============================================
       MAIN CONTAINER
       ============================================ */
    .progress-text { 
        display: none !important;
    }
    
    .gradio-container { 
        max-width: 1000px !important;
        width: 100% !important;
        margin: 0 auto !important;
        font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        background:
            radial-gradient(circle at top right, rgba(79, 140, 255, 0.14), transparent 28%),
            linear-gradient(180deg, #0b1220 0%, #0e1728 100%) !important;
        color: var(--text-primary) !important;
        min-height: 100vh !important;
    }

    .gradio-container,
    .gradio-container .prose,
    .gradio-container p,
    .gradio-container span,
    .gradio-container label,
    .gradio-container li,
    .gradio-container div {
        color: var(--text-secondary);
    }

    .gradio-container .prose h1,
    .gradio-container .prose h2,
    .gradio-container .prose h3,
    .gradio-container .prose h4,
    .gradio-container .prose h5,
    .gradio-container .prose h6,
    .gradio-container .prose strong,
    .gradio-container .prose p strong {
        color: var(--text-primary) !important;
    }

    .gradio-container .prose p,
    .gradio-container .prose li,
    .gradio-container .prose em,
    .gradio-container .prose code {
        color: var(--text-secondary) !important;
    }

    .gradio-container .prose {
        background: transparent !important;
    }

    .block,
    .gr-box,
    .gr-panel,
    .gr-form,
    .gr-group,
    .gradio-container .tabs,
    .gradio-container .tabitem,
    .gradio-container [role="tabpanel"] {
        background: transparent !important;
    }
    
    /* ============================================
       TABS
       ============================================ */
    button[role="tab"] {
        color: var(--text-muted) !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
        transition: all 0.2s ease !important;
        background: transparent !important;
    }
    
    button[role="tab"]:hover {
        color: var(--text-primary) !important;
    }
    
    button[role="tab"][aria-selected="true"] {
        color: var(--text-primary) !important;
        border-bottom: 2px solid var(--accent) !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    
    .tabs {
        border-bottom: none !important;
        border-radius: 0 !important;
    }
    
    .tab-nav {
        border-bottom: 1px solid var(--border-strong) !important;
        border-radius: 0 !important;
    }
    
    button[role="tab"]::before,
    button[role="tab"]::after,
    .tabs::before,
    .tabs::after,
    .tab-nav::before,
    .tab-nav::after {
        display: none !important;
        content: none !important;
        border-radius: 0 !important;
    }
    
    #doc-management-tab {
        max-width: 500px !important;
        margin: 0 auto !important;
    }
    
    /* ============================================
       BUTTONS
       ============================================ */
    button {
        border-radius: 8px !important;
        border: none !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }
    
    .primary {
        background: var(--accent) !important;
        color: #ffffff !important;
    }
    
    .primary:hover {
        background: var(--accent-hover) !important;
        transform: translateY(-1px) !important;
    }
    
    .stop {
        background: var(--danger) !important;
        color: #ffffff !important;
    }
    
    .stop:hover {
        background: var(--danger-hover) !important;
        transform: translateY(-1px) !important;
    }
    
    /* ============================================
       CHAT INPUT BOX
       ============================================ */
    textarea[placeholder="Type a message..."],
    textarea[data-testid*="textbox"]:not(#file-list-box textarea) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: var(--text-primary) !important;
    }
    
    textarea[placeholder="Type a message..."]:focus {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }

    textarea::placeholder,
    input::placeholder {
        color: var(--text-muted) !important;
        opacity: 1 !important;
    }
    
    .gr-text-input:has(textarea[placeholder="Type a message..."]),
    [class*="chatbot"] + * [data-testid="textbox"],
    form:has(textarea[placeholder="Type a message..."]) > div {
        background: var(--bg-panel) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 14px !important;
        gap: 12px !important;
        padding: 6px 10px !important;
    }
    
    form:has(textarea[placeholder="Type a message..."]) button,
    [class*="chatbot"] ~ * button[type="submit"] {
        background: transparent !important;
        border: none !important;
        padding: 8px !important;
        color: var(--text-secondary) !important;
    }
    
    form:has(textarea[placeholder="Type a message..."]) button:hover {
        background: rgba(79, 140, 255, 0.12) !important;
    }
    
    form:has(textarea[placeholder="Type a message..."]) {
        gap: 12px !important;
        display: flex !important;
    }
    
    /* ============================================
       FILE UPLOAD
       ============================================ */
    .file-preview, 
    [data-testid="file-upload"] {
        background: var(--bg-panel) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
        min-height: 200px !important;
    }
    
    .file-preview:hover, 
    [data-testid="file-upload"]:hover {
        border-color: var(--accent) !important;
        background: var(--bg-panel-soft) !important;
    }
    
    .file-preview *,
    [data-testid="file-upload"] * {
        color: var(--text-primary) !important;
    }
    
    .file-preview .label,
    [data-testid="file-upload"] .label {
        display: none !important;
    }
    
    /* ============================================
       INPUTS & TEXTAREAS
       ============================================ */
    input, 
    textarea {
        background: var(--bg-panel) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 10px !important;
        color: var(--text-primary) !important;
        transition: border-color 0.2s ease !important;
    }
    
    input:focus, 
    textarea:focus {
        border-color: var(--accent) !important;
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(79, 140, 255, 0.12) !important;
    }
    
    textarea[readonly] {
        background: var(--bg-panel) !important;
        color: var(--text-muted) !important;
    }
    
    /* ============================================
       FILE LIST BOX
       ============================================ */
    #file-list-box {
        background: var(--bg-panel) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 12px !important;
        padding: 10px !important;
    }
    
    #file-list-box textarea {
        background: transparent !important;
        border: none !important;
        color: var(--text-secondary) !important;
        padding: 0 !important;
    }
    
    /* ============================================
       CHATBOT CONTAINER
       ============================================ */
    .chatbot {
        border-radius: 16px !important;
        background: linear-gradient(180deg, rgba(18, 26, 43, 0.96), rgba(14, 22, 37, 0.98)) !important;
        border: 1px solid var(--border-strong) !important;
    }

    .chatbot .message-wrap,
    .chatbot > div {
        gap: 8px !important;
        padding: 12px !important;
    }

    .chatbot .placeholder,
    .chatbot [data-testid="chatbot-placeholder"],
    .chatbot .empty,
    .chatbot .empty-chatbot {
        color: var(--text-secondary) !important;
    }

    /* ============================================
       MESSAGE BUBBLES
       ============================================ */
    .message {
        border-radius: 14px !important;
    }

    .message.user {
        background: linear-gradient(135deg, var(--accent), #5ca2ff) !important;
        color: #ffffff !important;
    }
    
    .message.bot {
        background: var(--bg-panel-soft) !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border-strong) !important;
        width: fit-content !important;
        max-width: 90% !important;
    }

    /* 确保消息内所有文本可见 */
    .message.user *,
    .message.bot *,
    .message .md,
    .message .md p,
    .message .md strong,
    .message .md li,
    .message .md code,
    .message .md em,
    .message .md span,
    .message .md div {
        color: inherit !important;
    }
    
    /* 修复折叠面板内的文本颜色 */
    .message.bot details,
    .message.bot summary,
    .message.bot details *,
    .message.bot summary * {
        color: var(--text-primary) !important;
    }
    
    .message.bot details summary {
        color: var(--text-secondary) !important;
    }
    
    /* 确保引用的文本块可读 */
    .message.bot blockquote,
    .message.bot .blockquote {
        color: var(--text-primary) !important;
        border-left-color: var(--accent) !important;
    }
    
    /* 修复系统节点消息中的浅色文字 */
    .message.bot .system-node,
    .message.bot .system-node *,
    .message.bot .collapsible,
    .message.bot .collapsible * {
        color: var(--text-primary) !important;
    }
    
    .message-row img {
        margin: 0px !important;
    }

    .avatar-container img {
        padding: 0px !important;
    }

    /* ============================================
       PROGRESS BAR
       ============================================ */
    .progress-bar-wrap {
        border-radius: 10px !important;
        overflow: hidden !important;
        background: var(--bg-panel) !important;
    }

    .progress-bar {
        border-radius: 10px !important;
        background: var(--accent) !important;
    }
    
    /* ============================================
       TYPOGRAPHY
       ============================================ */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary) !important;
    }

    .gradio-container a {
        color: #8eb6ff !important;
    }

    .gradio-container a:hover {
        color: #bad2ff !important;
    }

    .gradio-container [data-testid="textbox"] label,
    .gradio-container [data-testid="file-upload"] label,
    .gradio-container .wrap label,
    .gradio-container .label-wrap span,
    .gradio-container .gr-button span {
        color: var(--text-secondary) !important;
    }
    
    /* ============================================
       GLOBAL OVERRIDES
       ============================================ */
    * {
        box-shadow: none !important;
    }
    
    footer {
        visibility: hidden;
    }
"""
