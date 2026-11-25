import type { Schema } from "../api/client";
import { DefinitionFlow } from "./app/StepNode";

type Step = Schema["PipelineStepOut"];

/** Steps left to right with the gate role under each; the selected step is marked. */
export function PipelineGraph({ steps, current, onPick }: { steps: Step[]; current?: string; onPick: (id: string) => void }) {
  return <DefinitionFlow steps={steps} current={current} onPick={onPick} />;
}
