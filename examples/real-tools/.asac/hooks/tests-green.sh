#!/bin/sh
# post_step hook: the project's real tests must pass before the step can finish.
# Exit 0 = pass, non-zero = fail (hook contract).
# Attached to the development step in asac.yaml.
# Runs in the run's worktree (ASAC_WORKTREE): that is where the agent's code is.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}/app" || exit 1
PYTHONPATH=. python3 -m unittest discover -s tests -q >&2
