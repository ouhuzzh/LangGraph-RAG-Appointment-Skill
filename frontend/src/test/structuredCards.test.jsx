import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import StructuredCards from "../components/StructuredCards";
import { reducer } from "../hooks/useChatSession";

describe("StructuredCards", () => {
  it("renders department recommendation card", () => {
    render(<StructuredCards cards={[{ card_type: "department", department: "心内科" }]} />);
    expect(screen.getByText("推荐科室")).toBeInTheDocument();
    expect(screen.getByText("心内科")).toBeInTheDocument();
  });

  it("renders critical risk alert card", () => {
    render(<StructuredCards cards={[{ card_type: "risk_alert", level: "critical" }]} />);
    expect(screen.getByText("请立即就医或拨打 120")).toBeInTheDocument();
  });

  it("renders high risk alert card", () => {
    render(<StructuredCards cards={[{ card_type: "risk_alert", level: "high" }]} />);
    expect(screen.getByText("建议尽快线下就医")).toBeInTheDocument();
  });

  it("renders appointment preview card", () => {
    render(<StructuredCards cards={[{ card_type: "appointment_preview" }]} />);
    expect(screen.getByText("预约确认")).toBeInTheDocument();
  });

  it("renders nothing for empty cards", () => {
    const { container } = render(<StructuredCards cards={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("ignores unknown card types without crashing", () => {
    const { container } = render(<StructuredCards cards={[{ card_type: "unknown_future_type" }]} />);
    expect(container.querySelector(".structured-cards")).toBeInTheDocument();
  });

  it("renders action buttons and fires structured confirm on click", () => {
    const onCardAction = vi.fn();
    const card = {
      card_type: "appointment_preview",
      details: { department: "呼吸内科", date: "2026-08-01", time_slot: "上午" },
      actions: [
        { label: "确认预约", action: "confirm_appointment", confirmation_id: "cid-1" },
        { label: "暂不预约", action: "abort_appointment", confirmation_id: "cid-1" },
      ],
    };
    render(<StructuredCards cards={[card]} onCardAction={onCardAction} />);

    const confirmBtn = screen.getByRole("button", { name: "确认预约" });
    fireEvent.click(confirmBtn);

    expect(onCardAction).toHaveBeenCalledWith("确认预约", {
      type: "confirm_appointment",
      confirmation_id: "cid-1",
    });
    // Both buttons lock after a choice — double-click cannot double-send.
    expect(screen.getByRole("button", { name: "已发送" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "暂不预约" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "已发送" }));
    expect(onCardAction).toHaveBeenCalledTimes(1);
  });

  it("renders plain preview card without buttons when no actions", () => {
    render(<StructuredCards cards={[{ card_type: "appointment_preview" }]} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("chat reducer APPEND_CARD_TO_LAST", () => {
  it("appends a card to the last assistant message", () => {
    const state = {
      messages: [
        { role: "user", content: "胸痛挂什么科" },
        { role: "assistant", content: "建议心内科" },
      ],
    };
    const next = reducer(state, {
      type: "APPEND_CARD_TO_LAST",
      payload: { card_type: "department", department: "心内科" },
    });
    expect(next.messages[1].cards).toHaveLength(1);
    expect(next.messages[1].cards[0].department).toBe("心内科");
  });

  it("accumulates multiple cards", () => {
    const state = {
      messages: [{ role: "assistant", content: "答案", cards: [{ card_type: "department" }] }],
    };
    const next = reducer(state, {
      type: "APPEND_CARD_TO_LAST",
      payload: { card_type: "risk_alert", level: "high" },
    });
    expect(next.messages[0].cards).toHaveLength(2);
  });

  it("is a no-op when last message is from the user", () => {
    const state = { messages: [{ role: "user", content: "hi" }] };
    const next = reducer(state, {
      type: "APPEND_CARD_TO_LAST",
      payload: { card_type: "department" },
    });
    expect(next.messages[0].cards).toBeUndefined();
  });

  it("does not mutate the previous state", () => {
    const state = { messages: [{ role: "assistant", content: "x" }] };
    reducer(state, { type: "APPEND_CARD_TO_LAST", payload: { card_type: "department" } });
    expect(state.messages[0].cards).toBeUndefined();
  });
});
