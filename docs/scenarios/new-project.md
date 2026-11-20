# New project from scratch

David, tech lead of a new team, configures ASAC before the first sprint. Stack: Java 21, Maven, Spring Boot. *About 20 minutes.*

```bash
asac init --template java-microservice
```

Detects the stack, CI and issue tracker; generates `asac.yaml`, `asac.vars.yaml.example`, `.asac/policies/default.rego` and the `.gitignore` entry.

Then David fills `asac.vars.yaml` (values and secret references only):

```yaml
gitlab_url: https://gitlab.example.com
gitlab_token: ${vault.gitlab/deploy-token}
llm_model: claude-opus-5-5
dev_harness: claude-code
ba_harness: copilot
qa_harness: claude-code
state_backend: s3://asac-state/payments
```

```bash
asac validate      # syntax, references, capability/skill links, vars, policies, providers
asac plan --pipeline feature --trigger jira:PAY-1001
```

The plan lists each step, agent, mode, required and produced evidence, gates (3 human, 1 quality), estimated tokens and agent time. David approves, commits `asac.yaml`, and the whole team shares the same configuration. Finally `asac portal` gives product owner, QA and manager their entry point.
