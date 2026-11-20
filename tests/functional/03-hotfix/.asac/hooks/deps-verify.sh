#!/bin/sh
# Hook contract: exit 0 = pass, non-zero = fail.
# Reads one dependency coordinate per line (group:artifact:version) on stdin
# and fails if one is not on the allowed list. Illustrative allowlist check.
allowed="$(dirname "$0")/allowed-deps.txt"
status=0
while read -r dep; do
  [ -z "$dep" ] && continue
  if ! grep -qxF "$dep" "$allowed"; then
    echo "deps-verify: '$dep' is not on the allowed list" >&2
    status=1
  fi
done
exit $status
