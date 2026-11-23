# Contributing

See [`CONTRIBUTING.md`](https://github.com/asac-dev/asac/blob/main/CONTRIBUTING.md) in the repository. Useful contributions today:

- **Language spec**: RFCs for new resource types, composition patterns, gate-model extensions.
- **Skills and modules** for your stack.
- **Providers** for uncovered tools (Linear, Azure DevOps, Bitbucket, ServiceNow…).
- **Harness extensions** for new agent runtimes.
- **Policy library**: reusable Rego (OWASP, sector rules).
- **Reference runtime**: parser, plan/apply engine, state management.

ASAC aims to remain an open standard, like HTTP or OpenAPI, not a platform controlled by one vendor.

## Tests against the real tool

`tests/test_real_claude.py` runs ASAC with the real `claude`, on a small project that is not the
shipped example. It spends money (about 0.12 to 0.30 USD per run, an estimate from the tool) and
uses the network, so it is skipped unless you ask for it:

```bash
ASAC_REAL_CLAUDE=1 uv run pytest tests/test_real_claude.py -m integration -v
# the sandbox test also needs the host of your model API:
ASAC_REAL_CLAUDE=1 ASAC_REAL_CLAUDE_HOST=api.anthropic.com uv run pytest tests/test_real_claude.py -m integration
```

It needs `claude` (logged in), and for the sandbox test `srt` and Node 22.12 or newer. It checks
the disk and the audit, never what the agent says about itself. The sandbox's blocking is proved by
`tests/test_adversarial.py` (tools that really try), not by this file: a real agent declines to
break a rule on its own, so it cannot show the sandbox working.
