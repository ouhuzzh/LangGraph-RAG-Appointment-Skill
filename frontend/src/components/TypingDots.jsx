import React from "react";

const TypingDots = React.memo(function TypingDots() {
  return (
    <div className="typing-indicator" aria-label="AI 正在思考">
      <span />
      <span />
      <span />
    </div>
  );
});

export default TypingDots;
