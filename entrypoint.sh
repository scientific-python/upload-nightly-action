#!/bin/bash

set -e
set -x

ANACONDA_ORG="scientific-python-nightly-wheel"
ANACONDA_TOKEN="$ANACONDA_NIGHTLY_UPLOAD_TOKEN"

micromamba install -y -n base python anaconda-client -c conda-forge
eval "$(micromamba shell hook --shell=)"
micromamba activate base

anaconda -t $ANACONDA_TOKEN upload --force -u $ANACONDA_ORG $ARTIFACTS_PATH/*.whl
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
