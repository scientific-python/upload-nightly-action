#!/usr/bin/env python3
"""Monitor the scientific-python-nightly-wheels channel and file issues on this repo.

Run by ``.github/workflows/monitor-nightly.yml``. Uses ``PyGithub`` for the
GitHub API and ``requests`` for the anaconda.org API (installed from
``.github/scripts/requirements.txt``).

For every package on the channel, issues are filed on this coordination repo:
  * > 30 days without an upload -> open a "stale" issue (auto-closed on recovery)
  * > 60 days without an upload -> additionally open a "purge candidate" issue.

Optionally, if PRODUCER_GITHUB_TOKEN (a PAT) is set and the wheel appears in the
hand-maintained mapping ``packages-source-repos.yaml`` (wheel-name -> owner/repo):
  * > 15 days without an upload -> open a tracking issue on the wheel's own source
    repo, escalated with a comment at the 30- and 60-day marks and auto-closed on
    recovery.
If that PAT is missing, expired, or unauthorized, a "nightly-pat-invalid" issue is
opened on this repo instead (and auto-closed once the token works again).

Never deletes anything (that is remove-wheels.yml's job). Packages listed in
``packages-ignore-from-cleanup.txt`` are intentionally exempt and are skipped.

Environment:
    GITHUB_TOKEN          token with ``issues: write`` on this repo
    GITHUB_REPOSITORY     ``owner/name`` of this repo
    GITHUB_WORKSPACE      checkout root (holds the mapping + ignore list)
    GITHUB_API_URL        API base (set on GitHub Enterprise); optional
    GITHUB_STEP_SUMMARY   optional path to append the freshness table to
    PRODUCER_GITHUB_TOKEN optional PAT with ``issues: write`` on the source repos,
                          enabling notifications on each wheel's own repository
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import requests
import yaml
from github import Auth, Github, GithubException, UnknownObjectException

ANACONDA_ORG = "scientific-python-nightly-wheels"
NOTIFY_DAYS = 15
STALE_DAYS = 30
PURGE_DAYS = 60
STALE_LABEL = "stale-nightly"
PURGE_LABEL = "nightly-purge-candidate"
PRODUCER_LABEL = "nightly-upload-stalled"
PAT_INVALID_LABEL = "nightly-pat-invalid"
ANACONDA_API = "https://api.anaconda.org"


def marker(name, kind) -> str:
    return f"<!-- nightly-monitor:{name}:{kind} -->"


def load_ignore_list():
    """Reuse the same exemption list that remove-wheels.yml honors."""
    ignore = set()
    path = (
        Path(os.environ.get("GITHUB_WORKSPACE", "."))
        / "packages-ignore-from-cleanup.txt"
    )
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name and not name.startswith("#"):
                ignore.add(name)
        print(f"Ignoring {len(ignore)} exempt package(s): {', '.join(sorted(ignore))}")
    except OSError as exc:
        print(
            f"Could not read {path}: {exc}; proceeding without an ignore list.",
            file=sys.stderr,
        )
    return ignore


def latest_upload_age(name):
    """Return (age_in_days, YYYY-MM-DD) for the most recent file, or None."""
    detail = requests.get(
        f"{ANACONDA_API}/package/{ANACONDA_ORG}/{name}", timeout=30
    ).json()
    times = []
    for f in detail.get("files", []):
        raw = (f.get("upload_time") or "").strip()
        try:
            times.append(dt.datetime.fromisoformat(raw))
        except ValueError:
            continue
    if not times:
        return None
    latest = max(times)
    age_days = (dt.datetime.now(dt.timezone.utc) - latest).days
    return age_days, latest.date().isoformat()


def ensure_label(repo, name, color, description):
    try:
        return repo.get_label(name)
    except UnknownObjectException:
        return repo.create_label(name=name, color=color, description=description)


def open_issues(repo, label):
    return [
        i
        for i in repo.get_issues(state="open", labels=[label])
        if i.pull_request is None
    ]


def ensure_open(issues, repo, label, name, kind, title, body):
    m = marker(name, kind)
    if any(m in (i.body or "") for i in issues):
        print(f"Issue already open for {name} ({kind}).")
        return
    created = repo.create_issue(title=title, body=f"{m}\n\n{body}", labels=[label])
    print(f"Opened {kind} issue #{created.number} for {name}.")


def close_if_open(issues, name, kind, comment):
    m = marker(name, kind)
    for issue in (i for i in issues if m in (i.body or "")):
        issue.create_comment(comment)
        issue.edit(state="closed", state_reason="completed")
        print(f"Closed {kind} issue #{issue.number} for {name}.")


def load_source_repos():
    """Hand-maintained wheel-name -> owner/repo mapping (packages-source-repos.yaml).

    Each ``packages`` entry may be a bare ``owner/repo`` string or a mapping with a
    ``repo`` key (leaving room for per-repo config such as labels/assignees later).
    """
    mapping = {}
    path = Path(os.environ.get("GITHUB_WORKSPACE", ".")) / "packages-source-repos.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        print(
            f"Could not read {path}: {exc}; no producer notifications.", file=sys.stderr
        )
        return mapping
    except yaml.YAMLError as exc:
        print(
            f"Could not parse {path}: {exc}; no producer notifications.",
            file=sys.stderr,
        )
        return mapping

    for name, entry in (data.get("packages") or {}).items():
        repo = entry.get("repo") if isinstance(entry, dict) else entry
        if isinstance(repo, str) and "/" in repo:
            mapping[name] = repo
    print(f"Loaded {len(mapping)} wheel->repo mapping(s).")
    return mapping


def add_comment_once(issue, mark, body):
    """Add a comment, unless one carrying ``mark`` already exists (idempotent)."""
    if any(mark in (c.body or "") for c in issue.get_comments()):
        return
    issue.create_comment(f"{mark}\n\n{body}")


def check_producer_token(self_repo, producer_gh):
    """Validate the PAT; if it is invalid/expired, open an issue on this repo.

    Returns the client if the token authenticates (and closes any previously
    opened "PAT invalid" issue), or None if producer notifications should be
    skipped this run.
    """
    label = ensure_label(
        self_repo,
        PAT_INVALID_LABEL,
        "b60205",
        "The PAT used to notify producing repos is missing, expired, or unauthorized.",
    )
    issues = open_issues(self_repo, label)
    try:
        login = producer_gh.get_user().login
    except GithubException as exc:
        title = (
            "Cross-repo notification token (NIGHTLY_UPLOAD_ISSUE_PAT) is not working"
        )
        body = "\n".join(
            [
                "The nightly channel monitor is configured to notify producing "
                "repositories when their nightly wheels stop uploading, but the "
                "Personal Access Token it uses could not authenticate:",
                "",
                f"```\n{exc.status}: {exc.data}\n```",
                "",
                "Producer-repo notifications are skipped until this is fixed. Please "
                "renew or rotate the `NIGHTLY_UPLOAD_ISSUE_PAT` secret with a token "
                "that has `issues: write` on the target repositories.",
                "",
                "This issue will be closed automatically once the token works again.",
            ]
        )
        ensure_open(issues, self_repo, label, "config", "pat-invalid", title, body)
        return None
    except Exception as exc:  # noqa: BLE001 - transient error: skip, but do not file
        print(
            f"Could not validate producer PAT ({exc}); skipping producer notifications this run.",
            file=sys.stderr,
        )
        return None
    print(f"Producer PAT authenticated as {login}.")
    close_if_open(
        issues,
        "config",
        "pat-invalid",
        "The cross-repo notification token is working again; closing automatically.",
    )
    return producer_gh


def handle_producer(producer_gh, cache, repo_full, name, age_days, last_upload):
    """Open/escalate/close a tracking issue on the wheel's own source repository."""
    if repo_full not in cache:
        prepo = producer_gh.get_repo(repo_full)
        label = ensure_label(
            prepo,
            PRODUCER_LABEL,
            "b60205",
            "Nightly wheels have stopped being uploaded to the scientific-python nightly channel.",
        )
        cache[repo_full] = (prepo, label, open_issues(prepo, label))
    prepo, label, issues = cache[repo_full]

    m = marker(name, "producer")
    existing = next((i for i in issues if m in (i.body or "")), None)

    # Recovered: close the producer issue if one is open.
    if age_days <= NOTIFY_DAYS:
        if existing is not None:
            existing.create_comment(
                f"`{name}` is being uploaded to the nightly channel again "
                f"({last_upload}); closing automatically."
            )
            existing.edit(state="closed", state_reason="completed")
            print(
                f"Closed producer issue #{existing.number} on {repo_full} for {name}."
            )
        return

    # Open the tracking issue at the 15-day mark.
    if existing is None:
        body = "\n".join(
            [
                f"The nightly wheels for `{name}` have not been uploaded to the "
                f"[scientific-python nightly channel](https://anaconda.org/{ANACONDA_ORG}/{name}) "
                f"in **{age_days} days** (last upload: {last_upload}).",
                "",
                "This usually means the nightly build/upload job in this repository has "
                "started failing. Please check your CI and restore the nightly upload.",
                "",
                "Escalation policy on the nightly channel:",
                f"- after {STALE_DAYS} days a tracking issue is opened on "
                "`scientific-python/upload-nightly-action`;",
                f"- after {PURGE_DAYS} days the package may be purged from the channel.",
                "",
                "This issue was opened automatically and will be closed automatically "
                "once fresh nightly wheels are uploaded again.",
            ]
        )
        existing = prepo.create_issue(
            title=f"Nightly wheels for `{name}` have not been uploaded in {age_days}+ days",
            body=f"{m}\n\n{body}",
            labels=[label],
        )
        print(f"Opened producer issue #{existing.number} on {repo_full} for {name}.")

    # Escalate (one comment each) as later thresholds are crossed.
    if age_days > STALE_DAYS:
        add_comment_once(
            existing,
            marker(name, "producer-30"),
            f"Still no nightly upload after {STALE_DAYS}+ days (last upload: {last_upload}). "
            "A tracking issue has been opened on `scientific-python/upload-nightly-action`.",
        )
    if age_days > PURGE_DAYS:
        add_comment_once(
            existing,
            marker(name, "producer-60"),
            f"Still no nightly upload after {PURGE_DAYS}+ days (last upload: {last_upload}). "
            "This package may be purged from the nightly channel until uploads resume.",
        )


