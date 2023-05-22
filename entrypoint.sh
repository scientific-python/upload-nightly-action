#!/bin/bash

set -e
set -x

ANACONDA_ORG="scientific-python-nightly-wheel"
ANACONDA_TOKEN="$ANACONDA_NIGHTLY_UPLOAD_TOKEN"


export PATH=$CONDA/bin:$PATH
micromamba create -n upload -y python anaconda-client -c conda-forge
micromamba activate upload

anaconda -t $ANACONDA_TOKEN upload --force -u $ANACONDA_ORG $ARTIFACTS_PATH/*.whl
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
