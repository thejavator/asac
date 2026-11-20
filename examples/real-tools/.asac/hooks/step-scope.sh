#!/bin/sh
# pre_tool + post_step hook. Checks the result of a step, not who produced it.
# requirements: SPEC.md must exist with acceptance criteria and app/ must be unchanged.
[ "$ASAC_STEP" = "requirements" ] || exit 0
snap=".asac-state/scope-$ASAC_RUN_ID-$ASAC_STEP.sha"
fingerprint() {
  find app -type f -not -path '*/__pycache__/*' | sort | xargs shasum | shasum | cut -d' ' -f1
}
if [ "$ASAC_HOOK_ATTACH" = "pre_tool" ]; then
  mkdir -p .asac-state
  fingerprint > "$snap"
  exit 0
fi
if [ ! -s SPEC.md ]; then
  echo "SPEC.md is missing or empty" >&2
  exit 1
fi
if ! grep -qi "acceptance" SPEC.md; then
  echo "SPEC.md has no acceptance criteria" >&2
  exit 1
fi
if [ -f "$snap" ] && [ "$(fingerprint)" != "$(cat "$snap")" ]; then
  echo "app/ was modified during the requirements step" >&2
  exit 1
fi
