#!/bin/bash

# fail on undefined variables
set -u
# Prevent pipe errors to be silenced
set -o pipefail
# Exit if any command exit as non-zero
set -e
# enable trace mode (print what it does)
set -x

ANACONDA_ORG="scientific-python-nightly-wheels"
ANACONDA_TOKEN="$INPUT_ANACONDA_NIGHTLY_UPLOAD_TOKEN"

conda install -y anaconda-client -c conda-forge

# trim trailing slashes from $INPUT_ARTIFACTS_PATH
INPUT_ARTIFACTS_PATH="${INPUT_ARTIFACTS_PATH%/}"

# debug, print env
env

# upload wheels
echo "Uploading wheels to anaconda.org..."

anaconda -t $ANACONDA_TOKEN upload --force -u "$ANACONDA_ORG" "$INPUT_ARTIFACTS_PATH"/*.whl
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
