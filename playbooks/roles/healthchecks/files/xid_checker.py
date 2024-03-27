#!/usr/bin/env python3

import argparse
from shared_logging import logger
import subprocess
import sys
import re

class XidChecker:
    def __init__(self, dmesg_cmd="dmesg", time_interval=60):
        self.dmesg_cmd = dmesg_cmd
        self.results = {}


        # Check for the following GPU Xid errors in dmesg
        self.XID_EC = {
                "1": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "2": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "3": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "4": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "5": {"description": "Unused", "severity": "Critical"},
                "6": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "7": {"description": "Invalid or corrupted push buffer address", "severity": "Critical"},
                "8": {"description": "GPU stopped processing", "severity": "Critical"},
                "9": {"description": "Driver error programming GPU", "severity": "Critical"},
                "10": {"description": "Unused", "severity": "Critical"},
                "11": {"description": "Invalid or corrupted push buffer stream", "severity": "Critical"},
                "12": {"description": "Driver error handling GPU exception", "severity": "Critical"},
                "13": {"description": "Graphics Engine Exception", "severity": "Critical"},
                "14": {"description": "Unused", "severity": "Warn"},
                "15": {"description": "Unused", "severity": "Warn"},
                "16": {"description": "Display engine hung", "severity": "Warn"},
                "17": {"description": "Unused", "severity": "Warn"},
                "18": {"description": "Bus mastering disabled in PCI Config Space", "severity": "Warn"},
                "19": {"description": "Display Engine error", "severity": "Warn"},
                "20": {"description": "Invalid or corrupted Mpeg push buffer", "severity": "Warn"},
                "21": {"description": "Invalid or corrupted Motion Estimation push buffer", "severity": "Warn"},
                "22": {"description": "Invalid or corrupted Video Processor push buffer", "severity": "Warn"},
                "23": {"description": "Unused", "severity": "Warn"},
                "24": {"description": "GPU semaphore timeout", "severity": "Warn"},
                "25": {"description": "Invalid or illegal push buffer stream", "severity": "Warn"},
                "26": {"description": "Framebuffer timeout", "severity": "Warn"},
                "27": {"description": "Video processor exception", "severity": "Warn"},
                "28": {"description": "Video processor exception", "severity": "Warn"},
                "29": {"description": "Video processor exception", "severity": "Warn"},
                "30": {"description": "GPU semaphore access error", "severity": "Warn"},
                "31": {"description": "GPU memory page fault", "severity": "Critical"},    
                "32": {"description": "Invalid or corrupted push buffer stream", "severity": "Warn"},
                "33": {"description": "Internal micro-controller error", "severity": "Warn"},
                "34": {"description": "Video processor exception", "severity": "Warn"},
                "35": {"description": "Video processor exception", "severity": "Warn"},
                "36": {"description": "Video processor exception", "severity": "Warn"},
                "37": {"description": "Driver firmware error", "severity": "Warn"},
                "38": {"description": "Driver firmware error", "severity": "Warn"},
                "39": {"description": "Unused", "severity": "Warn"},
                "40": {"description": "Unused", "severity": "Warn"},
                "41": {"description": "Unused", "severity": "Warn"},
                "42": {"description": "Video processor exception", "severity": "Warn"},
                "43": {"description": "GPU stopped processing", "severity": "Warn"},
                "44": {"description": "Graphics Engine fault during context switch", "severity": "Warn"},
                "45": {"description": "Preemptive cleanup, due to previous errors -- Most likely to see when running multiple cuda applications and hitting a DBE", "severity": "Warn"},
                "46": {"description": "GPU stopped processing", "severity": "Warn"},
                "47": {"description": "Video processor exception", "severity": "Warn"},
                "48": {"description": "Double Bit ECC Error", "severity": "Critical"}, 
                "49": {"description": "Unused", "severity": "Warn"},
                "50": {"description": "Unused", "severity": "Warn"},
                "51": {"description": "Unused", "severity": "Warn"},
                "52": {"description": "Unused", "severity": "Warn"},
                "53": {"description": "Unused", "severity": "Warn"},
                "54": {"description": "Auxiliary power is not connected to the GPU board", "severity": "Warn"},
                "55": {"description": "Unused", "severity": "Warn"},
                "56": {"description": "Display Engine error", "severity": "Critical"},
                "57": {"description": "Error programming video memory interface", "severity": "Critical"},
                "58": {"description": "Unstable video memory interface detected", "severity": "Critical"},
                "59": {"description": "Internal micro-controller error (older drivers)", "severity": "Warn"},
                "60": {"description": "Video processor exception", "severity": "Warn"},
                "61": {"description": "Internal micro-controller breakpoint/warning (newer drivers)", "severity": "Warn"},
                "62": {"description": "Internal micro-controller halt", "severity": "Critical"},
                "63": {"description": "ECC page retirement or row remapping recording event", "severity": "Critical"},
                "64": {"description": "ECC page retirement or row remapper recording failure", "severity": "Critical"},
                "65": {"description": "Video processor exception", "severity": "Critical"},
                "66": {"description": "Illegal access by driver", "severity": "Warn"},
                "67": {"description": "Illegal access by driver", "severity": "Warn"},
                "68": {"description": "NVDEC0 Exception", "severity": "Critical"},
                "69": {"description": "Graphics Engine class error", "severity": "Critical"},
                "70": {"description": "CE3: Unknown Error", "severity": "Warn"},
                "71": {"description": "CE4: Unknown Error", "severity": "Warn"},
                "72": {"description": "CE5: Unknown Error", "severity": "Warn"},
                "73": {"description": "NVENC2 Error", "severity": "Critical"},
                "74": {"description": "NVLINK Error", "severity": "Critical"},
                "75": {"description": "CE6: Unknown Error", "severity": "Warn"},
                "76": {"description": "CE7: Unknown Error", "severity": "Warn"},
                "77": {"description": "CE8: Unknown Error", "severity": "Warn"},
                "78": {"description": "vGPU Start Error", "severity": "Warn"},
                "79": {"description": "GPU has fallen off the bus", "severity": "Critical"},
                "80": {"description": "Corrupted data sent to GPU", "severity": "Critical"},
                "81": {"description": "VGA Subsystem Error", "severity": "Critical"},
                "82": {"description": "NVJPGO Error", "severity": "Warn"},
                "83": {"description": "NVDEC1 Error", "severity": "Warn"},
                "84": {"description": "NVDEC2 Error", "severity": "Warn"},
                "85": {"description": "CE9: Unknown Error", "severity": "Warn"},
                "86": {"description": "OFA Exception", "severity": "Warn"},
                "87": {"description": "Reserved", "severity": "Warn"},
                "88": {"description": "NVDEC3 Error", "severity": "Warn"},
                "89": {"description": "NVDEC4 Error", "severity": "Warn"},
                "90": {"description": "Reserved", "severity": "Warn"},
                "91": {"description": "Reserved", "severity": "Warn"},
                "92": {"description": "High single-bit ECC error rate", "severity": "Critical"},
                "93": {"description": "Non-fatal violation of provisioned InfoROM wear limit", "severity": "Warn"},
                "94": {"description": "Contained ECC error", "severity": "Critical"},
                "95": {"description": "Uncontained ECC error", "severity": "Critical"},
                "96": {"description": "NVDEC5 Error", "severity": "Warn"},
                "97": {"description": "NVDEC6 Error", "severity": "Warn"},
                "98": {"description": "NVDEC7 Error", "severity": "Warn"},
                "99": {"description": "NVJPG1 Error", "severity": "Warn"},
                "100": {"description": "NVJPG2 Error", "severity": "Warn"},
                "101": {"description": "NVJPG3 Error", "severity": "Warn"},
                "102": {"description": "NVJPG4 Error", "severity": "Warn"},
                "103": {"description": "NVJPG5 Error", "severity": "Warn"},
                "104": {"description": "NVJPG6 Error", "severity": "Warn"},
                "105": {"description": "NVJPG7 Error", "severity": "Warn"},
                "106": {"description": "SMBPBI Test Message", "severity": "Warn"},
                "107": {"description": "SMBPBI Test Message Silent", "severity": "Warn"},
                "108": {"description": "Reserved", "severity": "Warn"},
                "109": {"description": "Context Switch Timeout Error", "severity": "Critical"},
                "110": {"description": "Security Fault Error", "severity": "Warn"},
                "111": {"description": "Display Bundle Error Event", "severity": "Warn"},
                "112": {"description": "Display Supervisor Error", "severity": "Warn"},
                "113": {"description": "DP Link Training Error", "severity": "Warn"},
                "114": {"description": "Display Pipeline Underflow Error", "severity": "Warn"},
                "115": {"description": "Display Core Channel Error", "severity": "Warn"},
                "116": {"description": "Display Window Channel Error", "severity": "Warn"},
                "117": {"description": "Display Cursor Channel Error", "severity": "Warn"},
                "118": {"description": "Display Pixel Pipeline Error", "severity": "Warn"},
                "119": {"description": "GSP RPC Timeout", "severity": "Critical"},
                "120": {"description": "GSP Error", "severity": "Critical"},
                "121": {"description": "C2C Link Error", "severity": "Critical"},
                "122": {"description": "SPI PMU RPC Read Failure", "severity": "Warn"},
                "123": {"description": "SPI PMU RPC Write Failure", "severity": "Warn"},
                "124": {"description": "SPI PMU RPC Erase Failure", "severity": "Warn"},
                "125": {"description": "Inforom FS Failure", "severity": "Warn"},
                "126": {"description": "Reserved", "severity": "Warn"},
                "127": {"description": "Reserved", "severity": "Warn"},
                "128": {"description": "Reserved", "severity": "Warn"},
                "129": {"description": "Reserved", "severity": "Warn"},
                "130": {"description": "Reserved", "severity": "Warn"},
                "131": {"description": "Reserved", "severity": "Warn"},
                "132": {"description": "Reserved", "severity": "Warn"},
                "133": {"description": "Reserved", "severity": "Warn"},
                "134": {"description": "Reserved", "severity": "Warn"},
                "135": {"description": "Reserved", "severity": "Warn"},
                "136": {"description": "Reserved", "severity": "Warn"},
                "137": {"description": "Reserved", "severity": "Warn"},
                "138": {"description": "Reserved", "severity": "Warn"},
                "139": {"description": "Reserved", "severity": "Warn"},
                "140": {"description": "Unrecovered ECC Error", "severity": "Warn"},
                "141": {"description": "Reserved", "severity": "Warn"},
                "142": {"description": "Reserved", "severity": "Warn"},
                "143": {"description": "GPU Initialization Failure", "severity": "Warn"}
                }

    def check_gpu_xid(self):
        status = "Pass"
        dmesg_output = subprocess.check_output([self.dmesg_cmd]).decode("utf-8")
        if "NVRM: Xid" in dmesg_output:
            for XID in self.XID_EC.keys():
                logger.debug(f"Checking for GPU Xid {XID} error in dmesg")
                
                matches = re.findall(f"NVRM: Xid \(PCI:(.*?): {XID},", dmesg_output)
                tmp_dict = {}
                for match in matches:
                    if match not in tmp_dict:
                        tmp_dict[match] = 1
                    else:
                        tmp_dict[match] = tmp_dict[match] + 1
                for x in tmp_dict.keys():
                    logger.info(f"{XID} : count: {tmp_dict[x]}, {self.XID_EC[XID]['description']} - PCI: {x}")
                if not matches:
                    logger.debug(f"No GPU Xid {XID} error found in dmesg")
                if tmp_dict != {}:
                    if self.XID_EC[XID]['severity'] == "Critical":
                        status = "Failed"
                    self.results[XID] = {"results": tmp_dict, "description": self.XID_EC[XID]['description']}
        else:
            logger.info("Xid Check: Passed")
        return {"status": status, "results": self.results}


if __name__ == '__main__':
    # Argument parsing
    parser = argparse.ArgumentParser(description='Check for GPU Xid errors.')
    parser.add_argument('--dmesg_cmd', default='dmesg', help='Dmesg file to check. Default is dmesg.')
    args = parser.parse_args()


    logger.debug(f"Using dmesg command: {args.dmesg_cmd}")
    
    xc = XidChecker(dmesg_cmd=args.dmesg_cmd)
    results = xc.check_gpu_xid()
    logger.debug("Status: {}, Results: {}".format(results["status"], results["results"]))
