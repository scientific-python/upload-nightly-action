# Notes for agents

Guidance for automated contributors working in this repository.
Written for someone who can read the code but has no way to know the conventions or the reasoning behind them.

## What is here

`action.yml` and `upload_wheels.sh` are the published action itself, which projects call from their own workflows to upload nightly wheels.
Everything else exists to look after the [`scientific-python-nightly-wheels`](https://anaconda.org/scientific-python-nightly-wheels) channel those uploads land on.

`.github/workflows/remove-wheels.yml` deletes wheels beyond the retention policy, daily at 01:23 UTC.
`tools/check_stale_wheels.py` warns projects before that deletion strands them, daily at 00:23 UTC.
The hour between the two is deliberate: a package must be flagged before it can be deleted, and a fully deleted package disappears from the channel listing where we would no longer see it at all.

`.github/workflows/report-failure.yml` is a reusable workflow every scheduled workflow calls when it fails.
This repository nags other projects about silently broken automation, so its own cron jobs must not fail quietly.
It is called as a job rather than used as a composite action because `ci.yml` checks out to `_action_path` and `remove-wheels.yml` does not check out at all.

## Conventions

Pin third-party actions to a full commit SHA with a `# vX.Y.Z` comment; Dependabot updates them monthly as a single group.

Run the Python tools with `uv run --with-requirements tools/requirements.txt <script>`, which is how the workflows invoke them; the scripts carry no PEP 723 header, so that their dependencies are declared in exactly one place.
That file pins exact versions rather than a `uv.lock`, because Dependabot has no `uv` ecosystem and an unmaintainable lock would only rot, while it does understand `tools/requirements.txt` and proposes updates monthly.
`scientific-python/issue-from-pytest-log-action` is worth reading for the rest of the house style, though it locks its scripts individually where this repository does not.

Pin versions exactly, as `pixi.toml` and `tools/requirements.txt` both do.
Do not add a `[tool.uv] exclude-newer` window to a script whose dependencies Dependabot pins: uv then refuses to resolve any pin newer than the cutoff, leaving every Dependabot pull request unresolvable until the release ages past it.
The window in `pixi.toml` is fine, because those versions are bumped by hand.

Format Python with `ruff format --line-length 100`; there is no ruff configuration in the repository yet, so pass the length explicitly.

## Things that will catch you out

Pull requests from forks *and* from Dependabot receive no secrets, so a job keyed on `github.event.pull_request.head.repo.fork` still breaks for Dependabot.
Gate on the secret instead, as `ci.yml` does with `HAS_TOKEN: ${{ secrets.UPLOAD_TOKEN != '' }}`, and have the tokenless path assert the action refuses to upload.

A called workflow's token is capped by the calling job's, so a job that calls `report-failure.yml` must itself declare `permissions: issues: write`.

The anaconda.org API's `latest_version` is not the most recently uploaded version, because nightly version strings do not sort consistently across projects.
Take the maximum `upload_time` across every version instead.

That API carries no repository URL for these packages — `home`, `dev_url`, and `source_git_url` are all null — so `check_stale_wheels.py` resolves the target repository from PyPI `Project-URL` metadata, with `PYPI_MAP` covering the one package that has none.

PyGithub serializes every request through an internal connection lock, so threading does not speed up the GitHub half of a run.
A full stale wheel check takes about two minutes, which is fine for a daily job.

## Working on the stale wheel check

Run it with `ISSUE_OPENER_TOKEN` and `GITHUB_TOKEN` set, and keep `--dry-run` on unless you intend to open issues in other projects' trackers.
Dry runs still authenticate and still read issues; they only skip writes.

The thresholds are constants at the top of the script rather than command line options, by request: add an option only when something actually needs to vary.
`RETENTION_DAYS` must stay in step with the 30 days in `remove-wheels.yml` and the policy section of `README.md`.

Tests live in `tests/test_check_stale_wheels.py` and run with `uv run --frozen tests/test_check_stale_wheels.py`.
They stub the network, so they are fast and safe to run anywhere.
Every case in them is a real package whose metadata would break a naive implementation; add to that table rather than replacing it when the resolution logic changes.

Issues opened in other projects are posted by [@scientific-python-bot](https://github.com/scientific-python-bot) using a classic token with the `public_repo` scope, stored as the `ISSUE_OPENER_TOKEN` secret.
Be conservative with anything that posts outward: those messages arrive unsolicited in other maintainers' inboxes.
