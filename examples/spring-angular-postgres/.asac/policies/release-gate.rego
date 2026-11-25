package asac.gates.release

import rego.v1

# Gate « qualité » de l'étape verification. Une politique rend deux choses :
#   block    : un ensemble de raisons ; s'il n'est pas vide, l'étape est bloquée (code 3)
#   escalate : vrai pour envoyer l'étape à une personne (code 2)
#
# Ce que le moteur de la v1 met dans `input` : le rapport de l'outil de l'étape (`tokens`,
# `cost_usd`, `cost_unknown`, `iterations`) et ce que votre harnais y ajoute. Elle n'y met PAS
# la couverture ni les alertes de sécurité : ce sont des CONTRÔLES (hooks coverage.sh,
# contract.sh) qui les vérifient. La politique juge donc ce qui est dans le rapport, et le
# choix est écrit ici plutôt que de supposer des champs que personne ne remplit.

# Un coût inconnu ne se range jamais à zéro : on ne livre pas ce qu'on n'a pas pu chiffrer.
block contains "le coût de l'étape est inconnu" if input.cost_unknown

# Un seuil de dépense par étape de vérification.
block contains reason if {
	input.cost_usd > max_step_cost
	reason := sprintf("coût de l'étape %v USD au-dessus du plafond %v USD", [input.cost_usd, max_step_cost])
}

# Une étape qui a tourné plus de fois que prévu : à regarder par une personne, pas à refuser.
escalate if input.iterations > 3

max_step_cost := 3
