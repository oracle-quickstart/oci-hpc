# Install baseline operating system packages for supported images, including
# apt/dnf setup work and OCI CLI installation where needed.
set -eu -o pipefail
source "$(dirname "${0}")/common.sh"

configure_hpc_apt_acquire

# Silence progress bars and wait briefly on dpkg frontend locks.
apt_options=(-q -o Dpkg::Progress-Fancy=0 -o APT::Color=0 -o Dpkg::Use-Pty=0 -o DPkg::Lock::Timeout=120)
export PIP_PROGRESS_BAR=off

arch="$(uname -m)"
readonly OCI_CLI_CACHE_DIR="/config/3rdparty/${arch}/oci-cli"
readonly OCI_CLI_VERSION_FILE="${OCI_CLI_CACHE_DIR}/latest_version"
readonly OCI_CLI_INSTALLER_FILE="${OCI_CLI_CACHE_DIR}/install.sh"
readonly OCI_CLI_LOCK_DIR="${OCI_CLI_CACHE_DIR}/cache.lock"
readonly OCI_CLI_CACHE_MAX_AGE_SECONDS=86400
readonly OCI_CLI_VERSION_URL="https://api.github.com/repos/oracle/oci-cli/releases/latest"
readonly OCI_CLI_INSTALLER_URL="https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh"

run_apt_command_after_wait() {
  # Wait for package-manager locks left by cloud-init, unattended upgrades, or apt timers.
  while sudo fuser /var/{lib/{dpkg/{lock,lock-frontend},apt/lists/lock},cache/apt/archives/lock} >/dev/null 2>&1; do
    echo "Waiting for dpkg/apt lock"
    sleep 2
  done
  "$@"
}

# Run apt commands through lock waits and retries for first-boot package races.
run_apt_with_retry() {
  local max_attempts="${1}"
  shift

  run_with_retry "${max_attempts}" 5 "APT command" run_apt_command_after_wait "$@"
}

# Check optional package names that vary between distro releases.
apt_package_has_candidate() {
  local package_name="${1}"
  local candidate

  candidate=$(apt-cache policy "${package_name}" 2>/dev/null | awk '/Candidate:/ {print $2; exit}')
  [[ -n "${candidate}" && "${candidate}" != "(none)" ]]
}

ensure_oci_cli_cache_dir() {
  sudo install -o "$(id -u)" -g "$(id -g)" -m 0755 -d \
    "$(dirname "${OCI_CLI_CACHE_DIR}")" \
    "${OCI_CLI_CACHE_DIR}"
}
cache_file_is_fresh() {
  local cache_file="${1}"
  local max_age_seconds="${2}"
  local mtime
  local now

  [[ -s "${cache_file}" ]] || return 1

  if ! mtime=$(stat -c %Y "${cache_file}" 2>/dev/null); then
    return 1
  fi

  now=$(date +%s)
  (( now - mtime < max_age_seconds ))
}

read_cached_oci_cli_version() {
  local latest_ver=""

  if [[ -s "${OCI_CLI_VERSION_FILE}" ]]; then
    latest_ver=$(sed -n '1p' "${OCI_CLI_VERSION_FILE}" 2>/dev/null || true)
    latest_ver="${latest_ver//[[:space:]]/}"
  fi
  if [[ "${latest_ver}" == "null" ]]; then
    latest_ver=""
  fi

  printf '%s\n' "${latest_ver}"
}

write_oci_cli_version_cache() {
  local latest_ver="${1}"
  local tmp_file="${OCI_CLI_VERSION_FILE}.tmp.$(hostname).$$"

  printf '%s\n' "${latest_ver}" > "${tmp_file}"
  chmod 0644 "${tmp_file}" 2>/dev/null || true
  mv "${tmp_file}" "${OCI_CLI_VERSION_FILE}"
}

