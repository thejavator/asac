package asac.gates.release_test

import rego.v1

import data.asac.gates.release

ok := {"tokens": 1000, "cost_usd": 0.4, "iterations": 1}

test_a_normal_report_passes if {
	count(release.block) == 0 with input as ok
	not release.escalate with input as ok
}

test_an_unknown_cost_blocks if {
	release.block["le coût de l'étape est inconnu"] with input as object.union(ok, {"cost_unknown": true})
}

test_a_cost_over_the_ceiling_blocks if {
	count(release.block) == 1 with input as object.union(ok, {"cost_usd": 3.5})
}

test_a_cost_at_the_ceiling_passes if {
	count(release.block) == 0 with input as object.union(ok, {"cost_usd": 3})
}

test_many_iterations_escalate_without_blocking if {
	release.escalate with input as object.union(ok, {"iterations": 4})
	count(release.block) == 0 with input as object.union(ok, {"iterations": 4})
}

test_exactly_three_iterations_do_not_escalate if {
	not release.escalate with input as object.union(ok, {"iterations": 3})
}
