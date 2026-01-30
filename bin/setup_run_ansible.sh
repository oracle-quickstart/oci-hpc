source "${UV_INSTALL_DIR}/env"
source "${VENV_PATH}/bin/activate"

inventory=$1
playbook=$2

if [[ "${inventory:+yes}" != "yes" || "${playbook:+yes}" != "yes" ]]; then
    echo "usage: ${0} <inventory> <playbook>"
    exit 1
fi

modified_hostname=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .displayName`
echo $modified_hostname
log=/config/logs/${modified_hostname}.log

echo "Testing Python and Ansible installations" | tee -a $log
uv run ansible localhost -c local -m ping 2>&1 | tee -a $log
uv run python -c "import uvicorn" 2>&1 | tee -a $log

max_attempts=6
attempt=1
wait_time=10
while [ $attempt -le $max_attempts ]; do
    echo "Attempt $attempt of $max_attempts: Configuring the node" | tee -a $log
    uv run ansible-playbook -i "${inventory}" "${playbook}" 2>&1 | tee -a $log
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "Ansible succeeded!" | tee -a $log
        break
    else
        echo "Ansible failed. " | tee -a $log
        if [ $attempt -lt $max_attempts ]; then
            echo "Retrying in ($wait_time)s ..." | tee -a $log
            sleep $wait_time
            wait_time=$((wait_time * 2))
        else
            echo "Max attempts ($max_attempts) reached. Giving up." | tee -a $log
        fi
        ((attempt++))
    fi
done 
