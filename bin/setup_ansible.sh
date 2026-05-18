# Configure Ansible for the cluster bootstrap.
#
# Executed every time:
# - load the uv-managed virtualenv from ${VENV_PATH}
# - regenerate /etc/ansible/ansible.cfg for the current host/user
#
# Executed once per requirements hash across the cluster:
# - install the required Ansible collections into /config/playbooks/collections
# - coordinate the install with /config/playbooks/ansible_install_in_progress lock file
# - record completion with /config/playbooks/ansible_install_success.<hash>
#
# The Ansible hash is computed from the generated Ansible collection requirements content

set -Eeuo pipefail
source "$(dirname "${0}")/common.sh"
setup_bootstrap_error_trap "setup_ansible.sh"

: "${BOOTSTRAP_ANSIBLE_GALAXY_TIMEOUT_SECONDS:=900}"
: "${BOOTSTRAP_ANSIBLE_CFG_TIMEOUT_SECONDS:=120}"
: "${BOOTSTRAP_ANSIBLE_CFG_RETRIES:=3}"
readonly BOOTSTRAP_ANSIBLE_GALAXY_TIMEOUT_SECONDS
readonly BOOTSTRAP_ANSIBLE_CFG_TIMEOUT_SECONDS
readonly BOOTSTRAP_ANSIBLE_CFG_RETRIES

acquired=false
ansible_requirements=""
GIT_CONFIG_GLOBAL=""
marker_in_progress=""

# Remove temporary files and release the collection install lock on exit.
cleanup_setup_ansible() {
  if [[ -n "${ansible_requirements}" && -f "${ansible_requirements}" ]]; then
    rm -f "${ansible_requirements}"
  fi

  if [[ -n "${GIT_CONFIG_GLOBAL}" && -f "${GIT_CONFIG_GLOBAL}" ]]; then
    rm -f "${GIT_CONFIG_GLOBAL}"
  fi

  if [[ "${acquired}" == true && -n "${marker_in_progress}" && -d "${marker_in_progress}" ]]; then
    rm -rf "${marker_in_progress}"
  fi
}

trap 'rc=$?; cleanup_setup_ansible; _bootstrap_log_exit "$rc"' EXIT

# Load the uv-managed Python environment that provides ansible and ansible-galaxy.
echo "Starting setup_ansible.sh on host=$(hostname 2>/dev/null || echo unknown) user=$(id -un 2>/dev/null || echo unknown)"
echo "Sourcing UV environment from ${UV_INSTALL_DIR}/env"
source "${UV_INSTALL_DIR}/env"
echo "Activating virtualenv from ${VENV_PATH}/bin/activate"
source "${VENV_PATH}/bin/activate"
echo "Virtualenv activated; ansible=$(command -v ansible 2>/dev/null || echo missing) ansible-galaxy=$(command -v ansible-galaxy 2>/dev/null || echo missing)"

arch=$(uname -m)

# Scale Ansible forks with CPU count but cap concurrency to avoid overload.
threads=$(nproc)
forks=$(( threads * 8 ))
(( forks > 256 )) && forks=256
echo "Detected arch=${arch} threads=${threads} forks=${forks} ID=${ID:-unknown}"

if [[ "${ID}" == "ubuntu" ]]; then
  ansible_owner="ubuntu:ubuntu"
  ansible_user_home="/home/ubuntu"
else
  ansible_owner="opc:opc"
  ansible_user_home="/home/opc"
fi
echo "Using ansible_owner=${ansible_owner} ansible_user_home=${ansible_user_home}"

configure_ansible_cfg() {
  local ansible_collections_path
  ansible_collections_path="/config/playbooks/collections:${ansible_user_home}/.ansible/collections:/usr/share/ansible/collections"
  echo "Configuring /etc/ansible/ansible.cfg with collections_path=${ansible_collections_path}"

  if [[ ! -d /etc/ansible ]]; then
    sudo mkdir /etc/ansible
    sudo chown "${ansible_owner}" /etc/ansible
  fi

  # Build an Ansible config tuned for this bootstrap environment.
  echo "Generating base ansible.cfg via ansible-config"
  "${VENV_PATH}/bin/ansible-config" init --disabled -t all | sudo tee /etc/ansible/ansible.cfg > /dev/null
  sudo sed -i "s/^\(#\|;\)forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
  sudo sed -i "s/^\(#\|;\)fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
  sudo sed -i "0,/^\(#\|;\)fact_caching_connection.*/s//fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
  sudo sed -i "s/^\(#\|;\)bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
  sudo sed -i "s/^\(#\|;\)retries.*/retries=5/" /etc/ansible/ansible.cfg
  sudo sed -i "s/^\(#\|;\)connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
  sudo sed -i "s/^\(#\|;\)command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg
  sudo sed -i "/^\[defaults\]/,/^\[/ s/^[#;]remote_tmp.*/remote_tmp=\/tmp\/.ansible-tmp/" /etc/ansible/ansible.cfg
  sudo sed -i "/^\[defaults\]/,/^\[/ s|^[#;]collections_path=.*|collections_path=${ansible_collections_path}|" /etc/ansible/ansible.cfg

  # Ensure the remote temp directory exists and is usable for any user (including become: true tasks)
  sudo mkdir -p /tmp/.ansible-tmp
  sudo chmod 1777 /tmp/.ansible-tmp

  # Replace the legacy yaml callback with the built-in default and enable YAML output
  sudo sed -i 's/^\([#;]\s*\)\?stdout_callback.*/stdout_callback = default/' /etc/ansible/ansible.cfg
  # Ensure the default callback outputs YAML (append the section if not present)
  if ! sudo grep -q '^\[callback_default\]' /etc/ansible/ansible.cfg; then
    sudo tee -a /etc/ansible/ansible.cfg >/dev/null <<'EOF'
[callback_default]
result_format = yaml
EOF
  else
    # Make sure result_format=yaml is set under [callback_default]
    sudo sed -i '/^\[callback_default\]/,/^\[/{s/^\([#;]\s*\)\?result_format.*/result_format = yaml/}' /etc/ansible/ansible.cfg
  fi
  echo "Finished configuring ansible.cfg"
}

