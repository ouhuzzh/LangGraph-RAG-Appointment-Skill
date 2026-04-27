import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  handleReload() {
    this.setState({ hasError: false, error: null });
  }

  handleHardReload() {
    window.location.reload();
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="error-boundary">
        <div className="error-boundary__icon">
          <AlertTriangle size={32} />
        </div>
        <h2 className="error-boundary__title">页面出了点问题</h2>
        <p className="error-boundary__desc">
          应用遇到了一个意外错误，请尝试重新加载。如果问题持续，请刷新页面。
        </p>
        {this.state.error && (
          <pre className="error-boundary__detail">
            {this.state.error.message || String(this.state.error)}
          </pre>
        )}
        <div className="error-boundary__actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={() => this.handleReload()}
          >
            <RefreshCw size={16} />
            重试
          </button>
          <button
            type="button"
            className="primary-btn"
            onClick={() => this.handleHardReload()}
          >
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}
