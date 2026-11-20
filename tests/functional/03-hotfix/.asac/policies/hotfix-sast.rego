package asac.steps.hotfix_sast

import rego.v1

# Le SAST n'est jamais ignoré, même en hotfix : aucun finding de sévérité haute.
block contains reason if {
	input.sast_high_count > 0
	reason := sprintf("hotfix: %v high-severity SAST findings must be resolved", [input.sast_high_count])
}
