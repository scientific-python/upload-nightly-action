#!/bin/bash

set -e
set -x

ANACONDA_ORG="scientific-python-nightly-wheel"
ANACONDA_TOKEN="$ANACONDA_NIGHTLY_UPLOAD_TOKEN"


export PATH=$CONDA/bin:$PATH
mnicromamba create -n upload -y python=3.10 anaconda-client
mnicromamba activate upload

anaconda -t $ANACONDA_TOKEN upload --force -u $ANACONDA_ORG $ARTIFACTS_PATH/*.whl
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