def write_summary(rows):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"## Nightly channel freshness ({ANACONDA_ORG})",
        "",
        "| Package | Age (days) | Last upload |",
        "| --- | ---: | --- |",
        *[f"| {name} | {age} | {last} |" for name, age, last in rows],
    ]
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo_name = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or "/" not in repo_name:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY are required.", file=sys.stderr)
        return 1

    gh = Github(
        auth=Auth.Token(token),
        base_url=os.environ.get("GITHUB_API_URL", Github.DEFAULT_BASE_URL),
    )
    repo = gh.get_repo(repo_name)
    ignore = load_ignore_list()

    # Optional: notify each wheel's own source repo, using a PAT that has
    # issues: write on those repos and a hand-maintained wheel -> repo mapping.
    producer_token = os.environ.get("PRODUCER_GITHUB_TOKEN", "").strip()
    producer_gh = Github(auth=Auth.Token(producer_token)) if producer_token else None
    if producer_gh:
        producer_gh = check_producer_token(repo, producer_gh)
    source_repos = load_source_repos() if producer_gh else {}
    producer_cache = {}
    if not producer_token:
        print("PRODUCER_GITHUB_TOKEN not set; skipping producer-repo notifications.")
    elif producer_gh and not source_repos:
        print("Mapping is empty; no producer-repo notifications will be sent.")

    stale_label = ensure_label(
        repo,
        STALE_LABEL,
        "fbca04",
        "A nightly package has not received an upload in over 30 days.",
    )
    purge_label = ensure_label(
        repo,
        PURGE_LABEL,
        "d93f0b",
        "A nightly package has not received an upload in over 60 days.",
    )

    packages = requests.get(
        f"{ANACONDA_API}/packages/{ANACONDA_ORG}", timeout=30
    ).json()
    print(f"Found {len(packages)} packages in {ANACONDA_ORG}.")

    stale_open = open_issues(repo, stale_label)
    purge_open = open_issues(repo, purge_label)
    summary = []

    for pkg in packages:
        name = pkg["name"]
        if name in ignore:
            print(f"Skipping exempt package {name}.")
            continue

        try:
            result = latest_upload_age(name)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"Could not fetch details for {name}: {exc}", file=sys.stderr)
            continue
        if result is None:
            print(f"No dated files for {name}; skipping.", file=sys.stderr)
            continue

        age_days, last_upload = result
        summary.append((name, age_days, last_upload))

        index_hint = (
            f"python -m pip install {name} --pre --upgrade "
            f"--index-url https://pypi.anaconda.org/{ANACONDA_ORG}/simple "
            f"--extra-index-url https://pypi.org/simple"
        )

        # --- 30 day stale issue ---------------------------------------------
        if age_days > STALE_DAYS:
            body = "\n".join(
                [
                    f"The package `{name}` has not received a nightly wheel upload in "
                    f"**{age_days} days** (last upload: {last_upload}).",
                    "",
                    "The producing project's nightly build is most likely failing. "
                    "Please check its CI and restore the nightly upload.",
                    "",
                    f"Latest files: https://anaconda.org/{ANACONDA_ORG}/{name}/files",
                    "",
                    "This issue was opened automatically and will be closed "
                    "automatically once a fresh upload lands.",
                ]
            )
            ensure_open(
                stale_open,
                repo,
                stale_label,
                name,
                "stale",
                f"`{name}`: no nightly upload in over {STALE_DAYS} days",
                body,
            )
        else:
            close_if_open(
                stale_open,
                name,
                "stale",
                f"`{name}` received a fresh nightly upload ({last_upload}); closing automatically.",
            )

        # --- 60 day purge issue ---------------------------------------------
        if age_days > PURGE_DAYS:
            body = "\n".join(
                [
                    f"The package `{name}` has not received a nightly wheel upload in "
                    f"**{age_days} days** (last upload: {last_upload}), which is beyond "
                    f"the {PURGE_DAYS}-day threshold.",
                    "",
                    "Maintainers: please decide whether to **purge this package from "
                    "the nightly channel** until its build is fixed. Long-stale wheels "
                    'are no longer "nightly" and can silently mask upstream breakage '
                    "for downstream users who install with:",
                    "",
                    "```",
                    index_hint,
                    "```",
                    "",
                    "If this package is intentionally kept despite being stale, add it "
                    "to `packages-ignore-from-cleanup.txt` to silence this monitor.",
                    "",
                    "If the nightly build is restored, this issue will be closed "
                    "automatically.",
                ]
            )
            ensure_open(
                purge_open,
                repo,
                purge_label,
                name,
                "purge",
                f"`{name}`: consider purging from the nightly channel ({age_days} days stale)",
                body,
            )
        else:
            close_if_open(
                purge_open,
                name,
                "purge",
                f"`{name}` received a fresh nightly upload ({last_upload}); closing automatically.",
            )

        # --- producer repo notification (opt-in, needs PAT + mapping) --------
        if producer_gh and name in source_repos:
            try:
                handle_producer(
                    producer_gh,
                    producer_cache,
                    source_repos[name],
                    name,
                    age_days,
                    last_upload,
                )
            except Exception as exc:  # noqa: BLE001 - one bad repo must not abort the run
                print(
                    f"Producer notification for {name} ({source_repos[name]}) failed: {exc}",
                    file=sys.stderr,
                )

    summary.sort(key=lambda row: row[1], reverse=True)
    write_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
