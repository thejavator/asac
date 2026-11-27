import { describe, expect, it } from "vitest";
import { health, passRate, tokens, usd } from "./overviewView";

const clean = { unavailable: false, integrity_violations: 0, sandbox_denials: 0, problems: 0, pending_gates: 0 };

describe("usd", () => {
  it("shows a dash when nothing was booked", () => {
    expect(usd(0)).toBe("—");
  });
  it("never rounds a real cost down to $0.00", () => {
    expect(usd(0.004)).toBe("< $0.01");
  });
  it("uses two decimals", () => {
    expect(usd(1.5)).toBe("$1.50");
    expect(usd(12.345)).toBe("$12.35");
  });
});

describe("tokens", () => {
  it("compacts thousands and millions", () => {
    expect(tokens(0)).toBe("—");
    expect(tokens(950)).toBe("950");
    expect(tokens(12_400)).toBe("12.4k");
    expect(tokens(2000)).toBe("2k");
    expect(tokens(3_200_000)).toBe("3.2M");
  });
});

describe("passRate", () => {
  it("shows a dash when no hook ran, never 0 %", () => {
    expect(passRate(null)).toBe("—");
    expect(passRate(undefined)).toBe("—");
  });
  it("rounds to a whole percent", () => {
    expect(passRate(2 / 3)).toBe("67 %");
    expect(passRate(1)).toBe("100 %");
  });
});

describe("health", () => {
  it("is on track when nothing needs a person", () => {
    expect(health(clean)).toEqual(["ok", "On track"]);
  });
  it("ranks tampered rules above a failing run", () => {
    expect(health({ ...clean, integrity_violations: 1, problems: 3 })).toEqual(["bad", "Rules tampered"]);
  });
  it("ranks a failing run above sandbox refusals and waiting decisions", () => {
    expect(health({ ...clean, problems: 1, sandbox_denials: 2, pending_gates: 4 })).toEqual(["bad", "Runs need attention"]);
  });
  it("flags sandbox refusals before waiting decisions", () => {
    expect(health({ ...clean, sandbox_denials: 1, pending_gates: 1 })).toEqual(["wait", "Sandbox refusals"]);
  });
  it("says a project that cannot be read is unavailable", () => {
    expect(health({ ...clean, unavailable: true })).toEqual(["bad", "Unavailable"]);
  });
});
