import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TypingDots from "../components/TypingDots";
import SkeletonLoader from "../components/SkeletonLoader";
import Composer from "../components/Composer";
import ClearConfirmDialog from "../components/ClearConfirmDialog";
import ActionButtons from "../components/ActionButtons";

describe("TypingDots", () => {
  it("renders without crashing", () => {
    render(<TypingDots />);
    expect(screen.getByLabelText("AI 正在思考")).toBeInTheDocument();
  });
});

describe("SkeletonLoader", () => {
  it("renders default 3 rows", () => {
    const { container } = render(<SkeletonLoader />);
    const rows = container.querySelectorAll(".skeleton-row");
    expect(rows.length).toBe(3);
  });

  it("renders custom row count", () => {
    const { container } = render(<SkeletonLoader rows={5} />);
    const rows = container.querySelectorAll(".skeleton-row");
    expect(rows.length).toBe(5);
  });
});

describe("Composer", () => {
  it("renders with send button when not streaming", () => {
    render(
      <Composer
        input="hello"
        onChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
        isStreaming={false}
        disabled={false}
        streamState="idle"
      />,
    );
    expect(screen.getByLabelText("发送消息")).toBeInTheDocument();
  });

  it("renders with stop button when streaming", () => {
    render(
      <Composer
        input=""
        onChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
        isStreaming={true}
        disabled={false}
        streamState="generating"
      />,
    );
    expect(screen.getByLabelText("停止 AI 生成")).toBeInTheDocument();
  });

  it("disables send button when input is empty", () => {
    render(
      <Composer
        input=""
        onChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
        isStreaming={false}
        disabled={false}
        streamState="idle"
      />,
    );
    expect(screen.getByLabelText("发送消息")).toBeDisabled();
  });
});

describe("ClearConfirmDialog", () => {
  it("renders when open", () => {
    // jsdom doesn't implement dialog.showModal, so we mock it
    HTMLDialogElement.prototype.showModal = () => {};
    HTMLDialogElement.prototype.close = () => {};
    render(
      <ClearConfirmDialog
        open={true}
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByText("清空会话")).toBeInTheDocument();
  });
});

describe("ActionButtons", () => {
  it("renders nothing when content has no action pattern", () => {
    const { container } = render(
      <ActionButtons content="这是一段普通文本" onAction={() => {}} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders confirm button for booking confirmation", () => {
    render(
      <ActionButtons content="请**确认预约**以继续" onAction={() => {}} />,
    );
    expect(screen.getByText("确认预约")).toBeInTheDocument();
  });

  it("renders cancel button for cancellation confirmation", () => {
    render(
      <ActionButtons content="请**确认取消**以继续" onAction={() => {}} />,
    );
    expect(screen.getByText("确认取消")).toBeInTheDocument();
  });
});
