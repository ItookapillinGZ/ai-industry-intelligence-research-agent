# AGENTS.md

## Project Goal

This repository is a portfolio-oriented backend/data pipeline project.

The current system collects articles from configurable RSS sources, normalizes and deduplicates them, stores them in SQLite, analyzes them through pluggable analysis providers, and generates Markdown reports.

The project should remain simple, modular, testable, and easy to explain in a technical interview.

Do not introduce architectural complexity unless it solves a concrete requirement.

---

## Core Architecture

Preserve the following high-level dependency direction:

```text
CLI
  ↓
Pipeline / Services
  ↓
Collectors + Analysis Interfaces
  ↓
Repository
  ↓
SQLite
```

Expected module responsibilities:

```text
app/
  cli.py
  config.py
  logging_config.py
  models.py

  collectors/
    base.py
    rss.py

  storage/
    database.py
    article_repository.py

  services/
    normalizer.py
    deduplicator.py
    processor.py
    pipeline.py
    reporter.py

  analysis/
    interfaces.py
    fallback.py
    llm.py
    factory.py
```

Keep responsibilities separated.

Do not move persistence logic into the CLI, collectors, or analysis providers.

Do not put orchestration logic inside repository classes.

---

## Scope Constraints

Unless explicitly requested, do NOT add:

- Web dashboards
- Frontend frameworks
- REST APIs
- FastAPI / Flask / Django
- LangChain
- LangGraph
- Agent frameworks
- Message queues
- Celery
- Redis
- PostgreSQL
- Docker orchestration
- Kubernetes
- Microservices
- Vector databases
- Authentication systems

Prefer the Python standard library where reasonable.

New dependencies must have a clear purpose.

Avoid introducing a dependency for functionality that can be implemented cleanly with a small amount of standard Python.

---

## Storage

SQLite is the persistence layer for the current phase.

Use the standard-library `sqlite3` module unless there is a strong reason to change it.

Database access should go through the repository/storage layer.

Do not silently change the database schema.

If a task requires a schema change:

1. explain why it is needed;
2. keep the change minimal;
3. update initialization/migration logic;
4. update affected tests.

Article identity and deduplication must not depend solely on database auto-increment IDs.

---

## RSS Collection

RSS sources must remain configuration-driven.

Source-specific URLs must not be hardcoded in Python when they belong in:

```text
config/sources.yaml
```

Collectors are responsible only for obtaining and converting external data into internal article representations.

Collectors must not:

- perform LLM analysis;
- write reports;
- contain database business logic;
- decide application-wide orchestration.

A failure from one RSS source should not unnecessarily terminate processing of all other sources.

---

## Normalization and Deduplication

Normalize incoming articles before persistence.

URL normalization should be deterministic.

Deduplication should support at least:

1. normalized URL matching;
2. normalized-title similarity matching where appropriate.

Do not weaken deduplication behavior without explicit justification.

Deduplication logic belongs in the service/domain layer rather than being scattered across collectors and CLI code.

When modifying deduplication logic, add or update tests covering:

- identical URLs;
- normalized equivalent URLs;
- identical titles;
- near-duplicate titles;
- clearly different articles.

---

## Analysis Layer

Analysis capabilities must remain replaceable behind interfaces/protocols.

The intended conceptual interfaces are:

```text
Classifier
Scorer
Summarizer
```

Concrete LLM implementations must not leak provider-specific behavior into pipeline/business logic.

Provider selection should happen through a factory or equivalent composition layer.

The rest of the application should depend on interfaces, not a specific LLM vendor.

---

## LLM Failure Policy

LLM availability must never be required for article collection, normalization, deduplication, or storage.

If:

- no API key is configured;
- the provider is unavailable;
- the request fails;
- the response cannot be parsed;

the application should use the deterministic local fallback where possible.

LLM failures should be logged clearly but should not corrupt stored data or unnecessarily terminate the full pipeline.

Fallback behavior should be deterministic enough to test.

---

## Configuration and Secrets

Configuration that may vary between environments should not be hardcoded.

Secrets must come from environment variables.

Never commit:

- API keys;
- tokens;
- credentials;
- `.env` files containing secrets.

Keep `.env.example` updated when environment variables are added or changed.

Do not place real credentials in tests, documentation, examples, or logs.

---

## CLI

The CLI should remain a thin application entry point.

CLI responsibilities include:

