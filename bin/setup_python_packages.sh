set -o errexit
set -o pipefail
set -o nounset

if [[ -z "${UV_INSTALL_DIR:+valid}" ]]; then
  echo "${0} needs to have the environment variable UV_INSTALL_DIR defined"
  exit 1
elif [[ -z "${VENV_PATH:+valid}" ]]; then
  echo "${0} needs to have the environment variable VENV_PATH defined"
  exit 1
fi

# Check if another node is already installing the environment.
# 
# If not, do it ourselves.
# If yes, wait for 1200s. Then use the install or (if failed, try to install ourselves).
marker_install="${UV_INSTALL_DIR}/python_install_success"
marker_in_progress="${UV_INSTALL_DIR}/python_install_in_progress"

# SECONDS is a bash built-in, counts seconds since invocation
timeout=$(( SECONDS + 1200 ))
while (( SECONDS < timeout )); do
  if [[ ! -f "${marker_in_progress}" ]]; then
    break
  fi
  sleep 30
done

if [[ -f "${marker_in_progress}" ]]; then
  echo "Python installation/setup in progress for >1200s"
  exit 1
elif [[ -f "${marker_install}" ]]; then
  echo "Python already installed and set up"
  exit 0
fi

export UV_CACHE_DIR=${UV_INSTALL_DIR}/cache
export UV_PYTHON_INSTALL_DIR=${UV_INSTALL_DIR}/python
export UV_LOCAL_CACHE_DIR=/opt/uv_local/cache/
export UV_LOCAL_PYTHON_INSTALL_DIR=${UV_LOCAL_CACHE_DIR}/python
export UV_NO_PROGRESS=yes

sudo mkdir -p "${UV_CACHE_DIR}"
sudo mkdir -p "${UV_LOCAL_CACHE_DIR}"
sudo mkdir -p "${UV_PYTHON_INSTALL_DIR}"
sudo mkdir -p "${UV_LOCAL_PYTHON_INSTALL_DIR}"
if [[ "${ID}" == "ubuntu" ]] ; then
  sudo chown -R ubuntu:ubuntu "${UV_CACHE_DIR}"
  sudo chown -R ubuntu:ubuntu "${UV_LOCAL_CACHE_DIR}"
  sudo chown -R ubuntu:ubuntu "${UV_INSTALL_DIR}"
else
  sudo chown -R opc:opc "${UV_CACHE_DIR}"
  sudo chown -R opc:opc "${UV_LOCAL_CACHE_DIR}"
  sudo chown -R opc:opc "${UV_INSTALL_DIR}"
fi

trap 'rm -f "${marker_in_progress}"' EXIT
touch "${marker_in_progress}"

curl -LsSf https://astral.sh/uv/install.sh | sh
source "${UV_INSTALL_DIR}/env"

if [[ "${USING_OL8}" == "true" ]]; then
  uv python install 3.10 --force
else
  uv python install 3.12 --force
fi
uv venv "${VENV_PATH}" --clear
source "${VENV_PATH}/bin/activate"

# Detect CUDA version to install matching CuPy wheel
shopt -s nullglob
CUDA_MAJOR=12
if compgen -G "/usr/local/cuda-13*" >/dev/null; then
  CUDA_MAJOR=13
elif ! compgen -G "/usr/local/cuda-12*" >/dev/null; then
  echo "/usr/local/cuda not found. Defaulting to CUDA 12" >&2
fi
CUPY_PKG="cupy-cuda${CUDA_MAJOR}x"

if [[ "${USING_OL8}" == "true" ]]; then
  ANSIBLE_EXTRA_PKG="ansible-core==2.12.9"
else
  ANSIBLE_EXTRA_PKG=
fi

# Store requirements in a temporary file
#
# Using a single requirements file allows uv to satisfy the proper dependencies
# for all installed packages.
requirements=$(mktemp)

cat <<EOF_REQUIREMENTS >> "${requirements}"
pip
ansible
${ANSIBLE_EXTRA_PKG}
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
flatdict
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
${CUPY_PKG}

# Other packages
ujson
fastapi[standard-no-fastapi-cloud-cli]
uvicorn
EOF_REQUIREMENTS

echo "--- 8< --- Python Requirements --- 8< ---"
cat "${requirements}"
echo "--- >8 --- Python Requirements --- >8 ---"

# This is for flatdict: fails to install with pkg_resources missing, which was
# removed in setuptools 82.
#
# FIXME evaluate if we really need to depend on a package that has not been
# updated since 202[01]
cat <<EOF > pyproject.toml
[tool.uv.extra-build-dependencies]
flatdict = ["setuptools<82"]
EOF

uv pip install -r "${requirements}"

touch "${marker_install}"
