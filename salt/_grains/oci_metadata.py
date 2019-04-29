import requests
import json

# metadata server address
_metadata_url = 'http://169.254.169.254/opc/v1/'

def main():
        grains = {}
        try:
                grains['oci_instance'] = json.loads(requests.get(_metadata_url + 'instance').text)
        except Exception:
                pass
        try:
                grains['oci_vnics'] = json.loads(requests.get(_metadata_url + 'vnics').text)
        except Exception:
                pass
        try:
                grains['identity'] = json.loads(requests.get(_metadata_url + 'identity').text)
        except Exception:
                pass

        return grains