#!/bin/bash

set -e
set -x

ANACONDA_ORG="scientific-python-nightly-wheel"
ANACONDA_TOKEN="$ANACONDA_NIGHTLY_UPLOAD_TOKEN"


export PATH=$CONDA/bin:$PATH
conda create -n upload -y python=3.10
source activate upload
conda install -y anaconda-client

anaconda -t $ANACONDA_TOKEN upload --force -u $ANACONDA_ORG $ARTIFACTS_PATH/*.whl
echo "Index: https://pypi.anaconda.org/$ANACONDA_ORG/simple"
