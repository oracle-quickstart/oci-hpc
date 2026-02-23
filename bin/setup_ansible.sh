source "${UV_INSTALL_DIR}/env"
source "${VENV_PATH}/bin/activate"


# Check if another node is already installing the required Ansible collections.
# 
# If not, do it ourselves.
# If yes, wait for 1200s. Then use the install or (if failed, try to install ourselves).
marker_install="${UV_INSTALL_DIR}/ansible_install_success"
marker_in_progress="${UV_INSTALL_DIR}/ansible_install_in_progress"

# SECONDS is a bash built-in, counts seconds since invocation
timeout=$(( SECONDS + 1200 ))
while (( SECONDS < timeout )); do
  if [[ ! -f "${marker_in_progress}" ]]; then
    break
  fi
  sleep 30
done

if [[ -f "${marker_in_progress}" ]]; then
  echo "Ansible installation/setup in progress for >1200s"
  exit 1
elif [[ -f "${marker_install}" ]]; then
  echo "Ansible already installed and set up"
else
  trap 'rm -f "${marker_in_progress}"' EXIT
  touch "${marker_in_progress}"

  export GIT_CONFIG_GLOBAL=$(mktemp)
  git config --global core.quiet true

  ansible_requirements=$(mktemp)

  if [[ "${USING_OL8}" == "true" ]]; then
    export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
    export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
    # Required for copr's includepkg attribute (monitoring uses it to install grafana)
    # This includepkg is present from 10.0.0+. Version 12 dropped support for
    # Python <3.7, the version of ansible (2.12) requires a bit older for full support.
    cat <<EOF_ANSIBLE_OL8 > "${ansible_requirements}"
---
collections:
  - name: community.general
    version: "<10"
  - name: oracle.oci
    src: git+https://github.com/oracle/oci-ansible-collection.git
EOF_ANSIBLE_OL8
  else
    cat <<EOF_ANSIBLE > "${ansible_requirements}"
---
collections:
  - name: community.general
  - name: ansible.netcommon
  - name: ansible.posix
  - name: community.crypto
  - name: ansible.utils
  - name: oracle.oci
EOF_ANSIBLE
  fi

  uv run ansible-galaxy collection install --upgrade --force -r "${ansible_requirements}"

  touch "${marker_install}"
fi

threads=$(nproc)
forks=$(($threads * 8))

if [ ! -d /etc/ansible ] ; then
  sudo mkdir /etc/ansible
  if [ $ID == "ubuntu" ] ; then
    sudo chown ubuntu:ubuntu /etc/ansible
  else
    sudo chown opc:opc /etc/ansible
  fi
fi

uv run ansible-config init --disabled -t all | sudo tee /etc/ansible/ansible.cfg > /dev/null
sudo sed -i "s/^\(#\|;\)forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
sudo sed -i "0,/^\(#\|;\)fact_caching_connection.*/s//fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)retries.*/retries=5/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg
sudo sed -i "/^\[defaults\]/,/^\[/ s/^\(#\|;\)remote_tmp.*/remote_tmp=\/tmp\/.ansible-tmp/" /etc/ansible/ansible.cfg

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
