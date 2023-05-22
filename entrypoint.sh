#!/bin/bash

# fail on undefined variables
set -u
# Prevent pipe errors to be silenced
set -o pipefail
# Exit if any command exit as non-zero
set -e
# enable trace mode (print what it does)
set -x

ANACONDA_ORG="scientific-python-nightly-wheel"
ANACONDA_TOKEN="$INPUT_ANACONDA_NIGHTLY_UPLOAD_TOKEN"

micromamba install -y -n base python anaconda-client -c conda-forge
eval "$(micromamba shell hook --shell=bash)"
micromamba activate base

anaconda -t $ANACONDA_TOKEN upload --force -u "$ANACONDA_ORG" "$ARTIFACTS_PATH/*.whl"
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
