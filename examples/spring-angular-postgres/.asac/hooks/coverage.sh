#!/bin/sh
# Couverture du backend (JaCoCo) au moins égale au seuil. Le seuil par défaut est 80 %.
floor="${ASAC_COVERAGE_FLOOR:-80}"
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}/backend" || exit 1
report=target/site/jacoco/jacoco.csv
[ -f "$report" ] || mvn -q -B -ntp verify >&2 || exit 1
[ -f "$report" ] || { echo "pas de rapport JaCoCo ($report)" >&2; exit 1; }
# colonnes : GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,...
pct=$(awk -F, 'NR>1 {m+=$4; c+=$5} END {if (m+c==0) print 0; else printf "%d", 100*c/(m+c)}' "$report")
echo "couverture : ${pct} % (seuil ${floor} %)" >&2
[ "$pct" -ge "$floor" ]
