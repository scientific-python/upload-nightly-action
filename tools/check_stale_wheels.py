#!/usr/bin/env python
"""Report projects whose nightly wheels are about to be removed from the channel.

Wheels older than the retention period are deleted by ``remove-wheels.yml``, which
can leave a project with no nightly wheels at all and break downstream CI. This
script runs on a schedule from this repository, finds packages whose most recent
upload is older than the warning threshold, and opens an issue on the project's
own tracker so the maintainers hear about it before the wheels disappear.

Requires ``ISSUE_OPENER_TOKEN`` (a classic token with the ``public_repo`` scope,
used to open issues on other projects) and ``GITHUB_TOKEN`` (used only to report
here when a project's tracker can't be reached).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from github import Auth, Github, GithubException

ANACONDA_USER = "scientific-python-nightly-wheels"
ANACONDA_API = "https://api.anaconda.org"
CHANNEL_URL = f"https://anaconda.org/{ANACONDA_USER}"
ACTION_URL = "https://github.com/scientific-python/upload-nightly-action"
BOT_URL = "https://github.com/scientific-python-bot"
POLICY_URL = f"{ACTION_URL}#artifact-cleanup-policy-at-the-scientific-python-nightly-wheels-channel"

# Hidden markers let us find our own issues and comments again without relying on
# the (fuzzy, eventually consistent) search API. Changing one silently orphans every
# issue already carrying it, so treat them as permanent.
MARKER = "<!-- scientific-python-nightly-wheels: stale-wheels -->"
FINAL_WARNING_MARKER = "<!-- scientific-python-nightly-wheels: stale-wheels-final -->"
REPORT_MARKER = "<!-- scientific-python-nightly-wheels: stale-wheels-report -->"

# Open an issue once wheels are this old, follow up once at FINAL_WARNING_DAYS, and
# keep RETENTION_DAYS in step with remove-wheels.yml, which does the deleting.
WARN_DAYS = 15
FINAL_WARNING_DAYS = 25
RETENTION_DAYS = 30

# Don't nag again about a package whose issue was closed without a new upload
# until this much time has passed.
RENOTIFY_DAYS = 60

# Packages whose GitHub repository can't be discovered from their PyPI metadata.
# Prefer fixing Project-URL metadata upstream over adding entries here.
PYPI_MAP = {
    "icechunk": "earth-mover/icechunk",
}

SCRIPT = Path(__file__).name
IGNORE_FILE = Path(__file__).resolve().parent.parent / "packages-ignore-from-cleanup.txt"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "scientific-python-upload-nightly-action"

# What this run did, surfaced as an annotation on the job page at the end so the
# issues are one click away rather than buried in the summary table.
NOTICES = []

# Ambient run configuration, set once by main().
GH: Github = None
LOGIN = ""
DRY_RUN = False

_GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?!orgs/)([^/]+)/([^/#?]+)", re.IGNORECASE
)
# Substrings of the Project-URL keys that name a project's own repository, best
# first. Matching on substrings covers "Bug Tracker", "issue-tracker", and friends;
# keys naming something else ("Changelog", "Discussions", "upstream") are ignored.
_REPO_URL_KEYS = ("tracker", "issues", "source", "repository", "homepage", "home")
# Everything we treat as "this package could not be checked" rather than a crash.
REPORTABLE = (GithubException, RuntimeError, requests.RequestException)


def fetch(url):
    """Read JSON from a public API (anaconda.org, PyPI), or None if missing."""
    response = SESSION.get(url, timeout=60)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


@dataclass
class Package:
    name: str
    last_upload: datetime | None = None
    repo: object = None  # github.Repository, once resolved
    status: str = ""
    issue_url: str | None = None
    error: str | None = None

    def age_days(self, now):
        return (now - self.last_upload).days


def list_packages():
    """Return every package currently on the channel."""
    return [package["name"] for package in fetch(f"{ANACONDA_API}/packages/{ANACONDA_USER}")]


def last_upload_time(name):
    """Return the newest upload time across every version of ``name``.

    ``latest_version`` is not reliable here: nightly version strings are not
    ordered consistently across projects, so an older release can sort last.
    """
    package = fetch(f"{ANACONDA_API}/package/{ANACONDA_USER}/{name}")
    if package is None:
        return None
    uploads = []
    for version in package["versions"]:
        quoted = urllib.parse.quote(version, safe="")
        release = fetch(f"{ANACONDA_API}/release/{ANACONDA_USER}/{name}/{quoted}")
        for distribution in (release or {}).get("distributions", []):
            uploads.append(datetime.fromisoformat(distribution["upload_time"]))
    if not uploads:
        return None
    return max(uploads).astimezone(timezone.utc)


def read_ignored(path):
    """Read the package names that are exempt from automated cleanup."""
    names = set()
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line)
    return names


def pypi_project_urls(name):
    """Return a package's PyPI Project-URLs, keyed as the project wrote them."""
    info = fetch(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if info is None:
        return {}
    urls = dict(info["info"].get("project_urls") or {})
    if info["info"].get("home_page"):
        urls.setdefault("home", info["info"]["home_page"])
    return urls


def repo_from_pypi(name):
    """Find the ``owner/repo`` a package's PyPI metadata points at."""
    candidates = []
    for key, url in pypi_project_urls(name).items():
        match = _GITHUB_REPO_RE.match(str(url))
        if not match:
            continue
        key = key.strip().lower()
        priority = next((i for i, want in enumerate(_REPO_URL_KEYS) if want in key), None)
        if priority is None:
            continue
        owner, repo = match.groups()
        candidates.append((priority, owner + "/" + repo.removesuffix(".git")))
    if not candidates:
        return None
    return min(candidates)[1]


def target_repo(name):
    """Return the repository to report to, following renames."""
    full_name = PYPI_MAP.get(name) or repo_from_pypi(name)
    if full_name is None:
        raise RuntimeError(
            f"no GitHub repository found in the Project-URL metadata at "
            f"https://pypi.org/project/{name}/ — add a tracker, source, repository, or "
            f"homepage URL there, or add an entry to PYPI_MAP in {SCRIPT}"
        )
    repo = GH.get_repo(full_name)
    if repo.archived:
        raise RuntimeError(f"repository {repo.full_name} is archived")
    if not repo.has_issues:
        raise RuntimeError(f"repository {repo.full_name} has issues disabled")
    return repo


def resolve(name):
    """Look up when a package was last uploaded and where to report about it."""
    package = Package(name=name)
    try:
        package.last_upload = last_upload_time(name)
        if package.last_upload is None:
            raise RuntimeError("no wheels found on the channel")
        package.repo = target_repo(name)
    except REPORTABLE as exc:
        package.status = "error"
        package.error = f"`{name}`: {exc}"
    return package


def bot_issues(repo):
    """Return this bot's issues on ``repo`` that carry our marker, newest first.

    Deliberately unbounded in time: an issue we opened months ago and never
    commented on again is exactly the one we must find, both to close it when
    wheels reappear and to avoid opening a duplicate beside it. The list stays
    short in practice, since a well-behaved run opens at most one per repository.
    """
    issues = repo.get_issues(state="all", creator=LOGIN, sort="created", direction="desc")
    return [
        issue for issue in issues if issue.pull_request is None and MARKER in (issue.body or "")
    ]


def describe(packages):
    names = [f"`{package.name}`" for package in packages]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def issue_title(stale, age):
    names = ", ".join(package.name for package in stale)
    return f"No {names} nightly wheels uploaded in {age} days"


def issue_body(stale, age, removal_date):
    uploads = "\n".join(f"- `{package.name}`: {package.last_upload:%Y-%m-%d}" for package in stale)
    return f"""\
{MARKER}
The most recent {describe(stale)} nightly wheels on the \
[`{ANACONDA_USER}`]({CHANNEL_URL}) channel were uploaded **{age} days ago**:

{uploads}

The *Updated* date shown on anaconda.org can be newer than these: it tracks any change to the \
package, including our own removal of versions that have expired.

Wheels are [removed after {RETENTION_DAYS} days]({POLICY_URL}), so unless a new nightly is \
uploaded before **{removal_date:%Y-%m-%d}** there will be no wheels left on the channel at all, \
and downstream projects that test against nightlies will fail to install them.

Some things worth checking:

- Is the workflow that builds and uploads the nightly wheels failing?
- Was its scheduled run \
[disabled by GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-a-workflow) \
after a period of repository inactivity?
- Has there simply been nothing to build? Consider uploading on a fixed cadence even when \
nothing has changed, to keep the channel populated for downstream users.

*🤖 Opened automatically by [scientific-python-bot]({BOT_URL}) from \
[scientific-python/upload-nightly-action]({ACTION_URL}), and closed again on its own once a new \
wheel is uploaded.*
"""


def action(done, would):
    """Word a summary status as an action taken, or one --dry-run only considered."""
    return would if DRY_RUN else done


def create_issue(repo, title, body):
    if DRY_RUN:
        print(f"  [dry run] would open an issue on {repo.full_name}: {title}")
        return None
    return repo.create_issue(title=title, body=body).html_url


def comment(issue, body):
    if DRY_RUN:
        print(f"  [dry run] would comment on {issue.html_url}")
        return
    issue.create_comment(body)


def close_issue(issue, body):
    comment(issue, body)
    if DRY_RUN:
        print(f"  [dry run] would close {issue.html_url}")
        return
    issue.edit(state="closed", state_reason="completed")


def handle_fresh(packages, issues):
    """Close any issue we opened now that new wheels have shown up."""
    for package in packages:
        package.status = "ok"
    open_issues = [issue for issue in issues if issue.state == "open"]
    if not open_issues:
        return
    newest = max(package.last_upload for package in packages)
    for issue in open_issues:
        for package in packages:
            package.status = action("resolved", "would close")
            package.issue_url = issue.html_url
        NOTICES.append(
            f"{action('Closed', 'Would close')} for {describe(packages)}: {issue.html_url}"
        )
        close_issue(
            issue, f"New nightly wheels were uploaded on {newest:%Y-%m-%d}. Thanks! Closing."
        )


def handle_stale(repo, stale, issues, now):
    age = max(package.age_days(now) for package in stale)
    oldest = min(package.last_upload for package in stale)
    removal_date = oldest + timedelta(days=RETENTION_DAYS)
    open_issues = [issue for issue in issues if issue.state == "open"]

    def mark(status, url):
        for package in stale:
            package.status = status
            package.issue_url = url

    if not open_issues:
        recent = [issue for issue in issues if (now - issue.created_at).days < RENOTIFY_DAYS]
        if recent:
            # An issue we opened was closed without new wheels appearing; give the
            # project some quiet before raising it again.
            mark("muted", recent[0].html_url)
            return
        url = create_issue(
            repo,
            issue_title(stale, age),
            issue_body(stale, age, removal_date),
        )
        mark(action("opened", "would open"), url)
        NOTICES.append(
            f"{action('Opened', 'Would open')} for {describe(stale)}: "
            f"{url or repo.html_url + '/issues'}"
        )
        return

    issue = open_issues[0]
    mark("reported", issue.html_url)
    if age < FINAL_WARNING_DAYS:
        return
    if any(FINAL_WARNING_MARKER in (item.body or "") for item in issue.get_comments()):
        return
    mark(action("final warning", "would comment"), issue.html_url)
    NOTICES.append(
        f"{action('Commented', 'Would comment')} on {describe(stale)} at {age} days: "
        f"{issue.html_url}"
    )
    comment(
        issue,
        f"{FINAL_WARNING_MARKER}\nStill no new nightly wheels for {describe(stale)}. The "
        f"remaining wheels are scheduled to be removed from the channel on "
        f"**{removal_date:%Y-%m-%d}**.",
    )


def handle_repo(repo, packages, now):
    """Open, update, or close one issue for every package built from ``repo``."""
    stale = [package for package in packages if package.age_days(now) >= WARN_DAYS]
    try:
        issues = bot_issues(repo)
        if stale:
            handle_stale(repo, stale, issues, now)
            for package in packages:
                if package not in stale:
                    package.status = "ok"
        else:
            handle_fresh(packages, issues)
    except REPORTABLE as exc:
        for package in packages:
            package.status = "error"
            package.error = f"`{package.name}` ({repo.full_name}): {exc}"


def write_summary(packages, now):
    lines = [
        f"## Nightly wheel freshness ({now:%Y-%m-%d}){' — dry run' if DRY_RUN else ''}",
        "",
        "| Package | Last upload | Age (days) | Repository | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    for package in sorted(packages, key=lambda p: p.last_upload or epoch):
        age = "?" if package.last_upload is None else package.age_days(now)
        upload = "?" if package.last_upload is None else f"{package.last_upload:%Y-%m-%d}"
        name = package.repo.full_name if package.repo else None
        repo = f"[{name}](https://github.com/{name})" if name else "—"
        status = package.status
        if package.issue_url:
            status = f"[{status}]({package.issue_url})"
        if package.error:
            # Keep the table readable; the full text, including how to fix it, goes
            # in the issue report_errors opens.
            status = f"error: {package.error.split(': ', 1)[-1].split(' — ')[0]}"
        elif age != "?" and age >= WARN_DAYS:
            age = f"**{age}**"
        lines.append(f"| {package.name} | {upload} | {age} | {repo} | {status} |")
    summary = "\n".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fid:
            fid.write(summary + "\n")


def annotate(lines):
    """Surface what the run did as an annotation on the GitHub Actions job page."""
    if not lines:
        return
    body = "\n".join(lines)
    if os.environ.get("GITHUB_ACTIONS"):
        # Workflow commands are one line, so the newlines have to be encoded
        body = body.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=Stale wheel check::{body}")
    else:
        print(f"\n{body}")


def report_errors(errors):
    """Open (or update) an issue here about projects we could not reach.

    This uses GITHUB_TOKEN rather than the bot's token: the thing that failed may
    well be the bot's token itself.
    """
    run_id = os.environ.get("GITHUB_RUN_ID")
    check = "stale wheel check"
    if run_id:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        check = f"[{check}]({server}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id})"
    body = (
        f"{REPORT_MARKER}\nThese packages are on the "
        f"[`{ANACONDA_USER}`]({CHANNEL_URL}) channel, but the "
        f"{check} could not work out where to report about them, so "
        f"nobody will hear from us when their wheels are about to be removed:\n\n"
        + "\n".join(f"- {error}" for error in errors)
        + "\n\nThis list is rewritten on every run, and the issue can be closed once it is empty."
    )
    if DRY_RUN:
        print(f"\n[dry run] could not report on {len(errors)} project(s):\n{body}")
        return
    home = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"])).get_repo(
        os.environ.get("GITHUB_REPOSITORY", "scientific-python/upload-nightly-action")
    )
    existing = [
        issue
        for issue in home.get_issues(state="open")
        if issue.pull_request is None and REPORT_MARKER in (issue.body or "")
    ]
    if not existing:
        create_issue(home, "Could not report stale nightly wheels", body)
    elif existing[0].body != body:
        # Rewrite rather than comment: this runs daily, and an unfixed package would
        # otherwise collect a comment a day. Editing notifies nobody.
        existing[0].edit(body=body)


def main(argv=None):
    global GH, LOGIN, DRY_RUN

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without opening, commenting on, or closing issues",
    )
    args = parser.parse_args(argv)

    DRY_RUN = args.dry_run
    for name in ("ISSUE_OPENER_TOKEN", "GITHUB_TOKEN"):
        if not os.environ.get(name):
            parser.error(f"{name} is not set")

    GH = Github(auth=Auth.Token(os.environ["ISSUE_OPENER_TOKEN"]))
    # An unusable token (usually expired) fails the run, which the workflow turns
    # into an issue; report_errors only covers projects we could not reach.
    LOGIN = GH.get_user().login
    print(f"Acting as {LOGIN}")

    # Packages exempt from the cleanup are also exempt from being nagged about,
    # since their wheels are not going anywhere
    ignored = read_ignored(IGNORE_FILE)
    names = [name for name in list_packages() if name not in ignored]

    now = datetime.now(timezone.utc)
    # Most of the runtime is the ~5 read-only lookups each package needs; writes
    # below stay serial.
    with ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(resolve, names))

    # Several packages can be built from one repository; report them together.
    by_repo = defaultdict(list)
    for package in packages:
        if package.repo is not None:
            by_repo[package.repo.full_name].append(package)
    for group in by_repo.values():
        handle_repo(group[0].repo, group, now)

    write_summary(packages, now)
    annotate(NOTICES)
    errors = [package.error for package in packages if package.error]
    if errors:
        report_errors(errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
