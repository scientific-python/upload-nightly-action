# Nightly upload

This is a GitHub Action that uploads (and helps remove) nightly builds to
the [scientific-python nightly channel][], as recommended in
[SPEC4 — Using and Creating Nightly Wheels][].

In a GitHub Actions workflow (`.github/workflows/*.yaml`), use the
following snippet on a Linux or macOS runner to upload built wheels to the
channel:

```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@82396a2ed4269ba06c6b2988bb4fd568ef3c3d6b # 0.6.1
      with:
        artifacts_path: dist
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
```

> [!IMPORTANT]
> Note that we recommend pinning the action against a specific SHA
(rather than a tag), to guard against the unlikely event of upstream
being compromised.

# Removing old nightly builds

This repository also ships with an action to ease removals of older nightly wheels from a channel.

To use this functionality, add the following snippet to your workflow:

```yml
jobs:
  steps:
    ...
    - name: Remove old wheels
      uses: scientific-python/upload-nightly-action/remove-wheels@cantknowhashyet # 0.6.0
      with:
        n_latest_uploads: ${{ env.N_LATEST_UPLOADS }}
        anaconda_nightly_upload_organization: "your-organization"
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
```

Which will remove all but the `n_latest_uploads` latest uploads from the channel. This is useful
to avoid hosting outdated development versions, as well as to clean up space.

Note that the ``scientific-python-nightly-wheels`` channel, specifically, already removes
old artifacts daily. The `remove-wheels` action is, therefore, intended for use with
other channels.

If you do not wish to have this automated cleanup, please [open an issue](https://github.com/scientific-python/upload-nightly-action/)
to be added to the list of packages exempt from it. The current ones are named in
[`packages-ignore-from-cleanup.txt`](packages-ignore-from-cleanup.txt).

Please refer to the [artifact cleanup policy][] for more information.

## Updating the actions

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
then generate a token at `https://anaconda.org/<anaconda cloud user name>/settings/access`
with permissions to _Allow write access to the API site_ and _Allow uploads to Standard Python repositories_,
and add the token as a secret to your GitHub repository.

## Using a channel other than ``scientific-python-nightly-wheels``

This Github Action can upload your nightly builds to a different channel. To do so,
define the `anaconda_nightly_upload_organization` variable. Furthermore,
you can add labels for organizing your artifacts using `anaconda_nightly_upload_labels`
optional parameter. See below:

```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@82396a2ed4269ba06c6b2988bb4fd568ef3c3d6b # 0.6.1
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
[artifact cleanup policy]: #artifact-cleanup-policy-at-the-scientific-python-nightly-wheels-channel
