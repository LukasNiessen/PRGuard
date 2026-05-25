#!/usr/bin/env python3
"""Generate PR quality audit markdown, HTML timeline, and JSON data.

Requires Python 3.10+ and GitHub CLI (`gh`) authenticated for the target host.
Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import fnmatch
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any


DEFAULT_IGNORED_CHECKS = ["sonar", "lint", "eslint", "typescript", "type"]
DEFAULT_SAFE_TITLE_PATTERNS = [
    "develop to main",
    "docs:",
    "report",
    "load test",
    "loadtest",
    "performance testing",
    "dashboard links",
    "rollback plan docs",
]
DEFAULT_SAFE_PATH_PATTERNS = [
    "docs/**",
    "reports/**",
    "**/playwright-report/**",
    "**/test-results/**",
    "**/screenshots/**",
    "**/*.md",
    "**/*.mdx",
    "**/*.rst",
    "**/*.txt",
    "**/*.pdf",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.svg",
    "**/*.csv",
    "**/*.xlsx",
    "**/*.pptx",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
    "**/uv.lock",
    "**/poetry.lock",
]
DEFAULT_AREAS = {
    "frontend": ["frontend/**"],
    "backend": ["backend/**"],
    "aiworker": ["backend/packages/aiworker/**"],
    "eval": ["eval/**"],
    "infra/manifests": ["manifests/**"],
    "ci": [".github/**"],
    "scripts/devtools": ["scripts/**", "dev", "docker-compose*"],
}


@dataclass
class Policy:
    ignored_checks: list[str] = field(default_factory=lambda: DEFAULT_IGNORED_CHECKS.copy())
    safe_title_patterns: list[str] = field(default_factory=lambda: DEFAULT_SAFE_TITLE_PATTERNS.copy())
    safe_path_patterns: list[str] = field(default_factory=lambda: DEFAULT_SAFE_PATH_PATTERNS.copy())
    medium_files: int = 10
    medium_churn: int = 400
    large_files: int = 20
    large_churn: int = 1000
    huge_files: int = 50
    huge_churn: int = 2500
    cross_area_min: int = 3
    areas: dict[str, list[str]] = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_AREAS)))
    colors: dict[str, str] = field(
        default_factory=lambda: {
            "low": "#2f8f6b",
            "medium": "#c89424",
            "high": "#c45138",
            "critical": "#8f2f46",
        }
    )


def info(message: str) -> None:
    print(f"[INFO] {message}")


def fail(message: str, code: int = 2) -> None:
    print(f"[INFO] {message}", file=sys.stderr)
    raise SystemExit(code)


def run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout


def run_json(args: list[str], cwd: Path | None = None) -> Any:
    return json.loads(run(args, cwd=cwd))


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    if "T" not in value:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def in_window(pr: dict[str, Any], since: datetime, until: datetime) -> bool:
    return any(
        dt and since <= dt <= until
        for dt in [parse_date(pr.get(k)) for k in ("createdAt", "updatedAt", "closedAt", "mergedAt")]
    )


def detect_repo(cwd: Path) -> tuple[str, str | None]:
    explicit = os.environ.get("GH_REPO")
    if explicit:
        return normalize_repo(explicit)
    try:
        remote = run(["git", "remote", "get-url", "origin"], cwd=cwd).strip()
    except Exception:
        fail("Could not detect repository. Pass --repo OWNER/REPO or HOST/OWNER/REPO.")
    if remote.startswith("git@"):
        host, path = remote[4:].split(":", 1)
        owner_repo = path.removesuffix(".git")
        return owner_repo, host
    match = re.search(r"https?://([^/]+)/(.+?)(?:\.git)?$", remote)
    if match:
        return match.group(2), match.group(1)
    fail(f"Could not parse git remote: {remote}")


def normalize_repo(repo: str) -> tuple[str, str | None]:
    repo = repo.strip().removesuffix(".git")
    if repo.startswith("http://") or repo.startswith("https://"):
        match = re.search(r"https?://([^/]+)/(.+)$", repo)
        if not match:
            fail(f"Could not parse --repo value: {repo}")
        return match.group(2), match.group(1)
    parts = repo.split("/")
    if len(parts) >= 3 and "." in parts[0]:
        return "/".join(parts[1:]), parts[0]
    return repo, None


def check_prereqs(host: str | None) -> None:
    if not command_exists("gh"):
        fail("GitHub CLI is not installed. Install it, then authenticate with `gh auth login`.")
    try:
        version = run(["gh", "--version"]).splitlines()[0]
        info(version)
    except Exception as exc:
        fail(f"GitHub CLI exists but could not run: {exc}")
    auth_cmd = ["gh", "auth", "status"]
    if host:
        auth_cmd += ["--hostname", host]
    try:
        run(auth_cmd)
    except Exception:
        suffix = f" --hostname {host}" if host else ""
        fail(f"GitHub CLI is not authenticated. Run `gh auth login{suffix}` and retry.")


def extract_section_items(text: str, heading: str) -> list[str]:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return []
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    block = text[start : start + next_heading.start()] if next_heading else text[start:]
    items = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def extract_scalar(text: str, key: str) -> int | None:
    match = re.search(rf"^{re.escape(key)}\s*:\s*(\d+)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return int(match.group(1)) if match else None


def load_policy(config_path: Path | None) -> Policy:
    policy = Policy()
    if not config_path or not config_path.exists():
        return policy
    text = config_path.read_text(encoding="utf-8")
    policy.ignored_checks += extract_section_items(text, "Ignored Checks")
    policy.safe_title_patterns += extract_section_items(text, "Safe Title Patterns")
    policy.safe_path_patterns += extract_section_items(text, "Safe Path Patterns")
    for attr, key_name in [
        ("medium_files", "medium_files"),
        ("medium_churn", "medium_churn"),
        ("large_files", "large_files"),
        ("large_churn", "large_churn"),
        ("huge_files", "huge_files"),
        ("huge_churn", "huge_churn"),
        ("cross_area_min", "cross_area_min"),
    ]:
        value = extract_scalar(text, key_name)
        if value is not None:
            setattr(policy, attr, value)
    return policy


def matches_any(value: str, patterns: list[str]) -> bool:
    lowered = value.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) or pattern.lower() in lowered for pattern in patterns)


def path_matches_any(path: str, patterns: list[str]) -> bool:
    lowered = path.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


def area_for_path(path: str, policy: Policy) -> str:
    lowered = path.lower()
    for area, patterns in policy.areas.items():
        if path_matches_any(lowered, patterns):
            return area
    return "root/other"


def ignored_check(check: dict[str, Any], policy: Policy) -> bool:
    text = f"{check.get('workflowName') or ''} {check.get('name') or ''}".lower()
    return any(term.lower() in text for term in policy.ignored_checks)


def check_name(check: dict[str, Any]) -> str:
    return check.get("workflowName") or check.get("name") or "Check"


def classify_pr(pr: dict[str, Any], policy: Policy) -> dict[str, Any]:
    files = pr.get("files") or []
    title_safe = matches_any(pr.get("title") or "", policy.safe_title_patterns)
    effective = [] if title_safe else [f for f in files if not path_matches_any(f["path"], policy.safe_path_patterns)]
    checks = pr.get("statusCheckRollup") or []
    failed = [
        c
        for c in checks
        if (c.get("conclusion") or "").upper()
        in {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
        and not ignored_check(c, policy)
    ]
    reviews = pr.get("reviews") or []
    approvals = [r for r in reviews if r.get("state") == "APPROVED"]
    changes_requested = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
    raw_files = pr.get("changedFiles") or len(files)
    raw_churn = (pr.get("additions") or 0) + (pr.get("deletions") or 0)
    eff_files = len(effective)
    eff_churn = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in effective)
    eff_areas = sorted({area_for_path(f["path"], policy) for f in effective})
    safe_only = raw_files > 0 and eff_files == 0
    size = "small"
    if not safe_only:
        if eff_files >= policy.huge_files or eff_churn >= policy.huge_churn:
            size = "huge"
        elif eff_files >= policy.large_files or eff_churn >= policy.large_churn:
            size = "large"
        elif eff_files >= policy.medium_files or eff_churn >= policy.medium_churn:
            size = "medium"
    reasons = []
    score = 1
    if size == "large":
        score += 4
        reasons.append(f"large effective review size ({eff_files} files, {eff_churn} changed lines)")
    elif size == "huge":
        score += 7
        reasons.append(f"huge effective review size ({eff_files} files, {eff_churn} changed lines)")
    if len(eff_areas) >= policy.cross_area_min:
        score += 4
        reasons.append(f"cross-area effective span ({', '.join(eff_areas)})")
    if pr.get("mergedAt") and failed:
        score += 5
        reasons.append(f"merged with relevant failed checks ({len(failed)})")
    elif failed:
        score += 2
        reasons.append(f"relevant failed checks present ({len(failed)})")
    if not safe_only and pr.get("mergedAt") and not approvals:
        score += 3
        reasons.append("merged with no approval visible in PR review metadata")
    if not safe_only and pr.get("mergedAt") and changes_requested:
        score += 2
        reasons.append("had changes-requested review before merge")
    risky = bool(reasons) and not (safe_only and not failed)
    return {
        "raw_files": raw_files,
        "raw_churn": raw_churn,
        "effective_files": eff_files,
        "effective_churn": eff_churn,
        "effective_areas": eff_areas,
        "failed_checks": failed,
        "approvals": approvals,
        "size": size,
        "score": min(score, 20),
        "reasons": reasons,
        "risky": risky,
        "safe_only": safe_only,
    }


def fetch_prs(repo: str, host: str | None, since: datetime, until: datetime, policy: Policy) -> list[dict[str, Any]]:
    repo_arg = f"{host}/{repo}" if host else repo
    basic = run_json(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo_arg,
            "--state",
            "all",
            "--limit",
            "300",
            "--json",
            "number,title,author,createdAt,updatedAt,closedAt,mergedAt,url,state,isDraft,baseRefName,headRefName,labels",
        ]
    )
    selected = [pr for pr in basic if not matches_any(pr.get("title") or "", ["develop to main"]) and in_window(pr, since, until)]
    fields = ",".join(
        [
            "number",
            "title",
            "author",
            "createdAt",
            "updatedAt",
            "closedAt",
            "mergedAt",
            "url",
            "state",
            "baseRefName",
            "headRefName",
            "additions",
            "deletions",
            "changedFiles",
            "files",
            "reviews",
            "mergedBy",
            "statusCheckRollup",
            "reviewDecision",
        ]
    )
    detailed = []
    for index, pr in enumerate(sorted(selected, key=lambda p: p["number"], reverse=True), 1):
        info(f"Fetching PR {index}/{len(selected)}: #{pr['number']}")
        detail = run_json(["gh", "pr", "view", str(pr["number"]), "--repo", repo_arg, "--json", fields])
        detail["audit"] = classify_pr(detail, policy)
        detailed.append(detail)
    return detailed


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_None._\n"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("\n", " ") for c in row) + " |")
    return "\n".join(out) + "\n"


def link_pr(pr: dict[str, Any]) -> str:
    return f"[#{pr['number']}]({pr['url']})"


def check_summary(checks: list[dict[str, Any]], policy: Policy) -> str:
    relevant = [c for c in checks if not ignored_check(c, policy)]
    if not relevant:
        return "no relevant checks"
    counts = Counter((c.get("conclusion") or c.get("status") or "UNKNOWN").upper() for c in relevant)
    return ", ".join(f"{k.lower()} {v}" for k, v in sorted(counts.items()))


def build_people(prs_all: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    people: dict[str, Any] = defaultdict(lambda: {"authored": [], "reviewed": [], "approvals": [], "risky_approvals": []})
    names: dict[str, str] = {}
    for pr in prs_all:
        author = (pr.get("author") or {}).get("login") or "unknown"
        if pr.get("author", {}).get("name"):
            names[author] = pr["author"]["name"]
        if pr["audit"]["risky"]:
            people[author]["authored"].append(pr)
        for review in pr.get("reviews") or []:
            reviewer = (review.get("author") or {}).get("login") or "unknown"
            people[reviewer]["reviewed"].append({"pr": pr, "review": review})
            if review.get("state") == "APPROVED":
                people[reviewer]["approvals"].append({"pr": pr, "review": review})
                if pr.get("mergedAt") and pr["audit"]["risky"] and (
                    pr["audit"]["failed_checks"]
                    or pr["audit"]["size"] in {"large", "huge"}
                    or len(pr["audit"]["effective_areas"]) >= 3
                ):
                    people[reviewer]["risky_approvals"].append({"pr": pr, "review": review})
    return people, names


def render_markdown(prs_all: list[dict[str, Any]], repo: str, since: datetime, until: datetime, policy: Policy) -> str:
    prs = [pr for pr in prs_all if pr["audit"]["risky"]]
    people, names = build_people(prs_all)
    merged = [pr for pr in prs if pr.get("mergedAt")]
    sizes = Counter(pr["audit"]["size"] for pr in prs)
    failed_merged = [pr for pr in merged if pr["audit"]["failed_checks"]]
    no_approval = [pr for pr in merged if not pr["audit"]["approvals"]]
    lines = [
        f"# PR Quality Audit: {since:%Y-%m-%d} to {until:%Y-%m-%d}\n",
        f"Repository: `{repo}`  \nGenerated from GitHub metadata on {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}.  \nWindow: {since:%Y-%m-%d %H:%M UTC} to {until:%Y-%m-%d %H:%M UTC}.  \nOnly risky PRs are included. Safe-route PRs and ignored checks are omitted from counts and tables.\n",
        "## Table of contents\n",
    ]
    sections = [
        "Executive summary",
        "Targeted coaching candidates",
        "Contributor summary",
        "Merged PRs with relevant failed checks",
        "Merged PRs with no visible approval",
        "Risk definitions used",
        "Highest-risk PRs",
        "Detailed per-person breakdown",
        "Risky PR inventory",
    ]
    lines.extend(f"- [{section}](#{re.sub(r'[^a-z0-9 -]', '', section.lower()).replace(' ', '-')})" for section in sections)
    lines.append("\n## Executive summary\n")
    lines.append(
        md_table(
            ["Metric", "Value"],
            [
                ["Risky PRs included in report", len(prs)],
                ["Risky merged PRs", len(merged)],
                ["Small risky PRs", sizes["small"]],
                ["Medium risky PRs", sizes["medium"]],
                ["Large risky PRs", sizes["large"]],
                ["Huge risky PRs", sizes["huge"]],
                ["Risky cross-area PRs", len([p for p in prs if len(p["audit"]["effective_areas"]) >= policy.cross_area_min])],
                ["Merged with relevant failed checks", len(failed_merged)],
                ["Merged with no approval visible", len(no_approval)],
                ["Median effective files", median([p["audit"]["effective_files"] for p in prs]) if prs else 0],
                ["Median effective churn", median([p["audit"]["effective_churn"] for p in prs]) if prs else 0],
            ],
        )
    )
    person_rows = []
    coaching_rows = []
    for login, stats in sorted(
        people.items(),
        key=lambda item: (len(item[1]["authored"]) * 2 + len(item[1]["risky_approvals"]), len(item[1]["authored"])),
        reverse=True,
    ):
        if not stats["authored"] and not stats["risky_approvals"]:
            continue
        huge = [pr for pr in stats["authored"] if pr["audit"]["size"] == "huge"]
        large = [pr for pr in stats["authored"] if pr["audit"]["size"] == "large"]
        cross = [pr for pr in stats["authored"] if len(pr["audit"]["effective_areas"]) >= policy.cross_area_min]
        failed = [pr for pr in stats["authored"] if pr.get("mergedAt") and pr["audit"]["failed_checks"]]
        score = len(stats["authored"]) * 2 + len(stats["risky_approvals"])
        display = f"{names[login]} (@{login})" if login in names else f"@{login}"
        signals = []
        if huge:
            signals.append(f"{len(huge)} huge authored PRs")
        if large:
            signals.append(f"{len(large)} large authored PRs")
        if cross:
            signals.append(f"{len(cross)} cross-area authored PRs")
        if failed:
            signals.append(f"{len(failed)} authored PRs merged with relevant failed checks")
        if stats["risky_approvals"]:
            signals.append(f"{len(stats['risky_approvals'])} risky approvals")
        coaching_rows.append([display, score, len(stats["authored"]), len(stats["risky_approvals"]), "; ".join(signals)])
        person_rows.append([display, len(stats["authored"]), f"{len(huge)}/{len(large)}", len(cross), len(failed), len(stats["risky_approvals"])])
    lines.append("## Targeted coaching candidates\n")
    lines.append(md_table(["Contributor", "Risk score", "Risky authored PRs", "Risky approvals", "Main coaching signals"], coaching_rows))
    lines.append("## Contributor summary\n")
    lines.append(md_table(["Contributor", "Risky authored", "Huge/Large authored", "Cross-area authored", "Authored merged w/ relevant failed checks", "Risky approvals"], person_rows))
    lines.append("## Merged PRs with relevant failed checks\n")
    lines.append(
        md_table(
            ["PR", "Author", "Merged by", "Approvers", "Failed checks"],
            [
                [
                    f"{link_pr(pr)} {pr['title']}",
                    person_label(pr.get("author")),
                    person_label(pr.get("mergedBy")),
                    ", ".join(sorted({person_label(r.get("author")) for r in pr["audit"]["approvals"]})) or "none",
                    "; ".join(check_name(c) for c in pr["audit"]["failed_checks"]),
                ]
                for pr in failed_merged
            ],
        )
    )
    lines.append("## Merged PRs with no visible approval\n")
    lines.append(
        md_table(
            ["PR", "Author", "Merged by", "Relevant checks", "Review decision"],
            [
                [
                    f"{link_pr(pr)} {pr['title']}",
                    person_label(pr.get("author")),
                    person_label(pr.get("mergedBy")),
                    check_summary(pr.get("statusCheckRollup") or [], policy),
                    pr.get("reviewDecision") or "",
                ]
                for pr in no_approval
            ],
        )
    )
    lines.append("## Risk definitions used\n")
    lines.append(
        f"- Medium: {policy.medium_files}+ effective files or {policy.medium_churn}+ effective changed lines.\n"
        f"- Large: {policy.large_files}+ effective files or {policy.large_churn}+ effective changed lines.\n"
        f"- Huge: {policy.huge_files}+ effective files or {policy.huge_churn}+ effective changed lines.\n"
        "- Effective size excludes safe-route paths, documentation, reports, screenshots/images, generated evidence, and lockfiles.\n"
        "- Ignored checks are fully omitted from risk scoring and reporting.\n"
        "- Terse approvals are not risky by themselves.\n"
    )
    highest = sorted(prs, key=lambda p: p["audit"]["score"], reverse=True)[:30]
    lines.append("## Highest-risk PRs\n")
    lines.append(
        md_table(
            ["PR", "Author", "State", "Score", "Effective files/churn", "Raw files/churn", "Effective areas", "Risk signals"],
            [
                [
                    f"{link_pr(pr)} {pr['title']}",
                    person_label(pr.get("author")),
                    pr["state"],
                    pr["audit"]["score"],
                    f"{pr['audit']['effective_files']}/{pr['audit']['effective_churn']}",
                    f"{pr['audit']['raw_files']}/{pr['audit']['raw_churn']}",
                    ", ".join(pr["audit"]["effective_areas"]) or "none",
                    "; ".join(pr["audit"]["reasons"]),
                ]
                for pr in highest
            ],
        )
    )
    lines.append("## Detailed per-person breakdown\n")
    for login, stats in sorted(people.items(), key=lambda item: (len(item[1]["authored"]), len(item[1]["risky_approvals"])), reverse=True):
        if not stats["authored"] and not stats["risky_approvals"]:
            continue
        display = f"{names[login]} (@{login})" if login in names else f"@{login}"
        lines.append(f"### {display}\n")
        lines.append(md_table(["Metric", "Value"], [["Risky authored PRs", len(stats["authored"])], ["Risky approvals", len(stats["risky_approvals"])]]))
        lines.append("Flagged authored PRs:\n")
        lines.append(
            md_table(
                ["PR", "State", "Score", "Effective files/churn", "Raw files/churn", "Signals"],
                [
                    [
                        f"{link_pr(pr)} {pr['title']}",
                        pr["state"],
                        pr["audit"]["score"],
                        f"{pr['audit']['effective_files']}/{pr['audit']['effective_churn']}",
                        f"{pr['audit']['raw_files']}/{pr['audit']['raw_churn']}",
                        "; ".join(pr["audit"]["reasons"]),
                    ]
                    for pr in stats["authored"]
                ],
            )
        )
    lines.append("## Risky PR inventory\n")
    lines.append(
        md_table(
            ["PR", "Author", "Created", "Merged", "State", "Size", "Score", "Effective files/churn", "Raw files/churn", "Effective areas", "Relevant checks"],
            [
                [
                    f"{link_pr(pr)} {pr['title']}",
                    person_label(pr.get("author")),
                    pr.get("createdAt"),
                    pr.get("mergedAt") or "",
                    pr["state"],
                    pr["audit"]["size"],
                    pr["audit"]["score"],
                    f"{pr['audit']['effective_files']}/{pr['audit']['effective_churn']}",
                    f"{pr['audit']['raw_files']}/{pr['audit']['raw_churn']}",
                    ", ".join(pr["audit"]["effective_areas"]) or "none",
                    check_summary(pr.get("statusCheckRollup") or [], policy),
                ]
                for pr in sorted(prs, key=lambda p: p["number"], reverse=True)
            ],
        )
    )
    return "\n".join(lines)


def person_label(user: dict[str, Any] | None) -> str:
    if not user:
        return "unknown"
    login = user.get("login") or "unknown"
    return f"{user.get('name')} (@{login})" if user.get("name") else f"@{login}"


def render_html(prs_all: list[dict[str, Any]], repo: str, since: datetime, until: datetime, policy: Policy) -> str:
    prs = [pr for pr in prs_all if pr["audit"]["risky"]]
    data = json.dumps(
        [
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": person_label(pr.get("author")),
                "url": pr["url"],
                "createdAt": pr["createdAt"],
                "state": pr["state"],
                "score": pr["audit"]["score"],
                "size": pr["audit"]["size"],
                "effectiveFiles": pr["audit"]["effective_files"],
                "effectiveChurn": pr["audit"]["effective_churn"],
                "rawFiles": pr["audit"]["raw_files"],
                "rawChurn": pr["audit"]["raw_churn"],
                "areas": pr["audit"]["effective_areas"],
                "violations": pr["audit"]["reasons"],
            }
            for pr in sorted(prs, key=lambda p: p["number"])
        ],
        ensure_ascii=False,
    )
    template_path = Path(__file__).resolve().parents[1] / "assets" / "timeline-template.html"
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("{{TITLE}}", html.escape(f"PR Quality Timeline: {since:%Y-%m-%d} to {until:%Y-%m-%d}"))
        .replace("{{REPO}}", html.escape(repo))
        .replace("{{SINCE}}", since.isoformat().replace("+00:00", "Z"))
        .replace("{{UNTIL}}", until.isoformat().replace("+00:00", "Z"))
        .replace("{{GENERATED_AT}}", f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
        .replace("{{PR_DATA}}", data)
        .replace("{{LOW_COLOR}}", policy.colors["low"])
        .replace("{{MEDIUM_COLOR}}", policy.colors["medium"])
        .replace("{{HIGH_COLOR}}", policy.colors["high"])
        .replace("{{CRITICAL_COLOR}}", policy.colors["critical"])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/REPO, HOST/OWNER/REPO, or full GitHub URL")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--since", help="YYYY-MM-DD or ISO datetime")
    parser.add_argument("--until", help="YYYY-MM-DD or ISO datetime")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/pr-quality-audit"))
    parser.add_argument("--format", choices=["all", "markdown", "html", "json"], default="all")
    args = parser.parse_args()

    cwd = Path.cwd()
    repo, host = normalize_repo(args.repo) if args.repo else detect_repo(cwd)
    check_prereqs(host)
    config = args.config or cwd / ".pr-quality-audit.md"
    policy = load_policy(config if config.exists() else None)
    until = parse_date(args.until) or datetime.now(timezone.utc)
    since = parse_date(args.since) or (until - timedelta(days=args.days))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prs = fetch_prs(repo, host, since, until, policy)
    suffix = f"{since:%Y-%m-%d}-to-{until:%Y-%m-%d}"
    if args.format in {"all", "json"}:
        (args.output_dir / f"pr-quality-data-{suffix}.json").write_text(json.dumps(prs, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.format in {"all", "markdown"}:
        (args.output_dir / f"pr-quality-audit-{suffix}.md").write_text(render_markdown(prs, repo, since, until, policy), encoding="utf-8")
    if args.format in {"all", "html"}:
        (args.output_dir / f"pr-quality-timeline-{suffix}.html").write_text(render_html(prs, repo, since, until, policy), encoding="utf-8")
    info(f"Wrote outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
