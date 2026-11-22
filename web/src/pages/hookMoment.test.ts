import { describe, expect, it } from "vitest";
import { hookMoment } from "./RunDetail";

describe("hookMoment", () => {
  it("reads a hook that ran before the agent", () => {
    expect(hookMoment("pre_tool no-secrets")).toEqual({ name: "no-secrets", moment: "before the agent of step" });
  });
  it("reads a hook that ran after the step", () => {
    expect(hookMoment("post_step tests-green")).toEqual({ name: "tests-green", moment: "after step" });
  });
  it("does not invent a moment for an audit written before it was recorded", () => {
    expect(hookMoment("no-secrets")).toEqual({ name: "no-secrets", moment: "during step" });
  });
  it("keeps a hook name that is not a moment word", () => {
    expect(hookMoment("step-scope")).toEqual({ name: "step-scope", moment: "during step" });
  });
});
