import type { components } from "../api/schema";

type Trigger = components["schemas"]["TriggerOut"];

/** "PAY-139 in Jira": a link when the project has a tracker, plain text otherwise. */
export function TriggerLink({ trigger }: { trigger: Trigger }) {
  const hint = trigger.title ? `${trigger.title}${trigger.status ? ` (${trigger.status})` : ""}` : undefined;
  if (!trigger.url) return <span title={hint}>{trigger.label}</span>;
  return (
    <a href={trigger.url} rel="noreferrer noopener" target="_blank" title={hint}>
      {trigger.label}
    </a>
  );
}
