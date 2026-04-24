import React from "react";
import { Stethoscope, Brain, CalendarCheck, HelpCircle, Activity } from "lucide-react";

const starterPrompts = [
  { icon: Activity, text: "高血压应该注意什么？" },
  { icon: HelpCircle, text: "我咳嗽三天了，挂什么科？" },
  { icon: CalendarCheck, text: "我想挂呼吸内科的号" },
  { icon: Brain, text: "取消刚才的预约" },
];

const capabilities = [
  "解答医学常识与健康咨询",
  "智能分诊推荐科室",
  "预约挂号与取消",
  "查询医院信息与就医指引",
];

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
          {capabilities.map((cap) => (
            <li key={cap}>
              <span className="empty-state__cap-dot" />
              {cap}
            </li>
          ))}
        </ul>
      </div>

      <div className="prompt-grid">
        {starterPrompts.map(({ icon: Icon, text }, i) => (
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
        ))}
      </div>
    </div>
  );
});

export default EmptyState;
