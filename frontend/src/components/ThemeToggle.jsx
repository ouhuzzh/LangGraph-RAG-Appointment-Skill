import React from "react";
import { Sun, Moon } from "lucide-react";

const ThemeToggle = React.memo(function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      title={isDark ? "切换亮色模式" : "切换暗色模式"}
      aria-label={isDark ? "切换亮色模式" : "切换暗色模式"}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
      <span>{isDark ? "亮色" : "暗色"}</span>
    </button>
  );
});

export default ThemeToggle;
