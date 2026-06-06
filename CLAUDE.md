# SemaFlow

## What this project is
A governed analytics agent. Multi-agent system with a semantic layer that translates business questions into trusted SQL or document retrieval. Built on real Olist e-commerce data (Brazilian, messy, real joins).

## Stack
- Python 3.14, Docker, Postgres + pgvector
- Gemini 2.0 Flash (text-to-SQL workhorse, via google-generativeai SDK)
- Claude (reviewer + synthesizer, later stages)
- LangGraph (orchestration, stage 5)
- LangSmith (tracing), Streamlit (dashboard)
- Pydantic for all data models
- sqlglot for SQL parsing in guardrails
- PyYAML for semantic layer config

## Project structure
- `/semaflow/app/semantic/` - semantic_layer.yaml and golden_set.yaml (the governed config)
- `/semaflow/app/sql/` - text-to-SQL pipeline: models, prompts, node, resolver, guardrails, executor
- `/semaflow/app/llm/` - LLM client wrappers (future)
- `/semaflow/data/` - raw Olist CSVs
- `/semaflow/evals/` - golden set evaluation scripts (stage 6)
- `/semaflow/.env` - DATABASE_URL, GEMINI_API_KEY (load with python-dotenv)

## Environment
- WSL Ubuntu on Windows. Docker Desktop with WSL integration.
- Postgres runs in Docker (container: semaflow_db, image: pgvector/pgvector:pg16)
- Venv: /semaflow/.venv/ — activate with: source /semaflow/.venv/bin/activate
- Python binary: /semaflow/.venv/bin/python3

### Database commands
Start:   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c "cd /semaflow && docker compose up -d"
Stop:    MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c "cd /semaflow && docker compose down"
Status:  MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- docker ps
Connect: MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- psql postgresql://semaflow:semaflow_local_pw@localhost:5432/semaflow

## Writing files (WSL — CRITICAL)
All project files are owned by root in WSL. The Write and Edit tools fail with EPERM. Always use this bash pattern:

    MSYS_NO_PATHCONV=1 wsl -d Ubuntu -u root -- tee /semaflow/path/to/file << 'PYEOF'
    ...file content...
    PYEOF

Rules:
- MSYS_NO_PATHCONV=1 prevents Git Bash from translating /semaflow/... to a Windows path
- -u root is required; default WSL user (ryuk) cannot write root-owned files
- Single-quoted delimiter (e.g. 'PYEOF') prevents shell expansion of $ and backticks
- Use tee, not bash -c "cat > ...": tee does not try to parse the content
- Choose a delimiter that does NOT appear as a standalone line in the file content

## Architecture rules
- The LLM (Gemini) NEVER writes SQL. It selects from declared measures and extracts parameters. The resolver assembles SQL from YAML templates deterministically. This is the trust boundary.
- Guardrails validate SQL BEFORE execution: read-only, schema, join safety, row limit. Uses sqlglot for parsing.
- The semantic layer (YAML) is the single source of truth for measures, joins, glossary, and terms. Code reasons against the config, not the raw database schema.
- Scope discipline: only define semantic layer entries when a golden-set question needs them. Do not model every column.
- All relative time terms resolve against dataset_reference_date (2018-10-17), not CURRENT_DATE.

## Code style
- Type hints on all functions
- Pydantic models for all data contracts between pipeline stages
- Logging via stdlib logging, not print statements
- Load .env with python-dotenv at entry points
- Use async where the pipeline supports it (node.py is async)
- Tests go in app/sql/tests/ using pytest

## What NOT to do
- Do not use the Write or Edit tools — use the bash tee pattern above.
- Do not wire up LangGraph until stage 5. Current work is stage 3 (text-to-SQL + guardrails).
- Do not add measures or glossary entries to semantic_layer.yaml unless a golden-set question requires them.
- Do not hardcode database credentials. Always read from environment variables.
- Do not use f-strings for SQL template substitution (injection risk). Use the resolver's safe substitution.

## Current build state
- Stage 1 (data model): COMPLETE. Star schema, 9 tables loaded.
- Stage 2 (semantic layer): COMPLETE. YAML config validated.
- Stage 3 (text-to-SQL + guardrails): IN PROGRESS.
  - DONE: models.py, prompts.py, node.py, resolver.py
  - TODO: guardrails.py (stub), executor.py (missing), tests (none yet)
