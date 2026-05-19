#!/usr/bin/env bash
#
# Build the bootstrap Python environment with uv.
#
# Executed every time:
# - select the uv cache location and the virtualenv build path
# - compute the install marker from OS, architecture, Python version, and packages
#
# Executed once per install marker across the cluster:
# - install uv/Python, create the virtualenv, and install Python requirements
# - coordinate the install with ${UV_INSTALL_DIR}/python_install_in_progress
# - record completion with ${UV_INSTALL_DIR}/python_install_success.<hash>
#
# The Python hash is computed from:
# - ID, VERSION_ID, arch, and python_version
# - the generated Python requirements content, including the selected CuPy wheel
#
# When ${VENV_PATH} is on a mounted/shared filesystem, the virtualenv is created
# locally at /opt/uv_local/venv/${ID^}_${VERSION_ID}_${arch}/oci and then
# replicated to the shared virtualenv path ${VENV_PATH} using parallel rsync.
set -eu -o pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/common.sh"

readonly CACHE_COPY_JOBS=16

# Shared marker names used by common.sh locking helpers.
marker_in_progress="${UV_INSTALL_DIR}/python_install_in_progress"
marker_in_progress_hostname="${marker_in_progress}/hostname"
arch=$(uname -m)

export UV_SHARED_CACHE_DIR="${UV_INSTALL_DIR}/cache"
export UV_PYTHON_INSTALL_DIR="${UV_INSTALL_DIR}/python"
export UV_LOCAL_CACHE_DIR="/opt/uv_local/cache/"
export UV_LOCAL_VENV_DIR="/opt/uv_local/venv/${ID^}_${VERSION_ID}_${arch}"
export UV_LOCAL_VENV_PATH="${UV_LOCAL_VENV_DIR}/oci"
export UV_NO_PROGRESS="yes"

# Mutable install state selected during main().
install_owner=""
python_version=""
requirements_content=""
marker_install=""
acquired=false
publish_local_uv_cache=false
shared_uv_cache_on_mounted_fs=false
install_venv_on_local_disk=false
VENV_INSTALL_PATH="${VENV_PATH}"

trap 'if [[ "${acquired}" == true && -n "${marker_in_progress}" && -d "${marker_in_progress}" ]]; then rm -rf "${marker_in_progress}"; fi' EXIT

# Treat non-root mount targets as shared filesystems where local staging is faster.
path_is_on_mounted_filesystem() {
  local path="${1}"
  local existing_path="${path}"
  local mount_target=""

  while [[ ! -e "${existing_path}" && "${existing_path}" != "/" ]]; do
    existing_path="$(dirname "${existing_path}")"
  done

  if command -v findmnt &>/dev/null; then
    mount_target="$(findmnt -n -o TARGET -T "${existing_path}" 2>/dev/null || true)"
    [[ -n "${mount_target}" && "${mount_target}" != "/" ]]
    return
  fi

  while [[ "${existing_path}" != "/" ]]; do
    if mountpoint -q "${existing_path}" 2>/dev/null; then
      return 0
    fi
    existing_path="$(dirname "${existing_path}")"
  done

  return 1
}

# Prefer an existing shared uv cache, otherwise stage locally when the shared path is mounted.
select_uv_cache() {
  publish_local_uv_cache=false
  shared_uv_cache_on_mounted_fs=false

  if path_is_on_mounted_filesystem "${UV_SHARED_CACHE_DIR}"; then
    shared_uv_cache_on_mounted_fs=true
  fi

  if [[ -d "${UV_SHARED_CACHE_DIR}" ]]; then
    export UV_CACHE_DIR="${UV_SHARED_CACHE_DIR}"
    echo "Using shared uv cache: ${UV_CACHE_DIR}"
  elif [[ "${shared_uv_cache_on_mounted_fs}" == true ]]; then
    sudo mkdir -p "${UV_LOCAL_CACHE_DIR}"
    sudo chown -R "${install_owner}" "${UV_LOCAL_CACHE_DIR}" || true
    export UV_CACHE_DIR="${UV_LOCAL_CACHE_DIR}"
    publish_local_uv_cache=true
    echo "Using local uv cache: ${UV_CACHE_DIR}"
  else
    sudo mkdir -p "${UV_SHARED_CACHE_DIR}"
    sudo chown "${install_owner}" "${UV_SHARED_CACHE_DIR}" || true
    export UV_CACHE_DIR="${UV_SHARED_CACHE_DIR}"
    echo "Using shared uv cache on local filesystem: ${UV_CACHE_DIR}"
  fi
}

