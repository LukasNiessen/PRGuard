# Default PR Quality Audit Policy

Copy this file to a repository root as `.pr-quality-audit.md` and edit it to customize the audit.

The script reads simple Markdown sections. Each bullet under a recognized section becomes a rule. Scalar thresholds use `key: value`.

## Ignored Checks

- sonar
- lint
- eslint
- typescript
- type

## Safe Title Patterns

PRs matching these title fragments are treated as safe-route/documentation/report work. They are omitted unless they still have a relevant failed check.

- develop to main
- docs:
- report
- load test
- loadtest
- performance testing
- dashboard links
- rollback plan docs

## Safe Path Patterns

Paths matching these glob patterns are excluded from effective review size. Raw file/churn counts remain available in JSON and hover details.

- docs/**
- reports/**
- **/playwright-report/**
- **/test-results/**
- **/screenshots/**
- **/*.md
- **/*.mdx
- **/*.rst
- **/*.txt
- **/*.pdf
- **/*.png
- **/*.jpg
- **/*.jpeg
- **/*.gif
- **/*.webp
- **/*.svg
- **/*.csv
- **/*.xlsx
- **/*.pptx
- **/package-lock.json
- **/pnpm-lock.yaml
- **/uv.lock
- **/poetry.lock

## Thresholds

medium_files: 10
medium_churn: 400
large_files: 20
large_churn: 1000
huge_files: 50
huge_churn: 2500
cross_area_min: 3

## Notes For Agents

- Do not treat terse approvals as risky by themselves.
- Do not mention ignored checks in the report.
- Do not mention documentation/report-only PRs unless a relevant failed check remains.
- If a user challenges a result, inspect that exact PR before defending the report.
