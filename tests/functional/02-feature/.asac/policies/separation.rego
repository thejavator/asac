package asac.steps.separation

import rego.v1

# Séparation des rôles : l'agent qui vérifie ne doit pas être celui qui a développé.
# Le harnais rapporte `dev_agent` et `qa_agent` ; avec le harnais fake on les injecte
# via ASAC_FAKE_RESULT. Si les champs sont absents, la règle ne bloque pas.
block contains reason if {
	input.dev_agent == input.qa_agent
	reason := sprintf("separation of duties: agent '%v' cannot both develop and verify", [input.dev_agent])
}
