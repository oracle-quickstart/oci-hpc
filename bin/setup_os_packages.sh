# Install baseline operating system packages for supported images, including
# apt/dnf setup work and OCI CLI installation where needed.
set -eu -o pipefail
source "$(dirname "${0}")/common.sh"

# Silence progress bars and wait briefly on dpkg frontend locks.
apt_options=(-q -o Dpkg::Progress-Fancy=0 -o APT::Color=0 -o Dpkg::Use-Pty=0 -o DPkg::Lock::Timeout=60)
export PIP_PROGRESS_BAR=off

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

  local latest_ver
  latest_ver=$(curl -sSf -L --retry 3 --retry-delay 5 \
    https://api.github.com/repos/oracle/oci-cli/releases/latest | jq -r '.name' 2>/dev/null)

  local max_attempts=5
  local attempt=0
  local success=false

  while (( attempt < max_attempts )); do
    attempt=$((attempt + 1))
    echo "OCI CLI install attempt ${attempt} of ${max_attempts}..."

    if [[ -z "${latest_ver}" || "${latest_ver}" == "null" ]]; then
      echo "Warning: Could not determine version. Falling back to default installation..."
      if bash -c "$(curl -L --retry 3 --retry-delay 5 https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" \
           -s --accept-all-defaults --install-dir /opt/oci-cli 2>&1; then
        success=true
        break
      fi
    else
      echo "Installing OCI CLI version: ${latest_ver}"
      if bash -c "$(curl -L --retry 3 --retry-delay 5 https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" \
           -s --accept-all-defaults --install-dir /opt/oci-cli --oci-cli-version "${latest_ver}" 2>&1; then
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
    os_package_list="python3 python3-pip openjdk-11-jre-headless rsync git jq"
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
