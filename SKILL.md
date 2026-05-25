---
name: prguard
description: Audit recent GitHub pull requests for risky review and merge practices. Use when Codex, Cloud Code, Cursor, OpenCode, Hermes, or another coding agent is asked to analyze PR quality, oversized PRs, cross-area changes, risky approvals, failed checks, develop-to-main exclusions, documentation/report exclusions, or generate markdown and HTML timeline reports for coaching or delivery risk.
---

# PRGuard

Use this skill to produce evidence-backed PR quality audits from GitHub metadata.

The goal is targeted coaching, not blame. Report only practices that create real regression risk: large effective code/config/infra changes, broad cross-area changes, relevant failed checks, missing visible approvals, and risky approvals on already-risky PRs.

## Workflow

1. Identify the repository.
   - Prefer the current Git repository remote.
   - If the user gives a repo, pass it explicitly as `--repo OWNER/REPO` or `--repo HOST/OWNER/REPO`.
2. Check prerequisites before fetching data.
   - Run `gh --version`.
   - Run `gh auth status` for the target host.
   - If `gh` is missing or unauthenticated, stop and tell the user how to log in. Do not fabricate PR data.
3. Load customization rules.
   - Look for `.pr-quality-audit.md` in the repository root unless the user gives another config path.
   - If no config exists, use the defaults in `references/default-policy.md`.
4. Run the deterministic report generator:

```bash
python scripts/pr_quality_audit.py --output-dir docs/pr-quality-audit
```

Useful options:

```bash
python scripts/pr_quality_audit.py --repo OWNER/REPO --days 3
python scripts/pr_quality_audit.py --repo HOST/OWNER/REPO --since 2026-05-20 --until 2026-05-22
python scripts/pr_quality_audit.py --config path/to/.pr-quality-audit.md --output-dir docs/audits/pr-quality
python scripts/pr_quality_audit.py --format markdown
python scripts/pr_quality_audit.py --format html
```

5. Review the outputs before answering.
   - Confirm obvious false positives: documentation-only, report-only, screenshots, generated evidence, and lockfile-only changes must not be counted as large/huge.
   - Confirm ignored checks are not mentioned at all.
   - Confirm safe route/develop-to-main PRs are excluded entirely.
   - Spot-check one or two named people when the user challenges a result.
6. Summarize the result with links to generated files and any notable caveats.

## Scoring Rules

Use effective review size, not raw GitHub churn:

- Exclude documentation, reports, screenshots/images, generated evidence, and lockfiles from effective size.
- Do not mention excluded PRs in the report unless they still have a real risk signal after exclusions.
- Ignore lint, ESLint, type/TypeScript, and SonarQube failures entirely by default.
- Do not treat terse approvals such as `LGTM` as risky by themselves.
- Count terse approvals only as context if another actual risk signal already exists and the user explicitly wants review-quality commentary.

Default size thresholds:

- Medium: 10+ effective files or 400+ effective changed lines.
- Large: 20+ effective files or 1000+ effective changed lines.
- Huge: 50+ effective files or 2500+ effective changed lines.

Default risk signals:

- Large or huge effective review size.
- Effective changes spanning three or more meaningful areas.
- Merged with relevant failed checks.
- Merged with no visible approval in GitHub review metadata.
- Approved a PR that already has a real risk signal.

## Outputs

Write generated artifacts under the target repository, usually:

```text
docs/pr-quality-audit/
  pr-quality-audit-YYYY-MM-DD-to-YYYY-MM-DD.md
  pr-quality-timeline-YYYY-MM-DD-to-YYYY-MM-DD.html
  pr-quality-data-YYYY-MM-DD-to-YYYY-MM-DD.json
```

The HTML timeline must be standalone and English by default. Each risky PR is one bar; taller means riskier. Hover text must include PR title, author, score, effective size, raw size, areas, and risk reasons.

## Customization

Use `references/default-policy.md` as the template for `.pr-quality-audit.md`.

Common customizations:

- ignored check names
- safe PR title patterns
- safe path patterns
- area mappings
- size thresholds
- output language
- timeline colors
- report scope and lookback days

Default lookback is 1 day. Pass `--days N`, `--since`, or `--until` only when the user asks for a different window.

When the user provides custom rules, respect them over defaults unless they contradict a direct instruction in the current conversation.

## Failure Handling

If the script cannot fetch PRs:

- State the missing prerequisite clearly.
- For GitHub CLI auth, tell the user to run `gh auth login --hostname HOST`.
- For enterprise hosts, include the detected host.
- Do not produce partial or guessed reports unless the user explicitly asks for a partial report.

If the user challenges a finding:

- Re-fetch or inspect the exact PR.
- Print the PR number, title, effective size, raw size, checks, and risk reasons.
- If the finding is wrong, fix the policy/script and regenerate all affected artifacts from fresh metadata.
