package asac.policies.payment_guard

import rego.v1

# Évaluée sur le rapport de l'outil après chaque lancement d'une étape de paiement.
# Un changement de paiement ne se juge pas « à peu près » : un coût inconnu bloque.
block contains "le coût du tour est inconnu" if input.cost_unknown

block contains reason if {
	input.cost_usd > max_turn_cost
	reason := sprintf("un tour a coûté %v USD, au-dessus de %v USD", [input.cost_usd, max_turn_cost])
}

max_turn_cost := 2
