#!/usr/bin/env python
# /// script
# dependencies = [
#     "PyGithub",
#     "pytest",
#     "requests",
# ]
# requires-python = ">=3.11"
#
# [tool.uv]
# # month window to find security issues
# exclude-newer = "30 days"
# ///
"""Tests for ``tools/check_stale_wheels.py``."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_stale_wheels

# Real metadata, trimmed to the keys that matter. Every case here is one that a
# package on the channel actually exercises.
CASES = {
    # The tracker wins over equally valid alternatives.
    "scikit-learn": (
        {
            "source": "https://github.com/scikit-learn/scikit-learn",
            "tracker": "https://github.com/scikit-learn/scikit-learn/issues",
            "download": "https://pypi.org/project/scikit-learn/#files",
        },
        "scikit-learn/scikit-learn",
    ),
    # github.com/orgs/<name> is not a repository, and must not win over the real one.
    "scikit_build_core": (
        {
            "Discussions": "https://github.com/orgs/scikit-build/discussions",
            "Homepage": "https://github.com/scikit-build/scikit-build-core",
        },
        "scikit-build/scikit-build-core",
    ),
    # An unrecognized key ("upstream") must not beat a recognized one.
    "scipy-openblas32": (
        {
            "homepage": "https://github.com/MacPython/openblas-libs",
            "upstream": "https://github.com/OpenMathLib/OpenBLAS",
        },
        "MacPython/openblas-libs",
    ),
    # Deep links are trimmed back to owner/repo. This one is also a repository that
    # has since been renamed, which resolve() canonicalizes separately.
    "awkward": (
        {"Bug Tracker": "https://github.com/scikit-hep/awkward-1.0/issues"},
        "scikit-hep/awkward-1.0",
    ),
    # A blob URL is still only useful for the owner/repo part.
    "python-flint": (
        {
            "Changelog": "https://github.com/flintlib/python-flint/blob/master/README.md#changelog",
            "Repository": "https://github.com/flintlib/python-flint",
        },
        "flintlib/python-flint",
    ),
    # home_page is folded in under a key we recognize.
    "pyproj": ({"home": "https://github.com/pyproj4/pyproj"}, "pyproj4/pyproj"),
    # Hyphenated and spaced spellings of the same keys both count.
    "xarray": (
        {
            "issue-tracker": "https://github.com/pydata/xarray/issues",
            "source-code": "https://github.com/pydata/xarray",
        },
        "pydata/xarray",
    ),
    # A repository visible only through a key that doesn't name it is not trusted;
    # such a project needs a PYPI_MAP entry rather than a guess.
    "changelog-only": ({"Changelog": "https://github.com/foo/bar/releases"}, None),
    # Nothing on GitHub: PYPI_MAP has to cover these.
    "icechunk": ({"Homepage": "https://icechunk.io", "Docs": "https://docs.earthmover.io"}, None),
    "nothing-at-all": ({}, None),
}


@pytest.fixture
def project_urls(monkeypatch):
    """Serve canned PyPI metadata instead of hitting the network."""

    def fake(name):
        return CASES[name][0]

    monkeypatch.setattr(check_stale_wheels, "pypi_project_urls", fake)


@pytest.mark.parametrize("name", list(CASES))
def test_repo_from_pypi(project_urls, name):
    assert check_stale_wheels.repo_from_pypi(name) == CASES[name][1]


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/foo/bar.git", "foo/bar"),
        ("http://github.com/foo/bar", "foo/bar"),
        ("https://www.github.com/foo/bar", "foo/bar"),
        ("https://GitHub.com/Foo/Bar", "Foo/Bar"),
        ("https://github.com/foo/bar#readme", "foo/bar"),
        ("https://gitlab.com/foo/bar", None),
        ("https://github.com/orgs/foo/discussions", None),
        ("https://example.com", None),
    ],
)
def test_repo_from_pypi_url_forms(monkeypatch, url, expected):
    monkeypatch.setattr(check_stale_wheels, "pypi_project_urls", lambda name: {"source": url})
    assert check_stale_wheels.repo_from_pypi("whatever") == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
