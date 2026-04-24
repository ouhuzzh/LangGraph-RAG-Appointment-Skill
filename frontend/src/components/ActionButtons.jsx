import React from "react";
import { CheckCircle, XCircle } from "lucide-react";

const ACTION_PATTERN = /\*\*(确认预约|确认取消)\*\*/g;

const ActionButtons = React.memo(function ActionButtons({ content, onAction }) {
  if (!content) return null;

  const matches = [...content.matchAll(ACTION_PATTERN)];
  if (matches.length === 0) return null;

  const actions = [...new Set(matches.map((m) => m[1]))];

  return (
    <div className="action-buttons">
      {actions.map((action) => (
        <button
          key={action}
          type="button"
          className={`action-btn ${action === "确认预约" ? "action-btn--confirm" : "action-btn--cancel"}`}
          onClick={() => onAction(action)}
        >
          {action === "确认预约" ? (
            <CheckCircle size={16} />
          ) : (
            <XCircle size={16} />
          )}
          {action}
        </button>
      ))}
    </div>
  );
});

export default ActionButtons;
