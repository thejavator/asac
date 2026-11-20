# Glossary

| Term | Definition |
|---|---|
| **Agent** | AI actor: skill + provider + harness + tools |
| **Assist / delegate** | Step modes: runs on the persona's machine / runs headless on a runner |
| **Autonomy** | How much freedom an agent has: `readonly`, `review`, `autonomous` |
| **Capability** | WHAT a step must achieve, vendor-agnostic |
| **Daemon** | Server component receiving events and dispatching steps |
| **Evidence** | Named, immutable proof that a step was done |
| **Gate** | Control point: human, quality or automated |
| **Golden Path** | Recommended project template (planned) |
| **Harness** | Agentic runtime executing the loop |
| **Harness engineering** | Discipline of designing everything around a model |
| **Manifest** | `asac.yaml`, layer 1 |
| **MCP** | Model Context Protocol, used to connect tools |
| **OKF** | File-based knowledge format used by the `okf` knowledge provider |
| **Plan / apply** | Preview then execute |
| **Provider** | Integration to an LLM or external system |
| **Registry** | Catalogue of versioned skills, modules, harnesses |
| **Runner** | Server-side pool executing `delegate` steps |
| **Skill** | HOW: portable, versioned procedure |
| **State** | Persistent record of runs and evidence |