# Build the virtualenv locally when the final venv path is on a mounted filesystem.
select_venv_install_path() {
  install_venv_on_local_disk=false
  VENV_INSTALL_PATH="${VENV_PATH}"

  if path_is_on_mounted_filesystem "${VENV_PATH}"; then
    install_venv_on_local_disk=true
    VENV_INSTALL_PATH="${UV_LOCAL_VENV_PATH}"
    sudo install -d -o "${install_owner%:*}" -g "${install_owner#*:}" "${UV_LOCAL_VENV_DIR}" || true
    sudo chown -R "${install_owner}" "${UV_LOCAL_VENV_DIR}" || true
    echo "Using local uv venv install path: ${VENV_INSTALL_PATH}"
  else
    echo "Using shared uv venv install path on local filesystem: ${VENV_INSTALL_PATH}"
  fi
}

# Generate the Python package set, including distro-specific Ansible constraints.
build_requirements_content() {
  local cupy_pkg="${1}"
  local content

  content=$(cat <<EOF_REQUIREMENTS
pip
oci-cli
oci
cryptography
netaddr
setuptools_rust
requests
urllib3
pyopenssl
psutil
distro
prometheus_client
watchdog
opentelemetry-sdk
opentelemetry-exporter-otlp
nvidia-ml-py
pyudev
clustershell
sqlalchemy
rich
click
ansible_runner
pymysql
cachetools
line-protocol-parser
influx-line-protocol
orjson

# --- Python build toolchain packages for Slurm SDK ---
packaging>=24.1
setuptools>=68
wheel>=0.41
build>=1.2.1

# --- Slurm SDK runtime dependencies ---
typing_extensions>=4.12.2
annotated_types>=0.6.0
typing-inspect>=0.4.0
pydantic>=2

# Silent Data Corruption checks
numpy
setuptools
wheel

# CuPy wheel
${cupy_pkg}

# Other packages
ujson
fastapi
uvicorn
EOF_REQUIREMENTS
)

  if [[ "${USING_OL8}" == "true" ]]; then
    content+=$'\n'"ansible-core==2.12.9"
    content+=$'\n'"ansible==5.10.0"
  else
    content+=$'\n'"ansible"
  fi

  printf '%s\n' "${content}"
}

# Persist the shared cache path into uv's environment file under a small lock.
record_shared_uv_cache_env() {
  local env_file="${UV_INSTALL_DIR}/env"
  local env_lock="${UV_INSTALL_DIR}/env.lockdir"
  local env_tmp="${env_file}.tmp.$$"

  if [[ ! -f "${env_file}" ]]; then
    return
  fi

  run_with_mkdir_lock "${env_lock}" "uv env update" 60 \
    bash -c 'grep -v "^export UV_CACHE_DIR=" "$1" > "$2" || true; printf "export UV_CACHE_DIR=\"%s\"\n" "$3" >> "$2"; mv "$2" "$1"' \
    _ "${env_file}" "${env_tmp}" "${UV_SHARED_CACHE_DIR}"
}

# Copy a locally built uv cache to the shared location for other nodes to reuse.
publish_uv_cache_to_shared() {
  local publish_tmp="${UV_SHARED_CACHE_DIR}.tmp.$(hostname).$$"

  if [[ -d "${UV_SHARED_CACHE_DIR}" ]]; then
    record_shared_uv_cache_env
    echo "Shared uv cache already exists; keeping existing cache: ${UV_SHARED_CACHE_DIR}"
    return
  fi

  rm -rf "${publish_tmp}"
  mkdir -p "${publish_tmp}"

  # Drop build/intermediate cache entries before copying the cache tree to NFS.
  uv cache prune --cache-dir "${UV_LOCAL_CACHE_DIR}" || true

  if ! rsync_copy "${UV_LOCAL_CACHE_DIR}" "${publish_tmp}" "uv cache"; then
    rm -rf "${publish_tmp}"
    echo "Failed to copy local uv cache to publish directory: ${publish_tmp}" >&2
    return 1
  fi

  sudo chown -R "${install_owner}" "${publish_tmp}" || true
  if mv "${publish_tmp}" "${UV_SHARED_CACHE_DIR}" 2>/dev/null; then
    record_shared_uv_cache_env
    echo "Published local uv cache to shared cache: ${UV_SHARED_CACHE_DIR}"
  elif [[ -d "${UV_SHARED_CACHE_DIR}" ]]; then
    rm -rf "${publish_tmp}"
    record_shared_uv_cache_env
    echo "Shared uv cache already exists; keeping existing cache: ${UV_SHARED_CACHE_DIR}"
  else
    rm -rf "${publish_tmp}"
    echo "Failed to publish local uv cache to shared cache: ${UV_SHARED_CACHE_DIR}" >&2
    return 1
  fi
}

