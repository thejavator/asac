package asac.policies.mobile_budget

import rego.v1

# Évaluée sur le rapport de l'outil après chaque lancement de l'étape `implementation`.
# Un coût inconnu ne se range pas à zéro : un budget qu'on ne peut pas vérifier bloque.
block contains "le coût du tour est inconnu" if input.cost_unknown

# Un seul tour qui coûte plus de 4 USD est anormal pour un écran : on s'arrête et on regarde.
block contains reason if {
	input.cost_usd > max_turn_cost
	reason := sprintf("un tour a coûté %v USD, au-dessus de %v USD", [input.cost_usd, max_turn_cost])
}

max_turn_cost := 4
