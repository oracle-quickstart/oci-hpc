#!/bin/bash

# Version 2.15.3. For roll back, uncomment below and comment out 2.15.5 to revert to old version
#LUSTRE_VERSION=2.15.3
#LUSTRE_PACKAGE_VERSION="${LUSTRE_VERSION}-1"
#LUSTRE_PACKAGES_OBJECT_STORE_URL=https://objectstorage.us-saltlake-2.oraclecloud.com/p/jcApbLrU34xHOdv-zVT34suRXCwvJswskv4gMIMTyE6Y2ExOshZ7NN_3k3h--u96/n/axsbohthbgkv/b/lustre-images/o/deb/${LUSTRE_VERSION}_dkms/client_base/
#LUSTRE_PKG_DIR="/tmp/lustre-${LUSTRE_PACKAGE_VERSION}-packages"

LUSTRE_VERSION=2.15.5
LUSTRE_PACKAGE_VERSION="${LUSTRE_VERSION}-oci0-12-gd3b2033-1"
#LUSTRE_PACKAGES_OBJECT_STORE_URL=https://objectstorage.us-saltlake-2.oraclecloud.com/p/fkbElfBAoUyHr_F1RqkSMc3dVQGMVs7nZNltqj8oewsSWeYefgAjFiDJcWM9WM4i/n/axehoqpdxwz4/b/packages/o/deb/${LUSTRE_VERSION}-12_dkms/client_base/
#LUSTRE_PACKAGES_OBJECT_STORE_URL=https://objectstorage.us-ashburn-1.oraclecloud.com/p/wM0DapEKogbt5Yqh2AResKhf_dJdVyqOrToPfoxE4vjWc1j8vis4DxUjyOEt9lkA/n/axehoqpdxwz4/b/packages-mirror/o/deb/${LUSTRE_VERSION}-12_dkms/client_base/
LUSTRE_PACKAGES_OBJECT_STORE_URL=https://objectstorage.eu-frankfurt-1.oraclecloud.com/p/_2UYvgPun0hQqMMNA0COppbWF7u5TUlHOJhJ7K-5kB7QZMoOGYc3IVPTdNHttXnm/n/fsssolutions/b/rclone-1/o/ubuntu-lustre-client/
LUSTRE_PKG_DIR="/tmp/lustre-${LUSTRE_PACKAGE_VERSION}-packages"

pkgs=(
    "lustre-client-modules-dkms_${LUSTRE_PACKAGE_VERSION}_amd64.deb"
    "lustre-client-utils_${LUSTRE_PACKAGE_VERSION}_amd64.deb"
)

# Log function for consistent logging
log() {
    echo "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ") - $1"
}
export SYSTEMCTL_FORCE_BUS=1

# Remove Lustre modules, wait for some time for the modules to be removed
#umount /mount/FSZETA0 2>/dev/null|| true
retry=0
while which lustre_rmmod  && ! lustre_rmmod && [ $retry -lt 10 ]
do
    log "Failed to unload Lustre modules, retry=$retry"
    sleep 30
    retry=$((retry+1))
done

if [ $retry -eq 10 ]; then
    log "Failed to unload Lustre modules after 5 minutes, this node likely require a reboot"
    exit 1
fi
log "Successfully unloaded Lustre modules, proceeding with Lustre client installation/upgrade"

log "Removing existing lustre packages"
apt-get remove --purge -y lustre-client-modules-dkms || true
apt-get remove --purge -y lustre-client-utils || true

#pre requisite for building lustre packages
log "Installing linux headers and images for the running kernel to make sure dependencies are met"
dpkg --configure -a
apt-get update --yes
apt-get install -y --no-upgrade linux-headers-$(uname -r)
apt-get install -y --no-upgrade linux-image-$(uname -r)
apt-get install -y --no-upgrade linux-base

#Make sure all the above pre-requisites are installed. Otherwise no point in continuing

dpkg --list | grep "linux-headers-$(uname -r) " || ( log "linux-headers-$(uname -r) is not installed. Exiting" && exit 1 )
dpkg --list | grep "linux-image-$(uname -r) " || (  log "linux-image-$(uname -r) is not installed. Exiting" && exit 1 )
dpkg --list | grep "linux-base " || ( log "linux-base is not installed. Exiting" && exit 1 )

# Array to hold packages that are not installed
not_installed_pkgs=()
for package in "${pkgs[@]}"; do
    log "Checking $package installation on system."
    package_to_query="${package//_${LUSTRE_PACKAGE_VERSION}_amd64.deb/}"
    if dpkg -s "$package_to_query" | grep "install ok installed" &> /dev/null; then
        log "Package $package is already installed."
    else
        log "Package $package is not currently installed."
        not_installed_pkgs+=("$package")
    fi
done

# If there are any packages not installed
if [ ${#not_installed_pkgs[@]} -ne 0 ]; then
    mkdir -p $LUSTRE_PKG_DIR
    cd $LUSTRE_PKG_DIR
    pwd
    log "Downloading and installing missing packages..."
    if ! printf '%s\n' "${not_installed_pkgs[@]}" | xargs -I{} -P8 curl -O "${LUSTRE_PACKAGES_OBJECT_STORE_URL}{}"; then
        log "Failed to download one or more packages."
        exit 1
    fi

    # Install all dependencies prior
    log "Installing depencies seperately to avoid auto install of new kernel versions"
    for pkg in $(ls *.deb)
    do
        apt-get install -y $(dpkg -I  $pkg | grep "^ Depends: " | sed -E -e 's/,/ /g' -e 's/(linux-base|linux-image-oracle|linux-image-oracle-amd64|linux-image-oracle-arm64|linux-headers-oracle|linux-headers-amd64)//g' -e 's/[,\|]//g'  -e 's/ +/ /g' | cut -f2 -d:)
    done

    log "Now installing Lustre packages alone without dependencies"
    if ! (apt-get update --yes && dpkg --ignore-depends=linux-image-oracle,linux-headers-oracle,linux-headers-amd64,inux-image-oracle-amd64,linux-image-oracle-arm64,linux-headers-oracle,linux-headers-amd64 -i ./*.deb && rm -f ./*.deb) then
        log "Failed to install one or more packages."
        exit 1
    fi
    log "Packages installed successfully."
else
    log "All required packages are already installed."
fi

# Try to load kernel module, to verify kernel module
if ! (modprobe lnet) then
    log "Failed to load kernel module"
    exit 1
else
    log "Module load test successful. Lustre client ready"
fi
exit 0
