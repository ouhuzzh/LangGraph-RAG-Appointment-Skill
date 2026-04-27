/**
 * Export chat messages to Markdown format
 */
export function exportAsMarkdown(messages, threadId) {
  const lines = [`# 心语医疗小助手 · 对话记录`, ``];
  if (threadId) {
    lines.push(`> 会话 ID: ${threadId}`);
    lines.push(`> 导出时间: ${new Date().toLocaleString("zh-CN")}`);
    lines.push(``);
  }

  messages.forEach((msg) => {
    const time = msg.timestamp
      ? new Date(msg.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
      : "";
    const label = msg.role === "user" ? "🧑 我" : "🤖 心语医疗 AI";
    lines.push(`### ${label}${time ? ` · ${time}` : ""}`);
    lines.push(``);
    lines.push(msg.content || "（空消息）");
    lines.push(``);
    if (msg.interrupted) {
      lines.push(`*— 生成已中断*`);
      lines.push(``);
    }
  });

  return lines.join("\n");
}

/**
 * Export chat messages to JSON format
 */
export function exportAsJSON(messages, threadId) {
  const data = {
    threadId,
    exportedAt: new Date().toISOString(),
    messageCount: messages.length,
    messages: messages.map((msg) => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      timestamp: msg.timestamp,
      interrupted: msg.interrupted || false,
    })),
  };
  return JSON.stringify(data, null, 2);
}

/**
 * Trigger a file download in the browser
 */
export function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Export chat and trigger download
 */
export function exportChat(messages, threadId, format = "markdown") {
  const safeId = threadId ? threadId.slice(0, 8) : "chat";
  const date = new Date().toISOString().slice(0, 10);

  if (format === "json") {
    const content = exportAsJSON(messages, threadId);
    downloadFile(content, `心语对话_${safeId}_${date}.json`, "application/json");
  } else {
    const content = exportAsMarkdown(messages, threadId);
    downloadFile(content, `心语对话_${safeId}_${date}.md`, "text/markdown");
  }
}
