package asac.gates.payment

import rego.v1

# Gate « qualité » de la revue de sécurité d'un changement de paiement.
# `block` : raisons de refus ; `escalate` : à envoyer à une personne.
# Entrée : le rapport de l'outil (`cost_usd`, `cost_unknown`, `iterations`, `tokens`).

block contains "le coût de la revue est inconnu" if input.cost_unknown

# Une revue qui n'a eu besoin d'aucun tour n'a rien lu : on ne l'accepte pas en silence.
block contains "la revue de sécurité n'a fait aucun tour" if input.iterations == 0

# Plus de deux tours pour une revue en lecture seule : à regarder par une personne.
escalate if input.iterations > 2
