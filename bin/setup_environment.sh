source /etc/os-release

export ID
export VERSION
export VERSION_ID
export VERSION_MAJOR=$(echo "${VERSION}" | awk -F. '{print $1}')

if [[ ( "${ID}" == "ol" || "${ID}" == "centos" ) && "${VERSION_MAJOR}" == "8" ]]; then
  export USING_OL8=true
else
  export USING_OL8=false
fi

export UV_INSTALL_DIR="/config/venv/${ID^}_${VERSION_ID}_$(uname -m)"
export VENV_PATH="${UV_INSTALL_DIR}/oci"
