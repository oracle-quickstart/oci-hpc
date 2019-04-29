#!py
from OpenSSL import crypto
import base64

def generate_pfx():

        if __grains__['identity'] != None:
                identity = __grains__['identity']
                intermediate = crypto.load_certificate(crypto.FILETYPE_PEM, identity['intermediate.pem'])
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, identity['cert.pem'])
                key = crypto.load_privatekey(crypto.FILETYPE_PEM, identity['key.pem'], "hic sunt leones")

                cacerts = []
                cacerts.append(intermediate)

                PKCS12 = crypto.PKCS12Type()
                PKCS12.set_ca_certificates(cacerts)
                PKCS12.set_certificate(cert)
                PKCS12.set_privatekey(key)

                with open('/etc/wpa_supplicant/certs_bundle.pfx', "w") as f:
                        f.write(PKCS12.export(passphrase="hic sunt leones"))
                return True
        else:
                return False