refresh_oci_cli_version_cache() {
  local latest_ver=""
  local cached_ver=""

  if cache_file_is_fresh "${OCI_CLI_VERSION_FILE}" "${OCI_CLI_CACHE_MAX_AGE_SECONDS}"; then
    cached_ver=$(read_cached_oci_cli_version)
    echo "Using cached OCI CLI latest version: ${cached_ver}"
    return 0
  fi

  echo "Refreshing OCI CLI latest version cache: ${OCI_CLI_VERSION_FILE}"
  if latest_ver=$(curl -sSf -L --retry 3 --retry-delay 5 "${OCI_CLI_VERSION_URL}" 2>/dev/null | jq -r '.name // empty' 2>/dev/null) \
    && [[ -n "${latest_ver}" && "${latest_ver}" != "null" ]]; then
    write_oci_cli_version_cache "${latest_ver}"
    echo "Cached OCI CLI latest version: ${latest_ver}"
    return 0
  fi

  cached_ver=$(read_cached_oci_cli_version)
  if [[ -n "${cached_ver}" ]]; then
    echo "Warning: Could not refresh OCI CLI latest version. Reusing cached version: ${cached_ver}"
    return 0
  fi

  echo "Warning: Could not determine OCI CLI version. Falling back to default installation."
}

refresh_oci_cli_installer_cache() {
  local tmp_file="${OCI_CLI_INSTALLER_FILE}.tmp.$(hostname).$$"

  if cache_file_is_fresh "${OCI_CLI_INSTALLER_FILE}" "${OCI_CLI_CACHE_MAX_AGE_SECONDS}"; then
    echo "Using cached OCI CLI installer: ${OCI_CLI_INSTALLER_FILE}"
    return 0
  fi

  echo "Refreshing OCI CLI installer cache: ${OCI_CLI_INSTALLER_FILE}"
  if curl -fsSL --retry 3 --retry-delay 5 "${OCI_CLI_INSTALLER_URL}" -o "${tmp_file}"; then
    chmod 0644 "${tmp_file}" 2>/dev/null || true
    mv "${tmp_file}" "${OCI_CLI_INSTALLER_FILE}"
    return 0
  fi

  rm -f "${tmp_file}"
  if [[ -s "${OCI_CLI_INSTALLER_FILE}" ]]; then
    echo "Warning: Could not refresh OCI CLI installer. Reusing cached installer."
    return 0
  fi

  echo "Warning: Could not cache OCI CLI installer. The install step will download it directly."
}

refresh_oci_cli_cache_if_needed() {
  ensure_oci_cli_cache_dir
  refresh_oci_cli_version_cache
  refresh_oci_cli_installer_cache
}

get_oci_cli_install_script() {
  if [[ -s "${OCI_CLI_INSTALLER_FILE}" ]]; then
    cat "${OCI_CLI_INSTALLER_FILE}"
    return
  fi

  curl -fsSL --retry 3 --retry-delay 5 "${OCI_CLI_INSTALLER_URL}"
}

# Disable unattended apt jobs so bootstrap package installs remain deterministic.
disable_unattended_upgrades() {
  export DEBIAN_FRONTEND=noninteractive

  if [[ -f /etc/apt/apt.conf.d/20auto-upgrades ]]; then
    sudo sed -i 's/"1"/"0"/g' /etc/apt/apt.conf.d/20auto-upgrades
  fi

  run_apt_with_retry 5 sudo apt-get "${apt_options[@]}" purge -y --auto-remove unattended-upgrades

  for unit in apt-daily-upgrade.timer apt-daily-upgrade.service apt-daily.timer apt-daily.service apt-news.timer apt-news.service; do
    if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
      sudo systemctl disable --now "$unit" 2>/dev/null || true
      sudo systemctl mask "$unit" 2>/dev/null || true
    fi
  done
}

