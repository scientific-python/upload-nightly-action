#!/bin/bash

# fail on undefined variables
set -u
# Prevent pipe errors to be silenced
set -o pipefail
# Exit if any command exit as non-zero
set -e
# enable trace mode (print what it does)
set -x

ANACONDA_USER="${INPUT_ANACONDA_USER}"
ANACONDA_TOKEN="${INPUT_ANACONDA_TOKEN}"
N_LATEST_UPLOADS="${INPUT_N_LATEST_UPLOADS}"
PACKAGE_NAME="${INPUT_PACKAGE_NAME}"

if [ -z "${ANACONDA_TOKEN}" ]; then
  echo "ANACONDA_TOKEN is empty, exiting..."
  exit 1
fi

if [ -z "${N_LATEST_UPLOADS}" ]; then
  echo "N_LATEST_UPLOADS is empty, exiting..."
  exit 1
fi

if [ -z "${PACKAGE_NAME}" ]; then
  echo "PACKAGE_NAME is empty, exiting..."
  exit 1
fi

# Remove all _but_ the last ${N_LATEST_UPLOADS} package versions and
# remove all package versions older than 30 days.

echo -e "\n# package: ${PACKAGE_NAME}"

threshold_date="$(date +%F -d '30 days ago')"

curl --silent https://api.anaconda.org/package/"${ANACONDA_USER}/${PACKAGE_NAME}" | \
    jq -r '.releases[].version' > package-versions.txt
tail --lines "+$(( N_LATEST_UPLOADS + 1 ))" package-versions.txt > remove-package-versions.txt

for package_version in $(cat package-versions.txt); do
  # c.f. https://github.com/Anaconda-Platform/anaconda-client/issues/682#issuecomment-1677283067
  upload_date=$(curl --silent https://api.anaconda.org/release/"${ANACONDA_USER}/${PACKAGE_NAME}/${package_version}" | \
      jq -r '.distributions[].upload_time' | \
      sort | \
      tail --lines 1 | \
      awk '{print $1}')

  # check upload_date is YYYY-MM-DD formatted
  # c.f. https://github.com/scientific-python/upload-nightly-action/issues/73
  if [[ "${upload_date}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
      if [[ "${upload_date}" < "${threshold_date}" ]]; then
          echo "# ${ANACONDA_USER}/${PACKAGE_NAME}/${package_version} last uploaded on ${upload_date}"
          echo "${package_version}" >> remove-package-versions.txt
      fi
  else
      echo "# ERROR: ${ANACONDA_USER}/${PACKAGE_NAME}/${package_version} upload date ${upload_date} is not YYYY-MM-DD."
  fi

done

if [ -s remove-package-versions.txt ]; then
    # Guard against duplicate entries from packages over
    # count and time thresholds
    sort --output remove-package-versions.txt --unique remove-package-versions.txt

    for package_version in $(cat remove-package-versions.txt); do
        echo "# Removing ${ANACONDA_USER}/${PACKAGE_NAME}/${package_version}"
        anaconda --token "${ANACONDA_TOKEN}" remove \
          --force \
          "${ANACONDA_USER}/${PACKAGE_NAME}/${package_version}"
    done
fi

echo "Finished removing old wheels except the last ${N_LATEST_UPLOADS} uploads for ${ANACONDA_USER}/${PACKAGE_NAME}."
