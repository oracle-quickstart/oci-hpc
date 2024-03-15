import argparse
import os
import sys
import socket
import multiprocessing
import paramiko
import csv
import json

specific_fieldnames = ['displayName','hostname', 'privateIp','networkBlockId','rackid', 'ociAdName','id']

def is_valid_file(parser, arg):
    if not os.path.exists(arg):
        parser.error(f"The file {arg} does not exist!")
    else:
        return arg

def is_valid_hostname(parser, arg):
    try:
        socket.gethostbyname(arg)
        return arg
    except socket.error:
        parser.error(f"Invalid hostname or IP address: {arg}")

def json_to_stdout(flattened_results):
    # Write JSON data to STDOUT
    writer = csv.DictWriter(sys.stdout, fieldnames=specific_fieldnames)
    writer.writeheader()
    for data in flattened_results:
        writer.writerow(data) 

def json_to_csv(flattened_results, csv_file):
    # Get the specific fieldnames
#    print("Content of result:", entries_data)
    # Write JSON data to CSV
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=specific_fieldnames)
        writer.writeheader()

        for data in flattened_results:
            writer.writerow(data) 

def process_entry(entry, username):
    # Replace this with the path to your private key
    ssh_key = "/home/"+username+"/.ssh/id_rsa"

    # Replace this with your SSH connection details
    ssh_host = entry
    ssh_user = username

    # Create SSH client
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    parsed_data_list = []

    try:
        # Connect to SSH server using key pair authentication
        ssh_client.connect(ssh_host, username=ssh_user, key_filename=ssh_key)

        # Perform SSH operations here
        stdin, stdout, stderr = ssh_client.exec_command('curl -H "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/')
        output = stdout.read().decode()
        parsed_instance = json.loads(output)

        stdin, stdout, stderr = ssh_client.exec_command('curl -H "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/host/')
        output = stdout.read().decode()
        parsed_host = json.loads(output)

        stdin, stdout, stderr = ssh_client.exec_command('curl -H "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/vnics/')
        output = stdout.read().decode()
        list_of_vnics = json.loads(output)
        first_vnic = list_of_vnics[0]

        parsed_data = {**parsed_instance, **parsed_host, **first_vnic}

        # Extract required fields from parsed_data
        required_fields = specific_fieldnames
        extracted_data = {field: parsed_data.get(field, "") for field in required_fields}
        parsed_data_list.append(extracted_data)

    except socket.error as e:
        print(f"Error occurred while connecting to {ssh_host}: {e}")
        return None
    except paramiko.AuthenticationException as e:
        print(f"Authentication error occurred while connecting to {ssh_host}: {e}")
        return None
    except paramiko.SSHException as e:
        print(f"SSH error occurred while connecting to {ssh_host}: {e}")
        return None
    except Exception as e:
        print(f"Error occurred while connecting to {ssh_host}: {e}")
        return None

    finally:
        # Close SSH connection
        ssh_client.close()

    return parsed_data_list

def process_entry_wrapper(args):
    entry, private_key = args
    return process_entry(entry, private_key)

def main():
    parser = argparse.ArgumentParser(description="Process file or hostname/IP address and optionally generate a CSV file of results.")
    parser.add_argument('input', metavar='input', type=str, help='Input file or hostname/IP address')
    parser.add_argument('--output-dir', metavar='output_dir', type=str, default='.', help='Output directory to save files (default: current directory)')
    parser.add_argument('--username', metavar='username', type=str, help='Username to pass to ssh connection, if not set will use login username')
    parser.add_argument('--csv', metavar='csv', type=str, help='Generate a CSV file of results')
    args = parser.parse_args()

    if not args.username:
          args.username=os.getlogin()

    if os.path.isfile(args.input):
        print(f"Processing file: {args.input}")
        with open(args.input, 'r') as file:
            entries = [line.strip() for line in file.readlines()]

        # Create a pool of worker processes
        pool = multiprocessing.Pool()

        # Execute the process_entry function on each entry in parallel
        results = pool.map(process_entry_wrapper, [(entry, args.username) for entry in entries])
        flattened_results = [item for sublist in results for item in sublist]

        # Close the pool to release resources
        pool.close()
        pool.join()
        # Parse JSON data and generate CSV file
        if args.csv:
           json_to_csv(flattened_results, args.csv)
        else:
           json_to_stdout(flattened_results)

    else:
        print(f"Processing hostname/IP: {args.input}")
        result = process_entry(args.input, args.username)

        # Parse JSON data and generate CSV file
        if args.csv:
           json_to_csv(result, args.csv)
        else:
           json_to_stdout(result)


if __name__ == "__main__":
    main()
