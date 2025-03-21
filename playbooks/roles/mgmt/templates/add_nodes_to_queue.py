import subprocess
import re
import sys
import json
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor

import oci

# Get the current date and time with milliseconds
current_time = datetime.now()
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

print(f"Started the to add nodes at {current_time_str}")

queue_ocid = "{{queue_ocid}}"
region = "{{region}}"
controller_name = "{{controller_hostname}}"

# Initialize Queue Client
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
cp_client = oci.queue.QueueAdminClient(config={}, signer=signer)
endpoint = cp_client.get_queue(queue_ocid).data.messages_endpoint
queue_client = oci.queue.QueueClient(config={}, signer=signer, service_endpoint=endpoint)

channel_id_md=oci.queue.models.MessageMetadata(channel_id=controller_name)
for ip_address in sys.argv[1:]:    
    message = oci.queue.models.PutMessagesDetailsEntry(content="{\"ip_address\": \""+ip_address+"\", \"status\": \"starting\"}",metadata=channel_id_md)
    messages_details = oci.queue.models.PutMessagesDetails(messages=[message])
    response=queue_client.put_messages(queue_ocid, messages_details)


current_time = datetime.now()
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
print(f"Finished to add nodes at {current_time_str}")