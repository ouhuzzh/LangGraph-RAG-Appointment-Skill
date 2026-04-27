import React from "react";

const SkeletonLoader = React.memo(function SkeletonLoader({ rows = 3 }) {
  return (
    <div className="skeleton-loader">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={`skeleton-row skeleton-row--${i % 2 === 0 ? "assistant" : "user"}`}
        >
          {i % 2 === 0 && <div className="skeleton-avatar" />}
          <div className="skeleton-bubble">
            <div className="skeleton-line skeleton-line--long" />
            <div className="skeleton-line skeleton-line--medium" />
            {i % 2 === 0 && <div className="skeleton-line skeleton-line--short" />}
          </div>
          {i % 2 !== 0 && <div className="skeleton-avatar skeleton-avatar--user" />}
        </div>
      ))}
    </div>
  );
});

export default SkeletonLoader;
