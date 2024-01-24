# Nightly upload

This is a GitHub Action that uploads nightly builds to the [scientific-python nightly channel][],
as recommended in [SPEC4 — Using and Creating Nightly Wheels][].

In a GitHub Actions workflow (`.github/workflows/*.yaml`), use the
following snippet to upload built wheels to the channel:

```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@6e9304f7a3a5501c6f98351537493ec898728299 # 0.3.0
      with:
        artifacts_path: dist
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
```

Note that we recommend pinning the action against a specific SHA
(rather than a tag), to guard against the unlikely event of upstream
being compromised.

## Updating the action

You can [use Dependabot to keep the GitHub Action up to date][],
with a `.github/dependabot.yml` config file similar to:

```yaml
version: 2
updates:
  # Maintain dependencies for GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

## Access to the ``scientific-python-nightly-wheels`` channel

To request access to the wheel channel, please open an issue on [the upload action's
repository](https://github.com/scientific-python/upload-nightly-action). You can
then generate a token at `https://anaconda.org/scientific-python-nightly-wheels/settings/access`
with permissions to _Allow write access to the API site_ and _Allow uploads to Standard Python repositories_,
and add the token as a secret to your GitHub repository.

## Using a different channel

This Github Action can upload your nightly builds to a different channel. To do so,
define the `anaconda_nightly_upload_organization` variable. Furthermore,
you can add labels for organizing your artifacts using `anaconda_nightly_upload_labels`
optional parameter. See below:

```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@6e9304f7a3a5501c6f98351537493ec898728299 # 0.3.0
      with:
        artifacts_path: dist
        anaconda_nightly_upload_organization: my-alternative-organization
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
        anaconda_nightly_upload_labels: dev
```

## Artifact cleanup-policy at the ``scientific-python-nightly-wheels`` channel

To avoid hosting outdated development versions, as well as to clean up space, we do have a
default retention policy of:

- Latest **5 versions**
- Artifacts newer than **30 days**

Any versions beyond these are automatically removed as part of a daily cron job run from this repository.
Projects may have reasons to request to be added to the list exempt from this automated cleanup, however
in that case the responsibility of cleaning-up old, unused versions fall back on the individual project.

# Using nightly builds in CI

To test against nightly builds, you can use the following command to install from
the nightly channel:

```sh
python -m pip install \
  --upgrade \
  --pre \
  --index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
  --extra-index-url https://pypi.org/simple \
  matplotlib
```

Note that `--index-url` takes priority over `--extra-index-url`, so
that packages, and their dependencies, with versions available in the
nightly channel will be installed before falling back to the [Python
Package Index][PyPI].

To install nightly builds within a conda environment, specify an extra
index in your `environment.yml`:

```yml
name: test
dependencies:
  - pip
  - pip:
    - --pre --index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple --extra-index-url https://pypi.org/simple
    - matplotlib
```

[use Dependabot to keep the GitHub Action up to date]: https://learn.scientific-python.org/development/guides/gha-basic/#updating
[PyPI]: https://pypi.org/
[scientific-python nightly channel]: https://anaconda.org/scientific-python-nightly-wheels
[SPEC4 — Using and Creating Nightly Wheels]: https://scientific-python.org/specs/spec-0004/
