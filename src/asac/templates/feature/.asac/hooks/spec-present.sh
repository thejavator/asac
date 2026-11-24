#!/bin/sh
# post_step hook of the requirements step: SPEC.md exists and lists acceptance criteria.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
if [ ! -s SPEC.md ]; then
  echo "SPEC.md is missing or empty" >&2
  exit 1
fi
if ! grep -qi "acceptance" SPEC.md; then
  echo "SPEC.md has no acceptance criteria" >&2
  exit 1
fi
exit 0
