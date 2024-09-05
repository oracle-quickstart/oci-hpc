import subprocess
import shutil
import shlex
import os
import re
import requests
from shared_logging import logger
import pwd
import grp

def get_metadata():

    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"

    return requests.get(request_url, headers=headers).json()

def is_user_root():

    # Check if the user is root
    if os.geteuid() != 0:
        logger.debug("User is not root")
        return False

    # Return true if the user is root
    return True

def get_host_serial():

    # Run the shell command
    if not is_user_root():
        result = subprocess.run(['sudo', 'dmidecode', '-s', 'system-serial-number'], stdout=subprocess.PIPE)
    else:
        result = subprocess.run(['dmidecode', '-s', 'system-serial-number'], stdout=subprocess.PIPE)

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')

    # Validate output
    if 'Not Specified' in output:
        output = 'None'
    elif output == "":
        output = 'None'

    # Return the serial number
    return output.strip()

def get_slurm_instance_data():

    # Dictionary for storing slurm instance configuration
    config = {}

    cmd = shlex.split(f'scontrol show node {os.environ["HOSTNAME"]}')
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    decoded_output = result.stdout.decode('utf-8')

    # Search for pattern and get desired values
    pattern=r'ActiveFeatures=(\w+.*),(.*)'
    match = re.search(pattern, decoded_output)

    # Update config dictionary
    config = {'instance_shape': match.group(1)}
    config.update({'cluster_name': match.group(2)})

    return config

def get_net_devices():

    cmd = ['ibdev2netdev']
    net_devices = {}

    if shutil.which(cmd[0]) is None:
        logger.debug(f'Command \"{cmd[0]}\" does not exist')
    else:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')

        for line in output.split('\n'):
            word = line.split()
            if len(word) > 0:
                net_devices.update({word[0]: word[4]})

    return net_devices

def get_rdma_devices(oci_shape):

    rdma_devices = []
    if oci_shape == "BM.GPU.H100.8":
        rdma_devices = ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    elif oci_shape == "BM.GPU.B4.8" or oci_shape == "BM.GPU.A100-v2.8":
        rdma_devices = ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    elif oci_shape == "BM.GPU4.8":
        rdma_devices = ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    elif oci_shape == "BM.Optimized3.36":
        rdma_devices = ["mlx5_2", "mlx5_3"]

    return rdma_devices

def create_textfile_dir(ne_dir, tf_dir_name, ne_user, ne_group):

    textfile_dir = os.path.join(ne_dir, tf_dir_name)

    # Check if user exists
    try:
        pwd.getpwnam(ne_user)
    except KeyError:
        logger.debug(f"User {ne_user} does not exist")
        return False

    # Check if group exists
    try:
        grp.getgrnam(ne_group)
    except KeyError:
        logger.debug(f"Group {ne_group} does not exist")
        return False

    # Check if node exporter directory under which textfile collector directory will be created exists
    if not os.path.exists(textfile_dir):

        # Command for creating textfile collector directory
        create_dir_cmd = ['mkdir', '-p', textfile_dir]

        # Commands for updating user and group ownership of textfile collector directory
        commands = [
                ['chown', '-R', ne_user, textfile_dir],
                ['chgrp', '-R', ne_group, textfile_dir],
            ]

        if not is_user_root():
            try:
                subprocess.run(['sudo', '-S'] + create_dir_cmd, check=True)
            except:
                logger.debug(f"Unable to create {textfile_dir} directory")
                return False

            # Update user and group ownership of directory
            for command in commands:
                subprocess.run(['sudo', '-S'] + command, check=True)
        else:
            try:
                subprocess.run(create_dir_cmd, check=True)
            except:
                logger.debug(f"Unable to create {textfile_dir} directory")
                return False

            # Update user and group ownership of directory
            for command in commands:
                subprocess.run(command, check=True)
    return textfile_dir

def copy_metric_file(src_tf_path, dest_tf_path, mfile_owner, mfile_group):
    # Check if user exists
    try:
        pwd.getpwnam(mfile_owner)
    except KeyError:
        logger.debug(f"User {mfile_owner} does not exist")

    # Check if group exists
    try:
        grp.getgrnam(mfile_group)
    except KeyError:
        logger.debug(f"Group {mfile_group} does not exist")

    # Command for updating file user and group ownership
    commands = [
            ['chown', '-R', mfile_owner, src_tf_path],
            ['chgrp', '-R', mfile_group, src_tf_path],
        ]

    # Update user and group ownership of the the text file
    if not is_user_root():
        for command in commands:
            subprocess.run(['sudo', '-S'] + command, check=True)
    else:
        for command in commands:
            subprocess.run(command, check=True)

    # Move the temporary metrics file to actual destination and overwrite the existing
    tf_dir_path = os.path.dirname(dest_tf_path)
    if os.path.exists(tf_dir_path):
        os.system(f'sudo mv {src_tf_path} {dest_tf_path}')
    else:
        logger.debug(f'Unable to move {src_tf_path} to {dest_tf_path}')
        return False

    return True
