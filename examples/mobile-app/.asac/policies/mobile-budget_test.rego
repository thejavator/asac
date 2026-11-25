package asac.policies.mobile_budget_test

import rego.v1

import data.asac.policies.mobile_budget

test_a_cheap_turn_passes if {
	count(mobile_budget.block) == 0 with input as {"cost_usd": 0.3}
}

test_an_unknown_cost_blocks if {
	mobile_budget.block["le coût du tour est inconnu"] with input as {"cost_unknown": true}
}

test_an_expensive_turn_blocks if {
	count(mobile_budget.block) == 1 with input as {"cost_usd": 4.5}
}

test_a_turn_at_the_ceiling_passes if {
	count(mobile_budget.block) == 0 with input as {"cost_usd": 4}
}
