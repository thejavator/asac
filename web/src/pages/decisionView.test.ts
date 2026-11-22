import { describe, expect, it } from "vitest";
import { dueText, signatureNote } from "./decisionView";

describe("dueText", () => {
  it("says nothing when the gate has no due time", () => {
    expect(dueText(null)).toBe("");
    expect(dueText(undefined)).toBe("");
  });
  it("reads minutes, hours and days left", () => {
    expect(dueText(40 * 60)).toBe("due in 40 min");
    expect(dueText(3 * 3600)).toBe("due in 3 h");
    expect(dueText(26 * 3600)).toBe("due tomorrow");
    expect(dueText(5 * 24 * 3600)).toBe("due in 5 days");
  });
  it("says how late a decision is", () => {
    expect(dueText(-3600)).toBe("1 h late");
    expect(dueText(-20 * 60)).toBe("20 min late");
  });
  it("never shows a negative or zero duration as 'due in 0'", () => {
    expect(dueText(0)).toBe("due now");
    expect(dueText(20)).toBe("due now");
  });
});

describe("signatureNote", () => {
  it("names who signed a bootstrapped evidence, as the mockup does", () => {
    expect(signatureNote({ bootstrapped: true, approved_by: "Malik B.", at: "2026-11-12T10:00:00Z" })).toBe(
      "bootstrapped · imported by Malik B. on 2026-11-12",
    );
  });
  it("says who signed an agent's evidence when someone approved it", () => {
    expect(signatureNote({ bootstrapped: false, approved_by: "Camille", at: "2026-11-12T10:00:00Z" })).toBe(
      "approved by Camille",
    );
  });
  it("does not invent a signer", () => {
    expect(signatureNote({ bootstrapped: true, approved_by: null, at: "2026-11-12T10:00:00Z" })).toBe(
      "bootstrapped · imported on 2026-11-12",
    );
  });
});
