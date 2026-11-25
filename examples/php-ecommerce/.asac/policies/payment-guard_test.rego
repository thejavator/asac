package asac.policies.payment_guard_test

import rego.v1

import data.asac.policies.payment_guard

test_a_cheap_turn_passes if {
	count(payment_guard.block) == 0 with input as {"cost_usd": 0.5}
}

test_an_unknown_cost_blocks if {
	payment_guard.block["le coût du tour est inconnu"] with input as {"cost_unknown": true}
}

test_a_turn_over_the_ceiling_blocks if {
	count(payment_guard.block) == 1 with input as {"cost_usd": 2.5}
}

test_a_turn_at_the_ceiling_passes if {
	count(payment_guard.block) == 0 with input as {"cost_usd": 2}
}
