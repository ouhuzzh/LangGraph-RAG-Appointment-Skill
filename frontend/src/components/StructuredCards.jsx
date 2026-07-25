import React from "react";

const cardBase = {
  display: "flex",
  alignItems: "center",
  gap: "0.75rem",
  padding: "0.75rem 1rem",
  borderRadius: "0.75rem",
  marginTop: "0.5rem",
  fontSize: "0.875rem",
  lineHeight: 1.4,
};

const styles = {
  department: { ...cardBase, background: "var(--color-surface-elevated, #f0fdf4)", border: "1px solid var(--color-border, #bbf7d0)" },
  risk_critical: { ...cardBase, background: "#fef2f2", border: "1px solid #fecaca" },
  risk_high: { ...cardBase, background: "#fffbeb", border: "1px solid #fde68a" },
  appointment: { ...cardBase, background: "var(--color-surface-elevated, #eff6ff)", border: "1px solid var(--color-border, #bfdbfe)" },
  icon: { fontSize: "1.5rem", flexShrink: 0 },
  label: { fontSize: "0.75rem", opacity: 0.7, display: "block" },
  value: { fontWeight: 600 },
};

function DepartmentCard({ department }) {
  return (
    <div style={styles.department}>
      <span style={styles.icon}>🏥</span>
      <div>
        <span style={styles.label}>推荐科室</span>
        <strong style={styles.value}>{department}</strong>
      </div>
    </div>
  );
}

function RiskAlertCard({ level }) {
  const isCritical = level === "critical";
  return (
    <div style={isCritical ? styles.risk_critical : styles.risk_high}>
      <span style={styles.icon}>{isCritical ? "🚨" : "⚠️"}</span>
      <div>
        <span style={styles.label}>{isCritical ? "紧急" : "注意"}</span>
        <span style={styles.value}>
          {isCritical ? "请立即就医或拨打 120" : "建议尽快线下就医"}
        </span>
      </div>
    </div>
  );
}

function AppointmentCard() {
  return (
    <div style={styles.appointment}>
      <span style={styles.icon}>📅</span>
      <div>
        <span style={styles.label}>预约确认</span>
        <span style={styles.value}>请回复"确认预约"以完成挂号</span>
      </div>
    </div>
  );
}

export default function StructuredCards({ cards }) {
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
            return <AppointmentCard key={i} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
