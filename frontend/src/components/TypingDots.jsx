import React from "react";

const TypingDots = React.memo(function TypingDots() {
  return (
    <span className="typing-indicator" aria-label="AI 正在思考">
      <span className="typing-dots">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </span>
      <span className="typing-label">思考中</span>
    </span>
  );
});

export default TypingDots;
