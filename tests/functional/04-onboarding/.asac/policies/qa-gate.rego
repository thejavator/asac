package asac.gates.qa

import rego.v1

# Block when findings exist and no human approved them.
block contains reason if {
	input.findings_count > 0
	not input.human_approved
	reason := "Findings detected: QA engineer approval required"
}

# Block when coverage is below the configured minimum.
block contains reason if {
	input.coverage < input.skill_params.coverage_min
	reason := sprintf("Coverage %v%% below minimum %v%%", [input.coverage, input.skill_params.coverage_min])
}

# Block when a high-severity SAST finding exists.
block contains reason if {
	input.sast_high_count > 0
	reason := sprintf("%v high-severity SAST findings must be resolved", [input.sast_high_count])
}

# Escalate when the gate has been pending for more than 24 hours.
escalate if input.pending_hours > 24
