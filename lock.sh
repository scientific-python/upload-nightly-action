#!/bin/bash

# This should be the base image the Docker image built by the GitHub Action uses
BUILD_IMAGE="mambaorg/micromamba:1.4.9-bullseye-slim"
docker pull "${BUILD_IMAGE}"

# Don't need to ensure emulation possible on non-x86_64 platforms at the
# `docker run` level as the platform is specified in the conda-lock command.
docker run \
    --rm \
    --volume "${PWD}":/work \
    --workdir /work \
    "${BUILD_IMAGE}" \
    /bin/bash -c "\
        micromamba install --yes --channel conda-forge conda-lock && \
        conda-lock lock --micromamba --platform linux-64 --file environment.yml"