# Copy a local file tree with a single rsync process.
rsync_copy() {
  local source_dir="${1}"
  local publish_tmp="${2}"
  local label="${3}"
  local t_start

  t_start=$(date +%s)

  if rsync -a "${source_dir}/" "${publish_tmp}/"; then
    echo "Moved ${label} in $(($(date +%s) - t_start))s"
    return 0
  fi

  echo "Failed to move ${label} after $(($(date +%s) - t_start))s" >&2
  return 1
}

# Split large file trees across parallel rsync processes to speed up publishing.
rsync_parallel_copy() {
  local source_dir="${1}"
  local publish_tmp="${2}"
  local label="${3}"
  local file_list_dir
  local file_list
  local rsync_pid
  local rsync_rc=0
  local copy_rc=0
  local -a rsync_pids=()
  local t_start

  file_list_dir=$(mktemp -d)
  t_start=$(date +%s)

  if (
    trap 'rm -rf "${file_list_dir}"' EXIT

    find "${source_dir}" \( -type f -o -type l \) -printf "%P\n" > "${file_list_dir}/files" || return 1
    split -n "l/${CACHE_COPY_JOBS}" "${file_list_dir}/files" "${file_list_dir}/files." || return 1

    for file_list in "${file_list_dir}"/files.*; do
      [[ -s "${file_list}" ]] || continue
      rsync -a --files-from="${file_list}" "${source_dir}" "${publish_tmp}" &
      rsync_pids+=("$!")
    done

    for rsync_pid in "${rsync_pids[@]}"; do
      if ! wait "${rsync_pid}"; then
        rsync_rc=1
      fi
    done

    return "${rsync_rc}"
  ); then
    copy_rc=0
  else
    copy_rc=$?
  fi

  if [[ "${copy_rc}" -eq 0 ]]; then
    echo "Moved ${label} in $(($(date +%s) - t_start))s"
  else
    echo "Failed to move ${label} after $(($(date +%s) - t_start))s" >&2
  fi
  return "${copy_rc}"
}

# Rewrite venv scripts from the local staging path to the final shared path.
rewrite_local_venv_paths() {
  local escaped_local
  local escaped_shared

  if [[ "${VENV_INSTALL_PATH}" == "${VENV_PATH}" ]]; then
    return
  fi

  escaped_local=$(printf '%s\n' "${VENV_INSTALL_PATH}" | sed 's/[\/&]/\\&/g')
  escaped_shared=$(printf '%s\n' "${VENV_PATH}" | sed 's/[\/&]/\\&/g')

  while IFS= read -r -d '' file; do
    if grep -Iq -- "${VENV_INSTALL_PATH}" "${file}"; then
      sed -i "s/${escaped_local}/${escaped_shared}/g" "${file}"
    fi
  done < <(find "${VENV_INSTALL_PATH}" -type f -print0)
}

# Publish a locally staged virtualenv atomically enough to recover on move failure.
publish_uv_venv_to_shared() {
  local publish_tmp="${VENV_PATH}.tmp.$(hostname).$$"
  local previous_path="${VENV_PATH}.previous.$(hostname).$$"
  local publish_owner

  if [[ "${install_venv_on_local_disk}" != true ]]; then
    return
  fi

  rm -rf "${publish_tmp}"
  rm -rf "${previous_path}"
  mkdir -p "${publish_tmp}"

  rewrite_local_venv_paths
  if ! rsync_parallel_copy "${VENV_INSTALL_PATH}" "${publish_tmp}" "uv venv"; then
    rm -rf "${publish_tmp}"
    echo "Failed to copy local uv venv to publish directory: ${publish_tmp}" >&2
    return 1
  fi

  publish_owner="$(stat -c '%U:%G' "${publish_tmp}" 2>/dev/null || true)"
  if [[ "${publish_owner}" != "${install_owner}" ]]; then
    echo "Fixing uv venv ownership before publish: ${publish_tmp}"
    sudo chown -R "${install_owner}" "${publish_tmp}" || true
  fi

  echo "Publishing uv venv to shared path: ${VENV_PATH}"
  if [[ -e "${VENV_PATH}" || -L "${VENV_PATH}" ]]; then
    echo "Moving previous uv venv aside: ${VENV_PATH}"
    mv "${VENV_PATH}" "${previous_path}"
  fi
  if mv "${publish_tmp}" "${VENV_PATH}"; then
    if [[ -e "${previous_path}" || -L "${previous_path}" ]]; then
      echo "Removing previous uv venv: ${previous_path}"
      rm -rf "${previous_path}"
    fi
  else
    if [[ -e "${previous_path}" || -L "${previous_path}" ]]; then
      mv "${previous_path}" "${VENV_PATH}"
    fi
    return 1
  fi
  echo "Published local uv venv to shared path: ${VENV_PATH}"
}

