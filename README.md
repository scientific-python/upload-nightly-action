# Nightly upload

This provides a standard GitHub Action to upload nightly builds to the
scientific-python nightly channel.

In your Continuous Intregration pipeline once you've built you wheel, you can
use the following snippet to upload to our central nightly repository:

```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@main
      with:
        artifacts_path: dist
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
```

To request access to the repository please open an issue on [this action
repository](https://github.com/scientific-python/upload-nightly-action). You can
then generate a token at `https://anaconda.org/scientific-python-nightly-wheels/settings/access`
with _Allow write access to the API site_ and _Allow uploads to Standard Python repositories_
permissions and add the token as a secret to your GitHub repository.

# Using nightly builds in CI

To test those nightly build, you can use the following command to install from
the nightly package.

```sh
python -m pip install \
  --upgrade \
  --pre \
  --index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
  --extra-index-url https://pypi.org/simple \
  matplotlib
```

Note that `--index-url` takes priority over `--extra-index-url`.
Packages, and dependencies, with versions available on the
[nightly package index][] will be installed from there before falling back to
the [Python Package Index][PyPI] to install all remaining requested packages.

```
if package in nightly:
   try to install from nightly
else:
   try to install from pypi
```

If you want to install nightly builds within your conda environment, you can specify an
extra index in your YML file.

```yml
name: test
dependencies:
  - pip
  - pip:
    - --pre --index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple --extra-index-url https://pypi.org/simple
    - matplotlib
```

[nightly package index]: https://anaconda.org/scientific-python-nightly-wheels
[PyPI]: https://pypi.org/
