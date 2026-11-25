package asac.gates.payment_test

import rego.v1

import data.asac.gates.payment

ok := {"cost_usd": 0.4, "iterations": 1}

test_a_normal_review_passes if {
	count(payment.block) == 0 with input as ok
	not payment.escalate with input as ok
}

test_an_unknown_cost_blocks if {
	payment.block["le coût de la revue est inconnu"] with input as object.union(ok, {"cost_unknown": true})
}

test_a_review_with_no_turn_blocks if {
	payment.block["la revue de sécurité n'a fait aucun tour"] with input as object.union(ok, {"iterations": 0})
}

test_three_turns_escalate_without_blocking if {
	payment.escalate with input as object.union(ok, {"iterations": 3})
	count(payment.block) == 0 with input as object.union(ok, {"iterations": 3})
}

test_two_turns_do_not_escalate if {
	not payment.escalate with input as object.union(ok, {"iterations": 2})
}
