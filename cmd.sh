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

ANACONDA_ORG="${INPUT_ANACONDA_NIGHTLY_UPLOAD_ORGANIZATION}"
ANACONDA_TOKEN="${INPUT_ANACONDA_NIGHTLY_UPLOAD_TOKEN}"
ANACONDA_LABELS="${INPUT_ANACONDA_NIGHTLY_UPLOAD_LABELS}"

# if the ANACONDA_ORG is empty, exit with status -1
# this is to prevent attempt to upload to the wrong anaconda channel
if [ -z "${ANACONDA_ORG}" ]; then
  echo "ANACONDA_ORG is empty, exiting..."
  exit -1
fi


# if the ANACONDA_TOKEN is empty, exit with status -1
# this is to prevent accidental uploads
if [ -z "${ANACONDA_TOKEN}" ]; then
  echo "ANACONDA_TOKEN is empty , exiting..."
  exit -1
fi

# if the ANACONDA_LABELS is empty, exit with status -1
# as this should be set in action.yml or by the user
# and it is better to fail on this to sigal a problem.
if [ -z "${ANACONDA_LABELS}" ]; then
  echo "ANACONDA_LABELS is empty, exiting..."
  exit -1
fi

# convert newlines to commas for parsing
# and ensure that there is no trailing comma
ANACONDA_LABELS="$(tr '\n' ',' <<< "${ANACONDA_LABELS}" | sed 's/,$//')"

IFS=',' read -ra LABELS <<< "${ANACONDA_LABELS}"

LABEL_ARGS=""
for label in "${LABELS[@]}"; do
  LABEL_ARGS+="--label ${label} "
done

# Install anaconda-client from lock file
echo "Installing anaconda-client from upload-nightly-action conda-lock lock file..."
micromamba create \
  --yes \
  --name upload-nightly-action \
  --file /conda-lock.yml

# 'micromamba' is running as a subprocess and can't modify the parent shell.
# Thus you must initialize your shell before using activate and deactivate.
eval "$(micromamba shell hook --shell bash)"
micromamba activate upload-nightly-action

# trim trailing slashes from $INPUT_ARTIFACTS_PATH
INPUT_ARTIFACTS_PATH="${INPUT_ARTIFACTS_PATH%/}"

# upload wheels
echo "Uploading wheels to anaconda.org..."

# Note: ${LABEL_ARGS} must not be quoted during shell parameter expansion,
# else it will be treated as a file and not additional command arguments.
anaconda --token "${ANACONDA_TOKEN}" upload \
  --force \
  --user "${ANACONDA_ORG}" \
  ${LABEL_ARGS} \
  "${INPUT_ARTIFACTS_PATH}"/*.whl
echo "Index: https://pypi.anaconda.org/${ANACONDA_ORG}/simple"
