import React from "react";

const UserAvatar = React.memo(function UserAvatar({ size = 28 }) {
  const id = React.useId().replace(/:/g, "");

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`ubg-${id}`} x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#e2e8f0" />
          <stop offset="100%" stopColor="#cbd5e1" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="34" height="34" rx="10" ry="10" fill={`url(#ubg-${id})`} />
      <circle cx="18" cy="14" r="5.5" fill="#64748b" />
      <path
        d="M8 30 C8 24 12 20 18 20 C24 20 28 24 28 30"
        fill="#64748b"
      />
    </svg>
  );
});

export default UserAvatar;
