#!/bin/sh
# post_step hook of the development step: the project's real tests must pass.
# Exit 0 = pass, non-zero = fail. Runs in the run's worktree (ASAC_WORKTREE).
# This template runs Python's unittest. For another stack, replace the last line with your
# test command (for example `npm test` or `mvn -q test`).
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
python3 -m unittest discover -q >&2
