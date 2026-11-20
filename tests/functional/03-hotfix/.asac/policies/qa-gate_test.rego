package asac.gates.qa_test

import rego.v1

import data.asac.gates.qa

ok := {"findings_count": 0, "coverage": 90, "skill_params": {"coverage_min": 85}, "sast_high_count": 0}

test_clean_run_is_not_blocked if {
	count(qa.block) == 0 with input as ok
}

test_findings_without_approval_block if {
	qa.block["Findings detected: QA engineer approval required"] with input as object.union(ok, {"findings_count": 2, "human_approved": false})
}

test_findings_with_approval_pass if {
	count(qa.block) == 0 with input as object.union(ok, {"findings_count": 2, "human_approved": true})
}

test_low_coverage_blocks if {
	count(qa.block) == 1 with input as object.union(ok, {"coverage": 70})
}

test_high_sast_blocks if {
	count(qa.block) == 1 with input as object.union(ok, {"sast_high_count": 3})
}

test_escalates_after_24h if {
	qa.escalate with input as {"pending_hours": 30}
}

test_no_escalation_before_24h if {
	not qa.escalate with input as {"pending_hours": 5}
}
