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
# this is to prevent accidental removals
echo "Getting anaconda token from github secrets..."

ANACONDA_USER="${INPUT_ANACONDA_USER}"
ANACONDA_TOKEN="${INPUT_ANACONDA_TOKEN}"
N_LATEST_UPLOADS="${INPUT_N_LATEST_UPLOADS}"

# if the ANACONDA_USER is empty, exit with status -1
# this is to prevent attempts to remove from the wrong anaconda channel
# whcih should fail anyway, but it is better to fail early?
if [ -z "${ANACONDA_USER}" ]; then
  echo "ANACONDA_USER is empty, exiting..."
  exit -1
fi


# if the ANACONDA_TOKEN is empty, exit with status -1
# this is to prevent accidental removals
if [ -z "${ANACONDA_TOKEN}" ]; then
  echo "ANACONDA_TOKEN is empty, exiting..."
  exit -1
fi

# if the N_LATEST_UPLOADS is empty, exit with status -1
# as this should be set in by the user and it is better
# to fail on this to signal a problem. i.e.,
# explicit is better than implicit.
if [ -z "${N_LATEST_UPLOADS}" ]; then
  echo "N_LATEST_UPLOADS is empty, exiting..."
  exit -1
fi


# Query the package index for packages
#
# TODO: should be possible to alter this, since separating the workflow
# into two steps, one for uploading and one for cleanup, should make it
# possible for users to manually trigger the cleanup step before/after the
# upload step has completed in their own repos instead of us having to do it.
#
# TODO: raises questions on how to moderate cleanups among multiple users
# operating on the same channel, but that might be a different issue.
curl https://raw.githubusercontent.com/scientific-python/upload-nightly-action/main/packages-ignore-from-cleanup.txt --output packages-ignore-from-cleanup.txt
anaconda show "${ANACONDA_USER}" &> >(grep "${ANACONDA_USER}/") | \
    awk '{print $1}' | \
    sed 's|.*/||g' | \
    grep -vf packages-ignore-from-cleanup.txt > package-names.txt

# Remove old uploads to save space
# Remove all _but_ the last ${N_LATEST_UPLOADS} package versions and
# remove all package versions older than 30 days.
if [ -s package-names.txt ]; then
    threshold_date="$(date +%F -d '30 days ago')"

    # Remember can't quote subshell as need to split on (space separated) token
    for package_name in $(cat package-names.txt); do
    # TODO: this outer loop can be removed when ready since there will be
    # just one package to remove when the action is triggered manually from
    # a user's (different) repo.

        echo -e "\n# package: ${package_name}"

        curl --silent https://api.anaconda.org/package/"${ANACONDA_USER}/${package_name}" | \
            jq -r '.releases[].version' > package-versions.txt
        head --lines "-${N_LATEST_UPLOADS}" package-versions.txt > remove-package-versions.txt

        for package_version in $(cat package-versions.txt); do
          # c.f. https://github.com/Anaconda-Platform/anaconda-client/issues/682#issuecomment-1677283067
          upload_date=$(curl --silent https://api.anaconda.org/release/"${ANACONDA_USER}/${package_name}/${package_version}" | \
              jq -r '.distributions[].upload_time' | \
              sort | \
              tail --lines 1 | \
              awk '{print $1}')

          # check upload_date is YYYY-MM-DD formatted
          # c.f. https://github.com/scientific-python/upload-nightly-action/issues/73
          if [[ "${upload_date}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
              if [[ "${upload_date}" < "${threshold_date}" ]]; then
                  echo "# ${ANACONDA_USER}/${package_name}/${package_version} last uploaded on ${upload_date}"
                  echo "${package_version}" >> remove-package-versions.txt
              fi
          else
              echo "# ERROR: ${ANACONDA_USER}/${package_name}/${package_version} upload date ${upload_date} is not YYYY-MM-DD."
          fi

        done

        if [ -s remove-package-versions.txt ]; then
            # Guard against duplicate entries from packages over
            # count and time thresholds
            sort --output remove-package-versions.txt --unique remove-package-versions.txt

            for package_version in $(cat remove-package-versions.txt); do
                echo "# Removing ${ANACONDA_USER}/${package_name}/${package_version}"
                anaconda --token "${ANACONDA_TOKEN}" remove \
                  --force \
                  "${ANACONDA_USER}/${package_name}/${package_version}"
            done
        fi

    done
fi

echo "Finished removing old wheels except the last ${N_LATEST_UPLOADS} uploads from the ${ANACONDA_USER} channel."
