#!/usr/bin/env python
"""
Remove old nightly wheel uploads from an Anaconda.org channel.

For a single package, it keeps the newest INPUT_N_LATEST_UPLOADS versions and additionally removes any version whose most recent upload is older than 30 days.

The inputs are read from the environment (see remove-wheels/action.yml):

- INPUT_ANACONDA_USER     - the Anaconda.org organisation/user to clean up
- INPUT_ANACONDA_TOKEN    - a token with permission to remove artifacts
- INPUT_N_LATEST_UPLOADS  - the number of newest versions to keep
- INPUT_PACKAGE_NAME      - the package to prune
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.anaconda.org"


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def latest_upload_date(distributions):
    """
    Return the date (YYYY-MM-DD) of the most recent distribution upload
    or an empty string if there are no upload times present. c.f.
    https://github.com/Anaconda-Platform/anaconda-client/issues/682#issuecomment-1677283067
    """
    upload_times = [
        "null" if d.get("upload_time") is None else str(d["upload_time"])
        for d in distributions
    ]
    if not upload_times:
        return ""
    latest = max(upload_times)
    fields = latest.split()
    return fields[0] if fields else ""


def main():
    anaconda_user = os.environ.get("INPUT_ANACONDA_USER", "")
    anaconda_token = os.environ.get("INPUT_ANACONDA_TOKEN", "")
    n_latest_uploads = os.environ.get("INPUT_N_LATEST_UPLOADS", "")
    package_name = os.environ.get("INPUT_PACKAGE_NAME", "")

    if not anaconda_token:
        print("ANACONDA_TOKEN is empty, exiting...")
        sys.exit(1)
    if not n_latest_uploads:
        print("N_LATEST_UPLOADS is empty, exiting...")
        sys.exit(1)
    if not package_name:
        print("PACKAGE_NAME is empty, exiting...")
        sys.exit(1)

    n_latest = int(n_latest_uploads)

    # 1. Remove all but the last ${n_latest} package versions.
    # 2. Remove all package versions older than 30 days.

    print(f"\n# package: {package_name}")

    threshold_date = datetime.now(timezone.utc).date() - timedelta(days=30)

    # The API lists releases oldest-first, so keep the newest ${n_latest}
    # uploads by marking all but the last ${n_latest} versions for removal.
    releases = get_json(f"{API}/package/{anaconda_user}/{package_name}").get(
        "releases", []
    )
    versions = [release["version"] for release in releases]
    if n_latest == 0:
        remove_versions = set(versions)
    elif n_latest < len(versions):
        remove_versions = set(versions[:-n_latest])
    else:
        remove_versions = set()

    for version in versions:
        # c.f. https://github.com/Anaconda-Platform/anaconda-client/issues/682#issuecomment-1677283067
        distributions = get_json(
            f"{API}/release/{anaconda_user}/{package_name}/{version}"
        ).get("distributions", [])
        upload_date = latest_upload_date(distributions)

        # check that the upload_date is YYYY-MM-DD formatted
        # c.f. https://github.com/scientific-python/upload-nightly-action/issues/73
        try:
            parsed_date = datetime.strptime(upload_date, "%Y-%m-%d").date()
        except ValueError:
            print(
                f"# ERROR: {anaconda_user}/{package_name}/{version} upload date {upload_date} is not YYYY-MM-DD."
            )
        else:
            if parsed_date < threshold_date:
                print(
                    f"# {anaconda_user}/{package_name}/{version} last uploaded on {upload_date}"
                )
                remove_versions.add(version)

    for version in sorted(remove_versions):
        print(f"# Removing {anaconda_user}/{package_name}/{version}")
        subprocess.check_call(
            [
                "anaconda",
                "--token",
                anaconda_token,
                "remove",
                "--force",
                f"{anaconda_user}/{package_name}/{version}",
            ]
        )

    print(
        f"Finished removing old wheels except the last {n_latest_uploads} uploads "
        f"for {anaconda_user}/{package_name}."
    )


if __name__ == "__main__":
    main()
