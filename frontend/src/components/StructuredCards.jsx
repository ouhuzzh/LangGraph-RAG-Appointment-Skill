import React, { useState } from "react";

/* Clinical annotation cards — quiet surfaces, a thin semantic rule on the
   left (like lab-report flags), uppercase eyebrow labels, one accent color.
   No emoji, no tinted fills: the message text stays the loudest element. */

function DepartmentCard({ department }) {
  return (
    <div className="ui-card ui-card--department">
      <span className="ui-card__eyebrow">推荐科室</span>
      <strong className="ui-card__value">{department}</strong>
    </div>
  );
}

function RiskAlertCard({ level }) {
  const isCritical = level === "critical";
  return (
    <div className={`ui-card ${isCritical ? "ui-card--critical" : "ui-card--warning"}`}>
      <span className="ui-card__eyebrow">{isCritical ? "紧急" : "注意"}</span>
      <strong className="ui-card__value">
        {isCritical ? "请立即就医或拨打 120" : "建议尽快线下就医"}
      </strong>
    </div>
  );
}

function AppointmentCard({ card, onCardAction }) {
  const [chosen, setChosen] = useState("");
  const details = card.details || {};
  const actions = Array.isArray(card.actions) ? card.actions : [];
  const detailText = [details.department, details.date, details.time_slot, details.doctor_name]
    .filter(Boolean)
    .join(" · ");

  const handleClick = (item) => {
    if (chosen || typeof onCardAction !== "function") return;
    setChosen(item.action);
    onCardAction(item.label, { type: item.action, confirmation_id: item.confirmation_id });
  };

  return (
    <div className="ui-card ui-card--appointment">
      <span className="ui-card__eyebrow">预约确认</span>
      <strong className="ui-card__value">
        {detailText || "请回复\u201c确认预约\u201d以完成挂号"}
      </strong>
      {actions.length > 0 && (
        <div className="ui-card__actions">
          {actions.map((item) => (
            <button
              key={item.action}
              type="button"
              className={
                item.action === "confirm_appointment"
                  ? "ui-card__btn ui-card__btn--primary"
                  : "ui-card__btn"
              }
              disabled={Boolean(chosen)}
              onClick={() => handleClick(item)}
            >
              {chosen === item.action ? "已发送" : item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function StructuredCards({ cards, onCardAction }) {
  if (!cards || !cards.length) return null;
  return (
    <div className="structured-cards">
      {cards.map((card, i) => {
        switch (card.card_type) {
          case "department":
            return <DepartmentCard key={i} department={card.department} />;
          case "risk_alert":
            return <RiskAlertCard key={i} level={card.level} />;
          case "appointment_preview":
            return <AppointmentCard key={i} card={card} onCardAction={onCardAction} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
