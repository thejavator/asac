#!/bin/sh
# Hook contract: exit 0 = pass, non-zero = fail.
# Reads a unified diff on stdin and fails if it adds an obvious secret.
if grep -E '^\+.*(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|password *= *"[^"]+")' >/dev/null; then
  echo "secret-scan: possible secret in the diff" >&2
  exit 1
fi
exit 0
