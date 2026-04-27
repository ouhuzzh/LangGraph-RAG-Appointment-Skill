import { describe, it, expect } from "vitest";
import { statusTone, STARTER_PROMPTS, EMPTY_STATE_CAPABILITIES } from "../constants/app";

describe("statusTone", () => {
  it("returns 'good' for ready/completed", () => {
    expect(statusTone("ready")).toBe("good");
    expect(statusTone("completed")).toBe("good");
  });

  it("returns 'bad' for failed/error", () => {
    expect(statusTone("failed")).toBe("bad");
    expect(statusTone("error")).toBe("bad");
  });

  it("returns 'warn' for no_documents/pending_rebuild", () => {
    expect(statusTone("no_documents")).toBe("warn");
    expect(statusTone("pending_rebuild")).toBe("warn");
  });

  it("returns 'info' for unknown values", () => {
    expect(statusTone("loading")).toBe("info");
    expect(statusTone("preparing")).toBe("info");
    expect(statusTone("")).toBe("info");
  });
});

describe("STARTER_PROMPTS", () => {
  it("has 4 prompts with key and text", () => {
    expect(STARTER_PROMPTS).toHaveLength(4);
    STARTER_PROMPTS.forEach((p) => {
      expect(p).toHaveProperty("key");
      expect(p).toHaveProperty("text");
      expect(p.text.length).toBeGreaterThan(0);
    });
  });
});

describe("EMPTY_STATE_CAPABILITIES", () => {
  it("has 4 capability descriptions", () => {
    expect(EMPTY_STATE_CAPABILITIES).toHaveLength(4);
    EMPTY_STATE_CAPABILITIES.forEach((cap) => {
      expect(typeof cap).toBe("string");
      expect(cap.length).toBeGreaterThan(0);
    });
  });
});
