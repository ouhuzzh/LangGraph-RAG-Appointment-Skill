import React from "react";

/**
 * 心语医疗 AI Agent Logo
 *
 * 设计语言：极简高级，参考 Claude / Gemini / ChatGPT 图标风格
 *  - 背景：圆角方形，深色渐变（teal → indigo），专业感
 *  - 中心：单一「流线符文」— 两条相交的平滑曲线，象征 AI 思维流
 *  - 小圆点：右上角一个高亮小圆，象征「在线 / 智能 agent 激活」
 *  - 无多余装饰，一眼辨识
 */
const XinyuLogo = React.memo(function XinyuLogo({
  size = 24,
  className = "",
  variant = "default", // "default" | "flat"（无背景，用于深色背景上）
  animated = false,
}) {
  const id = React.useId().replace(/:/g, "");
  const flat = variant === "flat";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`xinyu-logo${animated ? " xinyu-logo--pulse" : ""}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <defs>
        {/* 背景渐变：深 teal → indigo，沉稳高级 */}
        <linearGradient id={`bg-${id}`} x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#0d9488" />
          <stop offset="100%" stopColor="#4f46e5" />
        </linearGradient>

        {/* 符文笔画渐变：白→浅teal */}
        <linearGradient id={`stroke-${id}`} x1="6" y1="10" x2="30" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#ffffff" stopOpacity="0.98" />
          <stop offset="100%" stopColor="#99f6e4" stopOpacity="0.85" />
        </linearGradient>

        {/* 小圆点渐变 */}
        <radialGradient id={`dot-${id}`} cx="50%" cy="30%" r="70%">
          <stop offset="0%"   stopColor="#ffffff" />
          <stop offset="100%" stopColor="#5eead4" />
        </radialGradient>
      </defs>

      {/* ── 背景：圆角方形 ── */}
      {!flat && (
        <rect
          x="1" y="1" width="34" height="34"
          rx="9" ry="9"
          fill={`url(#bg-${id})`}
        />
      )}

      {/*
        ── 中心「流线符文」──
        两条曲线交叉，形成∞/流动感，象征 AI 持续推理循环
        上弧线：左→右，向下拱
        下弧线：左→右，向上拱
        两线在中心交叉，形成简洁「神经流」
      */}
      <path
        d="M8 13 C11 8, 18 9, 18 13 S25 18, 28 13"
        stroke={`url(#stroke-${id})`}
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M8 23 C11 28, 18 27, 18 23 S25 18, 28 23"
        stroke={`url(#stroke-${id})`}
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />

      {/* 中心交叉点高亮小圆 */}
      <circle cx="18" cy="18" r="2" fill="white" opacity="0.95" />

      {/* ── 右上角激活小圆点（agent 在线标志） ── */}
      <circle cx="27.5" cy="8.5" r="3.2" fill={`url(#dot-${id})`} opacity="0.95" />
    </svg>
  );
});

export default XinyuLogo;
