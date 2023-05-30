#!/bin/bash

# fail on undefined variables
set -u
# Prevent pipe errors to be silenced
set -o pipefail
# Exit if any command exit as non-zero
set -e
# enable trace mode (print what it does)
set -x

# get the anaconda token from the github secrets
#
# this is to prevent accidental uploads
echo "Getting anaconda token from github secrets..."

ANACONDA_ORG="scientific-python-nightly-wheels"
ANACONDA_TOKEN="$INPUT_ANACONDA_NIGHTLY_UPLOAD_TOKEN"

# if the ANACONDA_TOKEN is empty, exit with status -1
# this is to prevent accidental uploads
if [ -z "$ANACONDA_TOKEN" ]; then
  echo "ANACONDA_TOKEN is empty , exiting..."
  exit -1
fi

# install anaconda-client
echo "Installing anaconda-client..."

conda install -y anaconda-client -c conda-forge

# trim trailing slashes from $INPUT_ARTIFACTS_PATH
INPUT_ARTIFACTS_PATH="${INPUT_ARTIFACTS_PATH%/}"

# debug, print env
env

# upload wheels
echo "Uploading wheels to anaconda.org..."

anaconda --token "${ANACONDA_TOKEN}" upload \
  --user "${ANACONDA_ORG}" \
  --skip-existing \
  "${INPUT_ARTIFACTS_PATH}"/*.whl
echo "Index: https://pypi.anaconda.org/${ANACONDA_ORG}/simple"
