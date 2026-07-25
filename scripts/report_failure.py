#!/usr/bin/env python3
"""Open/close a tracking issue on the calling repository when a nightly upload fails.

Run by the "Report upload status" step in ``action.yml`` via the action's pixi
Python. Uses ``requests``, which is already part of the pixi environment (a
dependency of ``anaconda-client``), so nothing extra is installed.

Environment:
    GITHUB_TOKEN       token with ``issues: write`` on the target repo
    UPLOAD_OUTCOME     ``failure`` or ``success``
    ISSUE_REPOSITORY   optional ``owner/name`` override for where to open the issue
    GITHUB_REPOSITORY  ``owner/name`` of the repo running the action (fallback target)
    GITHUB_API_URL     API base (set on GitHub Enterprise); optional
    GITHUB_SERVER_URL / GITHUB_RUN_ID  used to link to the failing run
"""

from __future__ import annotations

import os
import sys

import requests

LABEL = "nightly-upload-failure"
TITLE = "Nightly wheel upload is failing"
API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "upload-nightly-action",
        }
    )
    return s


def run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    return (
        f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None
    )


def find_open_issues(s, repo):
    r = s.get(
        f"{API}/repos/{repo}/issues",
        params={"state": "open", "labels": LABEL, "per_page": 100},
    )
    r.raise_for_status()
    # The issues endpoint also returns pull requests; filter them out.
    return [i for i in r.json() if "pull_request" not in i]


def ensure_label(s, repo):
    r = s.post(
        f"{API}/repos/{repo}/labels",
        json={
            "name": LABEL,
            "color": "b60205",
            "description": "Automatically opened when a nightly wheel upload fails.",
        },
    )
    if r.status_code not in (201, 422):  # 422 == label already exists
        r.raise_for_status()


def open_failure_issue(s, repo):
    if find_open_issues(s, repo):
        print("A failure issue is already open; leaving it as-is.")
        return

    lines = [
        "The nightly wheel upload performed by "
        "[`scientific-python/upload-nightly-action`]"
        "(https://github.com/scientific-python/upload-nightly-action) failed.",
        "",
        "No fresh nightly wheels were published for this project. Downstream "
        "projects that test against these nightly wheels may start failing "
        "until the upload succeeds again.",
    ]
    if link := run_url():
        lines += ["", f"Failing workflow run: {link}"]
    lines += [
        "",
        "This issue was opened automatically and will be closed automatically "
        "on the next successful upload.",
    ]

    ensure_label(s, repo)
    r = s.post(
        f"{API}/repos/{repo}/issues",
        json={"title": TITLE, "body": "\n".join(lines), "labels": [LABEL]},
    )
    r.raise_for_status()
    print(f"Opened failure issue #{r.json()['number']} on {repo}.")


def close_failure_issues(s, repo):
    issues = find_open_issues(s, repo)
    if not issues:
        return

    comment = "Nightly wheel upload succeeded again; closing automatically."
    if link := run_url():
        comment += f"\n\nSuccessful run: {link}"

    for issue in issues:
        number = issue["number"]
        s.post(
            f"{API}/repos/{repo}/issues/{number}/comments", json={"body": comment}
        ).raise_for_status()
        s.patch(
            f"{API}/repos/{repo}/issues/{number}",
            json={"state": "closed", "state_reason": "completed"},
        ).raise_for_status()
        print(f"Closed failure issue #{number} on {repo}.")


def main() -> int:
    outcome = os.environ.get("UPLOAD_OUTCOME", "").strip()
    if outcome not in {"failure", "success"}:
        print(f"Unexpected UPLOAD_OUTCOME={outcome!r}; nothing to do.", file=sys.stderr)
        return 0

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("No GITHUB_TOKEN provided; skipping issue reporting.", file=sys.stderr)
        return 0

    repo = (
        os.environ.get("ISSUE_REPOSITORY", "").strip()
        or os.environ.get("GITHUB_REPOSITORY", "").strip()
    )
    if "/" not in repo:
        print("Could not determine target repository; skipping.", file=sys.stderr)
        return 0

    s = session(token)
    try:
        if outcome == "failure":
            open_failure_issue(s, repo)
        else:
            close_failure_issues(s, repo)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            print(
                f"Skipping issue reporting: the token cannot write issues on {repo} "
                f"(HTTP {status}). This is expected on pull requests and forks.",
                file=sys.stderr,
            )
            return 0
        body = exc.response.text if exc.response is not None else ""
        print(f"GitHub API error: {exc}\n{body}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Network error talking to GitHub: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
