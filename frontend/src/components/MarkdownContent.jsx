import React, { lazy, Suspense, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Lazy-load syntax highlighter to keep main bundle lean
const SyntaxHighlighter = lazy(() =>
  import("react-syntax-highlighter/dist/esm/prism-light").then((mod) => ({
    default: mod.default,
  }))
);
const themePromise = import("react-syntax-highlighter/dist/esm/styles/prism/one-light").then(
  (m) => m.default
);

// Simple eager fallback for code blocks while highlighter loads
function CodeFallback({ children }) {
  return (
    <pre className="code-block" style={{ overflow: "auto" }}>
      <code>{children}</code>
    </pre>
  );
}

// react-markdown v9: no "inline" prop — detect by newline presence
function CodeBlock({ className, children, node, ...props }) {
  const match = /language-(\w+)/.exec(className || "");
  const raw = String(children).replace(/\n$/, "");
  const isBlock = match || raw.includes("\n");

  if (isBlock) {
    return (
      <Suspense fallback={<CodeFallback>{raw}</CodeFallback>}>
        <LazyHighlighter language={match ? match[1] : "text"} raw={raw} {...props} />
      </Suspense>
    );
  }
  return (
    <code className={className ? `${className} inline-code` : "inline-code"} {...props}>
      {children}
    </code>
  );
}

function LazyHighlighter({ language, raw, ...props }) {
  const [theme, setTheme] = React.useState(null);
  React.useEffect(() => {
    themePromise.then(setTheme);
  }, []);

  if (!theme) return <CodeFallback>{raw}</CodeFallback>;

  return (
    <SyntaxHighlighter
      style={theme}
      language={language}
      PreTag="div"
      className="code-block"
      {...props}
    >
      {raw}
    </SyntaxHighlighter>
  );
}

const markdownComponents = {
  code: CodeBlock,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

const MarkdownContent = React.memo(function MarkdownContent({ content, isStreaming }) {
  if (!content) return null;

  return (
    <div className={`markdown-body${isStreaming ? " markdown-body--streaming" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
      {isStreaming && <span className="typing-cursor" aria-hidden="true" />}
    </div>
  );
});

export default MarkdownContent;
