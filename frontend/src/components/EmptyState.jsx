import React from "react";
import { Stethoscope, Brain, CalendarCheck, HelpCircle, Activity } from "lucide-react";
import { EMPTY_STATE_CAPABILITIES, STARTER_PROMPTS } from "../constants/app";

const promptIcons = {
  hypertension: Activity,
  triage: HelpCircle,
  booking: CalendarCheck,
  cancel: Brain,
};

const EmptyState = React.memo(function EmptyState({ onSendMessage }) {
  return (
    <div className="empty-state">
      <div className="empty-state__hero">
        <div className="empty-state__icon-wrap">
          <div className="empty-state__icon-ring" />
          <Stethoscope size={36} className="empty-state__icon" />
        </div>
        <h2 className="empty-state__title">你好，我是宁和医疗助手</h2>
        <p className="empty-state__subtitle">
          专业的 AI 医疗咨询助手，随时为您提供健康指导与就医帮助
        </p>
        <ul className="empty-state__caps">
          {EMPTY_STATE_CAPABILITIES.map((cap) => (
            <li key={cap}>
              <span className="empty-state__cap-dot" />
              {cap}
            </li>
          ))}
        </ul>
      </div>

      <div className="prompt-grid">
        {STARTER_PROMPTS.map(({ key, text }, i) => {
          const Icon = promptIcons[key] || HelpCircle;
          return (
          <button
            key={text}
            type="button"
            className="prompt-card"
            style={{ animationDelay: `${0.1 + i * 0.07}s` }}
            onClick={() => onSendMessage(text)}
          >
            <span className="prompt-card__icon">
              <Icon size={18} />
            </span>
            <span className="prompt-card__text">{text}</span>
          </button>
          );
        })}
      </div>
    </div>
  );
});

export default EmptyState;
