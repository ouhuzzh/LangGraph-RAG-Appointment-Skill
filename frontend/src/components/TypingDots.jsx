import React from "react";

const TypingDots = React.memo(function TypingDots() {
  return (
    <span className="typing-dots" aria-label="AI 正在思考">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
});

export default TypingDots;
