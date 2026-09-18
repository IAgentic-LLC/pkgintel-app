# pkgintel-app

Full-stack product: the package dependency intelligence assistant, hardened. Continues Book 2's Projects 2 and 3.

Companion product code for *Production AI Products* (Book 3 of the "Production AI Agent Engineering" series). Every chapter has a matching git tag here, real, tested, runnable code, not illustrative snippets.

**Status: Phase 2 scaffold.** Directory structure, dependency manifest, CI, and the five-tier testing taxonomy are wired and passing. Real product logic starts in Phase 4.

## Repository shape

```
backend/src/pkgintel_app/   application code
frontend/                    React frontend
workers/                     Arq background workers
tests/{unit,orchestration,integration,contract,evals}/
config/
docs/diagrams/
scripts/
```

## Testing

Five tiers, same taxonomy as Book 2's `reliable-agents-labs`: `tests/unit`, `tests/orchestration` (scripted fake model), `tests/integration` (real local services), `tests/contract` (real model call), `tests/evals` (golden dataset). Fast tiers run on every push; live tiers run on version tags and manual dispatch only, see `.github/workflows/ci.yml`.