# Install uv if needed, create the requested Python/venv, and install requirements.
install_python_environment() {
  local proj_dir
  local requirements

  if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  source "${UV_INSTALL_DIR}/env"

  if [[ "${install_venv_on_local_disk}" == true ]]; then
    rm -rf "${VENV_INSTALL_PATH}"
  fi

  uv python install "${python_version}"
  uv venv --python "${python_version}" --relocatable "${VENV_INSTALL_PATH}"
  source "${VENV_INSTALL_PATH}/bin/activate"

  # Create a temporary directory to avoid littering the home directory.
  proj_dir=$(mktemp -d)
  (
    trap 'rm -rf "${proj_dir}"' EXIT
    requirements="${proj_dir}/requirements.txt"
    printf '%s\n' "${requirements_content}" > "${requirements}"

    echo "--- 8< --- Python Requirements: ${requirements} --- 8< ---"
    cat "${requirements}"
    echo "--- >8 --- Python Requirements --- >8 ---"

    # Run installation in temporary directory to pollute less.
    cd "${proj_dir}"
    uv pip install --link-mode=copy -r "${requirements}"
  )

  publish_uv_venv_to_shared
}

# Ensure future shells use the shared cache, publishing a local cache in the background.
finalize_uv_cache() {
  if [[ -d "${UV_SHARED_CACHE_DIR}" ]]; then
    export UV_CACHE_DIR="${UV_SHARED_CACHE_DIR}"
    record_shared_uv_cache_env
    echo "Using shared uv cache after install: ${UV_CACHE_DIR}"
  elif [[ "${publish_local_uv_cache}" == true && "${shared_uv_cache_on_mounted_fs}" == true ]]; then
    echo "Publishing local uv cache to shared cache in the background: ${UV_SHARED_CACHE_DIR}"
    (
      trap '' HUP
      trap - EXIT
      publish_uv_cache_to_shared
    ) </dev/null >> "${UV_INSTALL_DIR}/cache_publish.log" 2>&1 &
  fi
}

main() {
  local cupy_pkg
  local cuda_major=12
  local python_setup_hash

  if [[ "${ID}" == "ubuntu" ]]; then
    install_owner="ubuntu:ubuntu"
  else
    install_owner="opc:opc"
  fi
  sudo install -d -o "${install_owner%:*}" -g "${install_owner#*:}" "${UV_INSTALL_DIR}" "${UV_PYTHON_INSTALL_DIR}" || true

  # Choose cache and venv paths before hashing so install behavior matches the host.
  select_uv_cache
  select_venv_install_path

  # OL8 stays on older Python/Ansible support; newer images use the current default.
  if [[ "${USING_OL8}" == "true" ]]; then
    python_version="3.10"
  else
    python_version="3.12"
  fi

  if compgen -G "/usr/local/cuda-13*" >/dev/null; then
    cuda_major=13
  elif ! compgen -G "/usr/local/cuda-12*" >/dev/null; then
    echo "/usr/local/cuda not found. Defaulting to CUDA 12" >&2
  fi
  cupy_pkg="cupy-cuda${cuda_major}x"

  # The install marker changes whenever platform details or requirements change.
  requirements_content=$(build_requirements_content "${cupy_pkg}")
  python_setup_hash=$(printf '%s\n' \
    "id=${ID}" \
    "version_id=${VERSION_ID}" \
    "arch=${arch}" \
    "python_version=${python_version}" \
    "${requirements_content}" | sha256sum | awk '{print $1}')
  marker_install="${UV_INSTALL_DIR}/python_install_success.${python_setup_hash}"

  if [[ -f "${marker_install}" ]]; then
    echo "Python is already set up"
    exit 0
  fi

  # Only the node that acquires the lock performs the environment build.
  acquire_install_lock "Python environment" "${BOOTSTRAP_PYTHON_INSTALL_LOCK_TIMEOUT_SECONDS}"
  if [[ "${acquired}" != true ]]; then
    if [[ -f "${marker_install}" ]]; then
      echo "Python is already set up"
      exit 0
    fi

    echo "Python installation/setup in progress for >${BOOTSTRAP_PYTHON_INSTALL_LOCK_TIMEOUT_SECONDS}s"
    exit 1
  fi

  install_python_environment
  finalize_uv_cache

  # Mark this exact environment as installed and remove obsolete success markers.
  touch "${marker_install}"
  find "${UV_INSTALL_DIR}" -maxdepth 1 -type f -name 'python_install_success.*' ! -name "$(basename "${marker_install}")" -delete
}

main "$@"
