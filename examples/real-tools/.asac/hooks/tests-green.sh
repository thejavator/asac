#!/bin/sh
# post_step hook: the project's real tests must pass before the step can finish.
# Exit 0 = pass, non-zero = fail (hook contract).
# Only meaningful once code exists: skip the other steps.
[ "${ASAC_STEP:-development}" = "development" ] || exit 0
cd "$(dirname "$0")/../../app" || exit 1
PYTHONPATH=. python3 -m unittest discover -s tests -q >&2
