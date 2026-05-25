# PR Review Skill for Claude Code and Codex: PRGuard

<div align="center" name="top">

[![Claude Skill](https://img.shields.io/badge/Claude-Skill-6272F5)](https://docs.claude.ai/docs/agent-skills)
[![Codex Skill](https://img.shields.io/badge/Codex-Skill-10A37F)](https://developers.openai.com/codex/skills/)
[![GitHub CLI](https://img.shields.io/badge/GitHub%20CLI-required-181717)](https://cli.github.com/)

</div>

### Finds Review Risk.

PRGuard audits recent GitHub pull requests for review and merge patterns that increase regression risk: oversized effective changes, cross-area blast radius, relevant failed checks, missing visible approvals, and risky approvals on already-risky PRs.

It is designed for late-stage delivery pressure where vague reminders like "review better" are not enough. PRGuard produces evidence-backed coaching reports with links, contributor summaries, and timeline visualizations.

### Avoids Noisy False Positives.

PRGuard does not count raw churn blindly. Documentation, reports, screenshots, generated evidence, and lockfiles are excluded from effective review size. Lint, type, TypeScript, ESLint, and SonarQube failures are ignored by default when teams have explicitly decided to tolerate them.

Tiny focused PRs are not flagged just because an approval says `LGTM`.

### Built For Agent Workflows.

The skill keeps the agent workflow compact and delegates deterministic work to `scripts/pr_quality_audit.py`: GitHub data fetching, scoring, JSON export, Markdown report generation, and standalone HTML timeline generation.

---

[Quick Start](#-quick-start) • [Why PRGuard](#-why-prguard) • [Token Strategy](#-token-strategy) • [What's Included](#-whats-included) • [Repository Layout](#-repository-layout) • [How It Works](#-how-it-works) • [Scope](#-scope)

---

## ⚡ 2 min Quickstart

### Option 1: Install As A Skill

**Windows (PowerShell):**

```powershell
git clone <your-prguard-repo-url> "$env:USERPROFILE\.agents\skills\prguard"
```

Or copy the folder directly:

```powershell
Copy-Item -Recurse C:\Users\78079\Repos\Private\PRGuard "$env:USERPROFILE\.agents\skills\prguard"
```

Start a new Codex chat if the slash menu does not refresh immediately.

### Option 2: Use By Path

You can use PRGuard without installing it globally:

```text
Use the PRGuard skill at C:\Users\78079\Repos\Private\PRGuard to audit this repo.
```

### Option 3: Run The Script Directly

From a Git repository with an authenticated GitHub CLI:

```bash
python C:/Users/78079/Repos/Private/PRGuard/scripts/pr_quality_audit.py
```

Default lookback is **1 day**.

When PRGuard is invoked with no text, flags, or arguments, agents should run the default audit immediately and print the resolved defaults first:

```text
Using PRGuard defaults: repository=current Git remote, lookback=1 day, output=docs/pr-quality-audit, format=all, config=.pr-quality-audit.md if present.
```

Useful variants:

```bash
python scripts/pr_quality_audit.py --days 3
python scripts/pr_quality_audit.py --repo github.example.com/Org/Repo --days 7
python scripts/pr_quality_audit.py --since 2026-05-20 --until 2026-05-22
python scripts/pr_quality_audit.py --config .pr-quality-audit.md --output-dir docs/pr-quality-audit
```

### Prerequisites

PRGuard needs:

- Python 3.10+
- GitHub CLI (`gh`)
- `gh auth login` completed for the target host
- repository access to the PRs being audited

If `gh` is missing or unauthenticated, PRGuard stops and prints the login step instead of guessing.

## 🏁 Why PRGuard

### Overview

| Dimension | **PRGuard** | Manual PR Review Audit | No Audit |
| --- | --- | --- | --- |
| **Evidence-backed reports** | Yes | Sometimes | No |
| **Per-person coaching summary** | Yes | Manual | No |
| **HTML risk timeline** | Yes | No | No |
| **GitHub links included** | Yes | Manual | No |
| **Effective size scoring** | Yes | Rarely | No |
| **Docs/report false-positive filtering** | Yes | Inconsistent | No |
| **Ignored checks policy** | Yes | Inconsistent | No |
| **Enterprise GitHub support** | Yes | Manual | No |
| **Custom policy file** | Yes | No | No |
| **Repeatable output** | Yes | No | No |

### PRGuard vs Manual Audit

Manual audits drift quickly. One reviewer counts generated files, another ignores them. One person treats SonarQube as blocking, another knows the team deliberately ignored it for a deadline. PRGuard centralizes those rules in `.pr-quality-audit.md` and applies them consistently.

The key difference is the **effective review size** model. PRGuard keeps raw size visible for transparency, but scores only meaningful code/config/infra review surface. That prevents load-test reports, screenshots, docs, and lockfile churn from dominating the coaching signal.

PRGuard also separates actual risk from review style. A tiny focused PR with `LGTM` is not risky. A huge cross-area PR approved with no meaningful validation context is risky because the underlying PR is risky.

---

## 🕵️ Token Strategy

- Keep `SKILL.md` procedural and compact.
- Put deterministic work in `scripts/pr_quality_audit.py`.
- Keep policy details in `references/default-policy.md`.
- Keep the HTML shell in `assets/timeline-template.html`.
- Load only the policy or script when the user asks for customization or debugging.

## 🧩 What's Included

- A focused `SKILL.md` workflow for agents.
- A deterministic Python audit script using only the standard library.
- GitHub CLI prerequisite and authentication checks.
- Markdown report generation.
- Standalone HTML timeline generation.
- JSON data export for follow-up analysis.
- Default policy reference for repository-local customization.
- Safe-route handling for develop-to-main and documentation/report work.
- Ignored-check handling for lint/type/SonarQube-style failures.

## 🔲 Repository Layout

| File | Description |
| --- | --- |
| `SKILL.md` | Operational workflow for agent use |
| `scripts/pr_quality_audit.py` | Fetches GitHub PR metadata, scores risk, writes Markdown/HTML/JSON |
| `references/default-policy.md` | Template for repository-local `.pr-quality-audit.md` customization |
| `assets/timeline-template.html` | Standalone HTML timeline shell used by the script |
| `agents/openai.yaml` | UI metadata for skill discovery |
| `.gitignore` | Local Python/output ignores |

## 🔎 How It Works

PRGuard runs a repeatable audit workflow:

1. **Resolve repository** - Use `--repo` or detect `origin`.
2. **Check prerequisites** - Verify Python, `gh`, and GitHub authentication.
3. **Load policy** - Use `.pr-quality-audit.md` or built-in defaults.
4. **Fetch PR metadata** - Pull PRs, files, reviews, checks, and merge state.
5. **Compute effective review size** - Exclude safe documentation/report/generated paths.
6. **Score actual risk** - Size, cross-area span, relevant failed checks, missing visible approval.
7. **Generate artifacts** - Markdown audit, HTML timeline, JSON source data.
8. **Sanity-check findings** - Agents should inspect challenged PRs before defending a result.

## 🐲 Scope

PRGuard is for GitHub pull request process risk. It does not replace:

- code review
- local application testing
- security review
- CI configuration hardening
- team delivery policy decisions

It is a coaching and visibility tool: it tells you where review process risk is concentrated so humans can course-correct faster.