- parsing arguments;
- invoking services/pipeline operations;
- presenting concise results/errors.

The CLI should not contain core business logic.

Prefer commands that can be explained easily, for example:

```bash
python -m app collect
python -m app process
python -m app report
python -m app run
```

Do not rename or significantly change established CLI behavior without checking existing tests and documentation.

---

## Reporting

Reports are generated from persisted data.

The reporting layer should not re-fetch RSS feeds or invoke unrelated collection logic.

Markdown is the default report format for the current phase.

Do not introduce a dashboard or UI merely to display reports unless explicitly requested.

---

## Error Handling

Handle expected external failures explicitly.

Examples include:

- network errors;
- malformed RSS feeds;
- missing configuration;
- missing environment variables;
- LLM provider failures;
- invalid provider responses;
- database errors.

Do not use broad `except Exception` blocks unless they exist at an application boundary and the exception is logged or deliberately converted into a controlled failure.

Do not silently swallow errors.

Errors should contain enough context to diagnose the failing component without exposing secrets.

---

## Logging

Use the project's logging configuration rather than scattered `print()` debugging.

CLI output intended for the user may use normal terminal output.

Internal operational information should use logging.

Never log API keys, secrets, or complete sensitive environment configuration.

---

## Testing Requirements

Changes to business logic should normally include tests.

Prioritize tests for:

- normalization;
- URL handling;
- deduplication;
- repository behavior;
- fallback analysis;
- configuration loading;
- pipeline orchestration;
- failure handling.

Tests should not require live external services unless explicitly marked as integration tests.

Unit tests must not depend on:

- real RSS servers;
- real LLM APIs;
- user-specific environment variables.

Use fixtures/mocks/fakes where appropriate.

Before declaring a task complete, run the relevant test suite.

If the full suite cannot run, state exactly what was and was not verified.

---

## Code Quality

Prefer:

- small focused functions;
- explicit names;
- type hints;
- clear module boundaries;
- deterministic behavior;
- simple dependency flow.

Avoid:

- premature abstraction;
- unnecessary base classes;
- global mutable state;
- hidden side effects;
- circular imports;
- giant service classes;
- provider-specific logic in domain services.

Do not refactor unrelated code while implementing a focused task unless the refactor is necessary.

Keep changes proportional to the requested task.

---

## Compatibility

Use the Python version defined by the repository configuration.

Do not adopt syntax or libraries incompatible with the declared Python version.

When adding a package:

1. verify it is genuinely needed;
2. add it to the project dependency configuration;
3. avoid adding overlapping packages that solve the same problem.

---

## Documentation

Keep documentation aligned with actual behavior.

Update README or relevant documentation when a change affects:

- installation;
- CLI usage;
- configuration;
- architecture;
- environment variables;
- user-visible behavior.

Do not document features that are not implemented.

---

## Git and Change Discipline

Keep each task focused.

Do not modify unrelated files without a clear reason.

Do not delete existing functionality merely because it appears unused without checking references and tests.

Do not rewrite large portions of working code when a localized change is sufficient.

Before making substantial changes, inspect the relevant existing implementation first.

Preserve user changes that are unrelated to the current task.

Never overwrite or revert unrelated modifications made by the user.

---

## Working Procedure

For non-trivial tasks, follow this workflow:

1. Inspect the relevant repository files.
2. Identify existing architecture and constraints.
3. State the intended change briefly.
4. Implement the smallest coherent solution.
5. Add or update tests.
6. Run relevant tests/checks.
7. Review the diff for unintended changes.
8. Summarize:
   - what changed;
   - why;
   - what was tested;
   - any remaining limitations.

Do not spend significant effort designing functionality outside the requested scope.

---

## Decision Principles

When several implementations are possible, prefer the one that is:

1. easier to explain in an interview;
2. easier to test;
3. easier to maintain;
4. less dependent on frameworks;
5. consistent with the existing architecture.

This is a portfolio project, so code clarity and justified engineering decisions are more valuable than maximizing the number of technologies used.

---

## Current Phase Boundary

The current architecture is intentionally a local Python application.

Unless the task explicitly changes the project phase, assume the following remain valid:

```text
RSS
 ↓
Collect
 ↓
Normalize
 ↓
Deduplicate
 ↓
SQLite
 ↓
Analyze
 ↓
Markdown Report
```

Do not independently expand the product scope beyond this pipeline.

Future phases may introduce additional features, but they should be added only when explicitly requested.