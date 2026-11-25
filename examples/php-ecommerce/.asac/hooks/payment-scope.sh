#!/bin/sh
# Un changement de paiement ne sort pas de son périmètre : src/Payment, src/Pricing et leurs tests.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
base=$(git merge-base HEAD "$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo main)" 2>/dev/null \
       || git merge-base HEAD master 2>/dev/null || git rev-list --max-parents=0 HEAD | tail -1)
changed=$({ git diff --name-only "$base"; git ls-files --others --exclude-standard; } | sort -u)
# Les fichiers qu'ASAC monte lui-même dans le worktree (skills, consignes, MCP) ne sont pas le travail.
mounts='\.claude/skills/[^/]+/SKILL\.md|\.bob/skills/[^/]+/SKILL\.md|\.agent/skills/[^/]+/SKILL\.md|\.cursor/rules/asac-[^/]+\.mdc|\.github/instructions/asac-[^/]+\.instructions\.md|CLAUDE\.md|AGENTS\.md|\.mcp\.json'
allowed="^(${mounts}|src/Payment/|src/Pricing/|tests/Payment/|tests/Pricing/|SPEC[.]md\$|[.]asac-state/)"
outside=$(printf '%s\n' "$changed" | grep -vE "$allowed" | grep -v '^$' || true)
[ -z "$outside" ] || { echo "payment-scope: fichiers modifiés hors du périmètre paiement/prix :" >&2; printf '%s\n' "$outside" | head -8 >&2; exit 1; }
# Aucune clé de production, même dans un fichier du périmètre.
if printf '%s\n' "$changed" | grep -E '^(src|tests)/' | xargs -r grep -lE 'sk_live_|pk_live_' 2>/dev/null | grep -q .; then
  echo "payment-scope: une clé de production apparaît dans le code" >&2; exit 1
fi
