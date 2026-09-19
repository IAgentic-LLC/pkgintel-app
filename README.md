# pkgintel-app

Full-stack product: the package dependency intelligence assistant, hardened. Continues Book 2's Projects 2 and 3.

Companion product code for *Production AI Products* (Book 3 of the "Production AI Agent Engineering" series). Every chapter has a matching git tag here, real, tested, runnable code, not illustrative snippets.

**Status: all 36 chapters complete**, book-wide (this product's own tags: `ch11-end` through `ch33-end`). Multi-tenant retrieval over a real Qdrant vector store (ch11), a scheduled ingestion pipeline (ch12) and a real Airflow DAG once it outgrew one function (ch13), a served API and React frontend behind real Auth0 Organizations (ch14), measured caching and cost (ch15), shared Langfuse tracing (ch16), zero-downtime migrations (ch17), a tiered CI/CD pipeline (ch31), and a real blast-radius bug found and fixed in the ingestion schedule (ch33). 33 tests passing across all five tiers where applicable. Real, disclosed gap: Auth0 Organizations excludes machine-to-machine credentials entirely, so tenant identity can only be proven through a real interactive user login, never queried unattended.

## Repository shape

```
backend/src/pkgintel_app/   application code
frontend/                    React frontend
workers/                     SAQ background workers
tests/{unit,orchestration,integration,contract,evals}/
config/
docs/diagrams/
scripts/
```

## Testing

Five tiers, same taxonomy as Book 2's `reliable-agents-labs`: `tests/unit`, `tests/orchestration` (scripted fake model), `tests/integration` (real local services), `tests/contract` (real model call), `tests/evals` (golden dataset). Fast tiers run on every push; live tiers run on version tags and manual dispatch only, see `.github/workflows/ci.yml`.
