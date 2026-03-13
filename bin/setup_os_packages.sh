# Silence progress bars
apt_options='-q -o Dpkg::Progress-Fancy="0" -o APT::Color="0" -o Dpkg::Use-Pty="0"'
export PIP_PROGRESS_BAR=off

if [ ! -d /opt/oci-hpc ] ; then
  sudo mkdir /opt/oci-hpc
fi   
if [ $ID == "ubuntu" ] ; then
  sudo chown -R ubuntu:ubuntu /opt/
else
  sudo chown -R opc:opc /opt/
fi

if [ $ID == "ol" ] ; then
  if [[ "${VERSION_MAJOR}" == "8" ]]; then
    repo="ol8_developer_EPEL"
    if command -v osms >/dev/null 2>&1; then
      sudo osms unregister 
    fi
  elif [[ "${VERSION_MAJOR}" == "9" ]]; then
    repo="ol9_developer_EPEL"
  fi
elif [ $ID == "centos" ] ; then
  repo="epel"
fi

# Install ansible and other required packages
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then 
  if [[ "${VERSION_MAJOR}" == "8" ]]; then
    sudo dnf makecache --enablerepo=$repo
  fi
  sudo dnf install -y python3 python3-pip python3-dnf java-11-openjdk-headless http-parser

elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then 
  # checking here as well to be sure that the lock file is not being held
  function fix_apt {
    apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
    apt_process=$(( apt_process -1 ))
    while [ $apt_process -ge 1 ]
      do
        echo "wait until apt update is done"
        sleep 10s
        ps aux | grep "apt update" | grep -v grep
        apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
        apt_process=$(( apt_process -1 ))
      done
  }
  fix_apt

  export DEBIAN_FRONTEND=noninteractive

  if [ $ID == "debian" ] && [ $VERSION_ID == "9" ] ; then 
    echo deb http://ppa.launchpad.net/ansible/ansible/ubuntu trusty main | sudo tee -a /etc/apt/sources.list
    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 93C4A3FD7BB9C367
  fi 

  sudo sed -i 's/"1"/"0"/g' /etc/apt/apt.conf.d/20auto-upgrades
  sudo apt ${apt_options} purge -y --auto-remove unattended-upgrades
  sudo systemctl stop apt-daily-upgrade.timer
  sudo systemctl disable apt-daily-upgrade.timer
  sudo systemctl mask apt-daily-upgrade.service
  sudo systemctl stop apt-daily.timer
  sudo systemctl disable apt-daily.timer
  sudo systemctl mask apt-daily.service

  sleep 10s

  sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle

  fix_apt
  sleep 10s
  sudo apt ${apt_options} -y --fix-broken install

  fix_apt
  sudo apt ${apt_options} update
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    sudo apt-get ${apt_options} -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  else
    sudo sed -i 's/#$nrconf{restart} = '"'"'i'"'"';/$nrconf{restart} = '"'"'a'"'"';/g' /etc/needrestart/needrestart.conf
    apt_success=1
    while [ $apt_success -ge 1 ]
      do
        echo "wait until apt update is done"
        sleep 10s
        sudo apt-get ${apt_options} -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
        apt_success=$?
        echo $apt_success
      done
  fi
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    fix_apt
    sudo apt-get ${apt_options} -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  elif [ $ID == "ubuntu" ] && [ $VERSION_ID == "22.04" ] ; then
    fix_apt
    sudo apt-get ${apt_options} -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  else
    fix_apt
    sudo apt-get ${apt_options} -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  fi
  # install oci-cli (add --oci-cli-version 3.23.3 or version that you know works if the latest does not work ) 
  cd /tmp
  LATEST_OCICLI=$(curl -s -L https://api.github.com/repos/oracle/oci-cli/releases/latest | jq -r '.name' 2>/dev/null)

  MAX_RETRIES=5
  RETRY_COUNT=0
  SUCCESS=false

  while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
      ((RETRY_COUNT++))
      echo "Attempt $RETRY_COUNT of $MAX_RETRIES..."

      # Check if the variable is empty or literal "null"
      if [ -z "$LATEST_OCICLI" ] || [ "$LATEST_OCICLI" == "null" ]; then
          echo "Warning: Could not determine version. Falling back to default installation..."
          INSTALL_CMD="bash -c \"\$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)\" -s --accept-all-defaults --install-dir /opt/oci-cli"
      else
          echo "Installing OCI CLI version: $LATEST_OCICLI"
          INSTALL_CMD="bash -c \"\$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)\" -s --accept-all-defaults --install-dir /opt/oci-cli --oci-cli-version \"$LATEST_OCICLI\""
      fi

      # Execute the command
      if eval "$INSTALL_CMD" 2>&1; then
          echo "OCI CLI installed successfully!"
          SUCCESS=true
          break
      else
          echo "Installation failed on attempt $RETRY_COUNT."
          if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
              echo "Sleeping for 30 seconds before retrying..."
              sleep 30
          fi
      fi
  done

  if [ "$SUCCESS" = false ]; then
      echo "Error: OCI CLI installation failed after $MAX_RETRIES attempts."
      exit 1
  fi
fi 
