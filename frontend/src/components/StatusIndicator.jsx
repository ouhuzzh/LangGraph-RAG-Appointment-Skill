import React, { useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { RefreshCw } from "lucide-react";
import { statusTone } from "../constants/app";

const StatusIndicator = React.memo(function StatusIndicator({
  icon: Icon,
  label,
  value,
  message,
  metrics,
  onRefresh,
}) {
  const tone = statusTone(value);
  const rowRef = useRef(null);
  const [tooltipStyle, setTooltipStyle] = useState(null);

  const showTooltip = useCallback(() => {
    const el = rowRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setTooltipStyle({
      top: rect.top,
      left: rect.right + 10,
    });
  }, []);

  const hideTooltip = useCallback(() => {
    setTooltipStyle(null);
  }, []);

  return (
    <div
      className="status-indicator"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      <div className="status-indicator__row" ref={rowRef}>
        <Icon size={16} className="status-indicator__icon" />
        <span className="status-indicator__label">{label}</span>
        <span className={`status-dot status-dot--${tone}`} title={value} />
        {onRefresh && (
          <button
            type="button"
            className="icon-button status-indicator__refresh"
            title="刷新状态"
            onClick={onRefresh}
          >
            <RefreshCw size={14} />
          </button>
        )}
      </div>

      {tooltipStyle && createPortal(
        <div
          className="status-indicator__tooltip"
          style={{ position: "fixed", top: tooltipStyle.top, left: tooltipStyle.left }}
        >
          <div className="tooltip-card">
            <div className={`tooltip-card__pill status-pill--${tone}`}>{value}</div>
            {metrics && metrics.map(({ label: ml, value: mv }) => (
              <div key={ml} className="tooltip-card__metric">
                <span>{ml}</span>
                <strong>{mv}</strong>
              </div>
            ))}
            {message && <p className="tooltip-card__msg">{message}</p>}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
});

export default StatusIndicator;