# Install the latest OCI CLI release with retries, falling back if version lookup fails.
install_oci_cli() {
  cd /tmp

  ensure_oci_cli_cache_dir
  if ! run_with_mkdir_lock "${OCI_CLI_LOCK_DIR}" "OCI CLI cache" 300 refresh_oci_cli_cache_if_needed; then
    echo "Warning: OCI CLI cache refresh did not complete before timeout. Reusing any existing cache."
  fi

  local latest_ver
  local max_attempts=5
  local attempt=0
  local success=false
  local install_script

  latest_ver=$(read_cached_oci_cli_version)

  while (( attempt < max_attempts )); do
    attempt=$((attempt + 1))
    echo "OCI CLI install attempt ${attempt} of ${max_attempts}..."

    if ! install_script=$(get_oci_cli_install_script); then
      echo "Failed to download OCI CLI installer on attempt ${attempt}."
    elif [[ -z "${latest_ver}" ]]; then
      if bash -c "${install_script}" -s --accept-all-defaults --install-dir /opt/oci-cli 2>&1; then
        success=true
        break
      fi
    else
      echo "Installing OCI CLI version: ${latest_ver}"
      if bash -c "${install_script}" -s --accept-all-defaults --install-dir /opt/oci-cli --oci-cli-version "${latest_ver}" 2>&1; then
        success=true
        break
      fi
    fi

    echo "Installation failed on attempt ${attempt}."
    if (( attempt < max_attempts )); then
      echo "Sleeping for 10 seconds before retrying..."
      sleep 10
    fi
  done

  if [[ "${success}" != "true" ]]; then
    echo "Error: OCI CLI installation failed after ${max_attempts} attempts."
    exit 1
  fi
  echo "OCI CLI installed successfully!"
}

# Prepare the shared /opt area for bootstrap tools and generated content.
sudo mkdir -p /opt/oci-hpc

if [[ "${ID}" == "ubuntu" ]]; then
  sudo chown -R ubuntu:ubuntu /opt/
else
  sudo chown -R opc:opc /opt/
fi

# Select package names and repository behavior for the detected OS family.
case "$ID" in
  ol)
    case "$VERSION_MAJOR" in
      8) repo="ol8_developer_EPEL" ;;
      9) repo="ol9_developer_EPEL" ;;
      *) repo="" ;;
    esac
    os_package_list="python3 python3-pip python3-dnf java-11-openjdk-headless http-parser rsync git jq"
    ;;
  debian|ubuntu)
    repo=""
    os_package_list="python3 python3-pip python3-debian openjdk-11-jre-headless rsync git jq"
    optional_os_package_list="libhttp-parser2.9 libhttp-parser2.10"
    ;;
  *)
    repo=""
    os_package_list="unsupported-os"
    ;;
esac

# Install OS packages using the native package manager.
case "$ID" in
  ol)
    if [[ "${VERSION_MAJOR}" == "8" ]]; then
      # OL8 images may still be registered with OSMS, which can block dnf repository use.
      if command -v osms >/dev/null 2>&1; then
        sudo osms unregister
      fi
      sudo dnf makecache --enablerepo="$repo"
    fi
    sudo dnf install -y ${os_package_list}
    ;;

  debian|ubuntu)
    # Prevent background apt activity and keep Oracle kernel packages unchanged.
    disable_unattended_upgrades

    sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle || true

    run_apt_with_retry 5 sudo apt-get "${apt_options[@]}" -y --fix-broken install

    # Avoid interactive service restart prompts during noninteractive package installs.
    if [[ -f /etc/needrestart/needrestart.conf ]]; then
      sudo sed -i "s/#\\\$nrconf{restart} = 'i';/\\\$nrconf{restart} = 'a';/g" /etc/needrestart/needrestart.conf
    fi

    run_apt_with_retry 5 sudo apt-get "${apt_options[@]}" update

    for optional_package in ${optional_os_package_list:-}; do
      if apt_package_has_candidate "${optional_package}"; then
        os_package_list="${os_package_list} ${optional_package}"
        break
      fi
    done

    if ! run_apt_with_retry 5 sudo apt-get "${apt_options[@]}" -y install ${os_package_list}; then
      echo "Error: Package installation failed after 5 attempts."
      exit 1
    fi

    # Debian-family images install OCI CLI through Oracle's GitHub installer.
    install_oci_cli
    ;;

  *)
    ;;
esac
