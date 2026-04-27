import React from "react";

const XinyuLogo = React.memo(function XinyuLogo({
  size = 24,
  className = "",
  variant = "default",
  animated = false,
}) {
  const id = React.useId().replace(/:/g, "");
  const flat = variant === "flat" || variant === "glow";

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
        <linearGradient id={`bg-${id}`} x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0f766e" />
          <stop offset="50%" stopColor="#0d9488" />
          <stop offset="100%" stopColor="#14b8a6" />
        </linearGradient>
        <linearGradient id={`heart-${id}`} x1="18" y1="8" x2="18" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="100%" stopColor="#ccfbf1" stopOpacity="0.9" />
        </linearGradient>
        <linearGradient id={`cross-${id}`} x1="18" y1="14" x2="18" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#99f6e4" />
          <stop offset="100%" stopColor="#ffffff" />
        </linearGradient>
        <radialGradient id={`glow-${id}`} cx="50%" cy="30%" r="60%">
          <stop offset="0%" stopColor="#5eead4" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#0d9488" stopOpacity="0" />
        </radialGradient>
      </defs>

      {!flat && (
        <rect
          x="1" y="1" width="34" height="34"
          rx="10" ry="10"
          fill={`url(#bg-${id})`}
        />
      )}

      {variant === "glow" && (
        <circle cx="18" cy="18" r="16" fill={`url(#glow-${id})`} />
      )}

      <path
        d="M18 27 C18 27 9 22 9 15.5 C9 12 11.5 9 14.5 9 C16 9 17.5 10 18 11.5 C18.5 10 20 9 21.5 9 C24.5 9 27 12 27 15.5 C27 22 18 27 18 27Z"
        fill={`url(#heart-${id})`}
        opacity="0.95"
      />

      <rect x="16.5" y="14.5" width="3" height="8" rx="1" fill={`url(#cross-${id})`} opacity="0.92" />
      <rect x="14" y="17" width="8" height="3" rx="1" fill={`url(#cross-${id})`} opacity="0.92" />
    </svg>
  );
});

export default XinyuLogo;
