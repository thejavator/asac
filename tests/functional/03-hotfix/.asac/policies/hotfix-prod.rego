package asac.steps.hotfix_prod

import rego.v1

# Déploiement direct en production : uniquement pour un Bug P1 avec un ticket rattaché.
# Les champs sont rapportés par le harnais ; avec le harnais fake on les injecte via
# ASAC_FAKE_RESULT. Un champ absent bloque (fail closed).
block contains reason if {
	not input.issue_type == "Bug"
	reason := "hotfix: issue type must be Bug"
}

block contains reason if {
	not input.priority == "P1"
	reason := "hotfix: priority must be P1"
}

block contains reason if {
	not input.ticket
	reason := "hotfix: a ticket must be attached"
}