configure_ansible_cfg_with_timeout() {
  local rc

  export VENV_PATH ansible_user_home forks ansible_owner
  export -f configure_ansible_cfg

  if timeout --kill-after=300s "${BOOTSTRAP_ANSIBLE_CFG_TIMEOUT_SECONDS}s" bash -c 'configure_ansible_cfg'; then
    return 0
  fi

  rc=$?
  case "${rc}" in
    124)
      echo "configure_ansible_cfg timed out after ${BOOTSTRAP_ANSIBLE_CFG_TIMEOUT_SECONDS}s"
      ;;
    137)
      echo "configure_ansible_cfg was killed after timeout grace period"
      ;;
    *)
      echo "configure_ansible_cfg failed rc=${rc}"
      ;;
  esac

  return "${rc}"
}

run_with_retry "${BOOTSTRAP_ANSIBLE_CFG_RETRIES}" 2 "configure_ansible_cfg" configure_ansible_cfg_with_timeout
echo "Ansible config phase complete"

# Shared markers let all nodes reuse a collection install performed by one node.
marker_in_progress="/config/playbooks/ansible_install_in_progress"
marker_in_progress_hostname="${marker_in_progress}/hostname"
echo "Using lock marker=${marker_in_progress} success marker prefix=/config/playbooks/ansible_install_success"

if [[ "${USING_OL8}" == "true" ]]; then
  echo "Preparing OL8 Ansible collection requirements"
  ansible_requirements_content=$(cat <<'EOF_ANSIBLE_OL8'
---
collections:
  - name: community.general
    version: "<10"
  - name: oracle.oci
    src: git+https://github.com/oracle/oci-ansible-collection.git
EOF_ANSIBLE_OL8
)
else
  echo "Preparing default Ansible collection requirements"
  ansible_requirements_content=$(cat <<'EOF_ANSIBLE'
---
collections:
  - name: community.general
  - name: ansible.netcommon
  - name: ansible.posix
  - name: community.crypto
  - name: ansible.utils
  - name: oracle.oci
EOF_ANSIBLE
)
fi

# The success marker is tied to the requirements content so collection changes reinstall.
ansible_setup_hash=$(printf '%s\n' "${ansible_requirements_content}" | sha256sum | awk '{print $1}')
marker_install="/config/playbooks/ansible_install_success.${ansible_setup_hash}"
echo "Computed ansible_setup_hash=${ansible_setup_hash} marker_install=${marker_install}"

acquire_install_lock "Ansible collections" "${BOOTSTRAP_ANSIBLE_INSTALL_LOCK_TIMEOUT_SECONDS}"

if [[ "${acquired}" == true ]]; then
  # This node owns the install, so materialize requirements and run ansible-galaxy.
  echo "Beginning Ansible collection installation"
  GIT_CONFIG_GLOBAL="$(mktemp)"
  export GIT_CONFIG_GLOBAL
  ansible_requirements=$(mktemp)
  echo "Created temp files GIT_CONFIG_GLOBAL=${GIT_CONFIG_GLOBAL} ansible_requirements=${ansible_requirements}"
  printf '%s\n' "${ansible_requirements_content}" > "${ansible_requirements}"
  echo "Wrote Ansible requirements to ${ansible_requirements}"

  echo "Configuring git core.quiet=true"
  git config --global core.quiet true

  if timeout --kill-after=60s "${BOOTSTRAP_ANSIBLE_GALAXY_TIMEOUT_SECONDS}s" \
      ansible-galaxy collection install \
        -r "${ansible_requirements}" \
        -p /config/playbooks/collections; then
    echo "Ansible galaxy collection install complete."
  else
    galaxy_rc=$?
    case "${galaxy_rc}" in
      124)
        echo "Ansible galaxy collection install timed out"
        ;;
      137)
        echo "Ansible galaxy collection install was killed after timeout grace period"
        ;;
      *)
        echo "Ansible galaxy collection install failed rc=${galaxy_rc}"
        ;;
    esac
    exit "${galaxy_rc}"
  fi

elif [[ -f "${marker_install}" ]]; then
  echo "Success marker present after wait; no install needed"
else
  echo "Ansible installation/setup in progress for >${BOOTSTRAP_ANSIBLE_INSTALL_LOCK_TIMEOUT_SECONDS}s; lock holder=$(cat "${marker_in_progress_hostname}" 2>/dev/null || echo unknown)"
  exit 1
fi

if [[ "${acquired}" == true ]]; then
  # Publish the success marker and prune stale markers from previous requirements.
  echo "Writing success marker ${marker_install}"
  touch "${marker_install}"
  echo "Removing stale Ansible collection success markers"
  find /config/playbooks -maxdepth 1 -type f -name "ansible_install_success.*" ! -name "$(basename "${marker_install}")" -delete
fi

echo "setup_ansible.sh complete"
