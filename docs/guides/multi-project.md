# Serving several projects from one portal

One portal serves one organisation. A project is a repository with its own `asac.yaml`.
Projects are created and managed in the portal's database, by an organisation admin.

```bash
asac portal --data /var/lib/asac-portal
```

`--data` is the portal folder (default `.asac-portal`): sessions, projects, access mappings and
the admin log. It starts empty. Sign in as an organisation admin (the claim `admin`), open
**Administration** and create the first project.

## Registering projects at startup

A shared portal starts empty. Pass each project once, as `ID=PATH`; the flag is repeatable and safe
to repeat, so a restarting pod can keep it in its command line:

```bash
asac portal --data /var/lib/asac-portal \
  --project payments=/project/asac.yaml --project billing=/projects/billing/asac.yaml
```

An id that already exists is left alone (its name, team and access may have been edited in the
portal). `compose.yaml` and `deploy/kubernetes/asac.yaml` do this for the project they mount, and
keep the portal's own data in `/state/portal`, because `/project` is read-only.

## Creating the first project from the command line

```bash
asac project add payments ./asac.yaml --name Payments --team Payments --data /var/lib/asac-portal
asac project list --data /var/lib/asac-portal
asac project archive payments --data /var/lib/asac-portal   # add --restore to bring it back
```

The commands use the same database as the portal. Use them to seed a new portal or from a script.

## Managing projects

| Action | Where | Notes |
|---|---|---|
| Create | Administration, Projects | Identifier, name, absolute path of `asac.yaml` on the portal server, team, repository, groups that can see it |
| Edit | Administration, Projects | Everything but the identifier |
| Archive and restore | Administration, Projects | An archived project disappears for everyone but keeps its state and audit trail |
| Organisation | Administration, Organisation | Name, and the groups that see every project |
| Roles per group | Project, Access | Project owner or organisation admin |

The same actions exist in the API under `/api/v1/admin/projects` and `/api/v1/admin/organization`
(admin role and CSRF header required). Every change is written to the admin log.

## Behaviour

- Web routes live under `/app/p/<project>/` (runs, decisions, audit). `/` lists the projects you can see.
- A project you cannot see answers 404, the same as an unknown one.
- A user's roles in a project are their claim values plus the mappings made in the Access page.
  The engine checks the role again on every decision.
- State is separate per project: a SQLite folder under `ASAC_STATE_DIR`, or a Postgres schema
  `asac_<id>`. The same run id can exist in two projects.

## Pages in each project

| Path | Content |
|---|---|
| `/` | Runs: indicators, your pending decisions, then every run with search, filters, pagination and a step rail |
| `/runs/<id>` | Run detail: pipeline graph, steps, evidence, decisions, events |
| `/gates` | Decision inbox |
| `/config` | The `asac.yaml` in use, read-only (changes go through a merge request) |
| `/audit` | Audit trail, CSV export for auditors and managers |
