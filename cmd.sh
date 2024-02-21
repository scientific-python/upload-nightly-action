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

get_wheel_name_version() {
    local wheel_name="$1"
    if [[ "${wheel_name}" =~ ^([[:alnum:]_-]+)-([0-9][^-]+)-(.+)$ ]]; then
        # return the package_name and version_number
        local return_values=("${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}")
        echo "${return_values[@]}"
    else
        echo "The wheel name ${1} does not follow the PEP 491 spec (https://peps.python.org/pep-0491/) and is invalid."
        return 1
    fi
}

# get the unique package names from all the wheels
package_names=()
for wheel_path in "${INPUT_ARTIFACTS_PATH}"/*.whl; do
  # remove the INPUT_ARTIFACTS_PATH/ prefix (including the /)
  wheel_name="${wheel_path#${INPUT_ARTIFACTS_PATH}/}"
  read -r package_basename_prefix _ <<< "$(get_wheel_name_version ${wheel_name})"
  package_names+=("${package_basename_prefix}")
done
package_names=($(tr ' ' '\n' <<< "${package_names[@]}" | sort --unique | tr '\n' ' '))

# If the package version doesn't exist on the package index then there will
# be no files to overwrite and the package can be uploaded safely.
# If the package version exists, is the only version on the package index,
# and only has one distribution file, then that package needs to be removed
# from the index before a wheel of the same name can be uploaded again.
# c.f. https://github.com/Anaconda-Platform/anaconda-client/issues/702

for package_basename_prefix in "${package_names[@]}"; do
  # normalize package_name to use '-' as delimiter
  package_name="${package_basename_prefix//_/-}"

  number_releases=$(curl --silent https://api.anaconda.org/package/"${ANACONDA_ORG}/${package_name}" | \
    jq -r '.releases' | \
    jq length)

  if [ "${number_releases}" -eq 1 ]; then
    # get any wheel for the package (they should all have the same version)
    wheel_path=$(find "${INPUT_ARTIFACTS_PATH}" -name "${package_basename_prefix}-*.whl" -print -quit)
    wheel_name="${wheel_path#${INPUT_ARTIFACTS_PATH}/}"
    read -r _ package_version <<< "$(get_wheel_name_version ${wheel_name})"

    number_files=$(curl --silent https://api.anaconda.org/release/"${ANACONDA_ORG}/${package_name}/${package_version}" | \
      jq -r '.distributions' | \
      jq length)

    if [ "${number_files}" -eq 1 ]; then
      distribution_name=$(curl --silent https://api.anaconda.org/release/"${ANACONDA_ORG}/${package_name}/${package_version}" | \
        jq -r '.distributions[].basename')

      if [ "${wheel_name}" = "${distribution_name}" ]; then
        echo -e "\n# ${distribution_name} is the only distribution file uploaded for the package https://anaconda.org/${ANACONDA_ORG}/${package_name}"
        echo "# To avoid https://github.com/Anaconda-Platform/anaconda-client/issues/702 remove the existing release before uploading."

        echo -e "\n# Removing ${ANACONDA_ORG}/${package_name}/${package_version}"
        anaconda --token "${ANACONDA_TOKEN}" remove \
          --force \
          "${ANACONDA_ORG}/${package_name}/${package_version}"
      fi
    fi
  fi
done

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
