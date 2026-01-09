#!/usr/bin/env python3

import argparse
from shared_logging import logger
import subprocess
import sys
import re
import os
import shlex

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, UTC
else:
    from datetime import datetime

class XidChecker:
    def __init__(self, dmesg_cmd="dmesg -T", time_interval=60):
        # if user is root
        if not os.geteuid() == 0:
            #logger.info("The XidChecker script did not run since it must be run as root")
            #sys.exit(1)
            raise PermissionError("Root privileges are required to run XidChecker")
        self.dmesg_cmd = dmesg_cmd
        self.results = {}

        # Check for the following GPU Xid errors in dmesg
        self.XID_EC = {
            "1": {"description": "Unused", "severity": "critical"},
            "2": {"description": "Unused", "severity": "critical"},
            "3": {"description": "Unused", "severity": "critical"},
            "4": {"description": "Unused", "severity": "critical"},
            "5": {"description": "Unused", "severity": "critical"},
            "6": {"description": "Unused", "severity": "critical"},
            "7": {"description": "Unused", "severity": "critical"},
            "8": {"description": "GPU stopped processing", "severity": "warning"},
            "9": {"description": "Unused", "severity": "critical"},
            "10": {"description": "Unused", "severity": "critical"},
            "11": {"description": "Invalid or corrupted push buffer stream", "severity": "warning"},
            "12": {"description": "Unused", "severity": "critical"},
            "13": {"description": "Graphics Engine Exception", "severity": "warning"},
            "14": {"description": "Unused", "severity": "warning"},
            "15": {"description": "Unused", "severity": "critical"},
            "16": {"description": "Unused", "severity": "critical"},
            "17": {"description": "Unused", "severity": "critical"},
            "18": {"description": "Bus mastering disabled in PCI Config Space", "severity": "critical"},
            "19": {"description": "Display Engine error", "severity": "critical"},
            "20": {"description": "Invalid or corrupted Mpeg push buffer", "severity": "warning"},
            "21": {"description": "Invalid or corrupted Motion Estimation push buffer", "severity": "warning"},
            "22": {"description": "Invalid or corrupted Video Processor push buffer", "severity": "warning"},
            "23": {"description": "Unused", "severity": "critical"},
            "24": {"description": "GPU semaphore timeout", "severity": "critical"},
            "25": {"description": "Invalid or illegal push buffer stream", "severity": "critical"},
            "26": {"description": "Framebuffer timeout", "severity": "critical"},
            "27": {"description": "Video processor exception", "severity": "critical"},
            "28": {"description": "Video processor exception", "severity": "critical"},
            "29": {"description": "Video processor exception", "severity": "critical"},
            "30": {"description": "GPU semaphore access error", "severity": "critical"},
            "31": {"description": "GPU memory page fault", "severity": "warning"},
            "32": {"description": "Invalid or corrupted push buffer stream", "severity": "warning"},
            "33": {"description": "Unused", "severity": "critical"},
            "34": {"description": "Unused", "severity": "critical"},
            "35": {"description": "Unused", "severity": "critical"},
            "36": {"description": "Unused", "severity": "critical"},
            "37": {"description": "Driver firmware error", "severity": "warning"},
            "38": {"description": "Driver firmware error", "severity": "warning"},
            "39": {"description": "Copy Engine Exception", "severity": "warning"},
            "40": {"description": "Copy Engine Exception", "severity": "warning"},
            "41": {"description": "Copy Engine Exception", "severity": "warning"},
            "42": {"description": "Unused", "severity": "critical"},
            "43": {"description": "GPU stopped processing", "severity": "warning"},
            "44": {"description": "Graphics Engine fault during context switch", "severity": "warning"},
            "45": {"description": "Preemptive cleanup, due to previous errors -- Most likely to see when running multiple cuda applications and hitting a DBE", "severity": "warning"},
            "46": {"description": "GPU stopped processing", "severity": "gpu_reset_reboot"},
            "47": {"description": "Unused", "severity": "critical"},
            "48": {"description": "Double Bit ECC Error", "severity": "warning"},
            "49": {"description": "Unused", "severity": "critical"},
            "50": {"description": "Unused", "severity": "critical"},
            "51": {"description": "Unused", "severity": "critical"},
            "52": {"description": "Unused", "severity": "critical"},
            "53": {"description": "Unused", "severity": "critical"},
            "54": {"description": "Auxiliary power is not connected to the GPU board", "severity": "critical"},
            "55": {"description": "Unused", "severity": "critical"},
            "56": {"description": "Unused", "severity": "critical"},
            "57": {"description": "Unused", "severity": "critical"},
            "58": {"description": "Unused", "severity": "critical"},
            "59": {"description": "Unused", "severity": "critical"},
            "60": {"description": "Video processor exception", "severity": "warning"},
            "61": {"description": "Internal micro-controller breakpoint/warning", "severity": "warning"},
            "62": {"description": "Internal micro-controller halt", "severity": "gpu_reset_reboot"},
            "63": {"description": "ECC page retirement or row re-mapper recording event", "severity": "warning"},
            "64": {"description": "ECC page retirement or row re-mapper recording failure", "severity": "warning"},
            "65": {"description": "Video processor exception", "severity": "warning"},
            "66": {"description": "Illegal access by driver", "severity": "warning"},
            "67": {"description": "Illegal access by driver", "severity": "warning"},
            "68": {"description": "NVDEC0 Exception", "severity": "warning"},
            "69": {"description": "Graphics Engine class error", "severity": "warning"},
            "70": {"description": "CE3: Unknown Error", "severity": "warning"},
            "71": {"description": "CE4: Unknown Error", "severity": "warning"},
            "72": {"description": "CE5: Unknown Error", "severity": "warning"},
            "73": {"description": "NVENC2 Error", "severity": "warning"},
            "74": {"description": "NVLINK Error", "severity": "warning"},
            "75": {"description": "CE6: Unknown Error", "severity": "warning"},
            "76": {"description": "CE7: Unknown Error", "severity": "warning"},
            "77": {"description": "CE8: Unknown Error", "severity": "warning"},
            "78": {"description": "vGPU Start Error", "severity": "warning"},
            "79": {"description": "GPU has fallen off the bus", "severity": "gpu_reset_reboot"},
            "80": {"description": "Corrupted data sent to GPU", "severity": "warning"},
            "81": {"description": "VGA Subsystem Error", "severity": "warning"},
            "82": {"description": "NVJPG0 Error", "severity": "warning"},
            "83": {"description": "NVDEC1 Error", "severity": "warning"},
            "84": {"description": "NVDEC2 Error", "severity": "warning"},
            "85": {"description": "CE9: Unknown Error", "severity": "warning"},
            "86": {"description": "OFA Exception", "severity": "warning"},
            "87": {"description": "Reserved", "severity": "warning"},
            "88": {"description": "NVDEC3 Error", "severity": "warning"},
            "89": {"description": "NVDEC4 Error", "severity": "warning"},
            "90": {"description": "Reserved", "severity": "warning"},
            "91": {"description": "Reserved", "severity": "warning"},
            "92": {"description": "High single-bit ECC error rate", "severity": "warning"},
            "93": {"description": "Non-fatal violation of provisioned Ecc InfoROM wear limit", "severity": "warning"},
            "94": {"description": "Contained memory error", "severity": "warning"},
            "95": {"description": "Uncontained memory error", "severity": "gpu_reset_reboot"},
            "96": {"description": "NVDEC5 Error", "severity": "warning"},
            "97": {"description": "NVDEC6 Error", "severity": "warning"},
            "98": {"description": "NVDEC7 Error", "severity": "warning"},
            "99": {"description": "NVJPG1 Error", "severity": "warning"},
            "100": {"description": "NVJPG2 Error", "severity": "warning"},
            "101": {"description": "NVJPG3 Error", "severity": "warning"},
            "102": {"description": "NVJPG4 Error", "severity": "warning"},
            "103": {"description": "NVJPG5 Error", "severity": "warning"},
            "104": {"description": "NVJPG6 Error", "severity": "warning"},
            "105": {"description": "NVJPG7 Error", "severity": "warning"},
            "106": {"description": "SMBPBI Test Message", "severity": "warning"},
            "107": {"description": "SMBPBI Test Message Silent", "severity": "warning"},
            "108": {"description": "Reserved", "severity": "warning"},
            "109": {"description": "Context Switch Timeout Error", "severity": "warning"},
            "110": {"description": "Security Fault Error", "severity": "warning"},
            "111": {"description": "Display Bundle Error Event", "severity": "warning"},
            "112": {"description": "Display Supervisor Error", "severity": "warning"},
            "113": {"description": "DP Link Training Error", "severity": "warning"},
            "114": {"description": "Display Pipeline Underflow Error", "severity": "warning"},
            "115": {"description": "Display Core Channel Error", "severity": "warning"},
            "116": {"description": "Display Window Channel Error", "severity": "warning"},
            "117": {"description": "Display Cursor Channel Error", "severity": "warning"},
            "118": {"description": "Display Pixel Pipeline Error", "severity": "warning"},
            "119": {"description": "GSP RPC Timeout", "severity": "gpu_reset_reboot"},
            "120": {"description": "GSP Error", "severity": "gpu_reset_reboot"},
            "121": {"description": "C2C Error", "severity": "warning"},
            "122": {"description": "SPI PMU RPC Read Failure", "severity": "warning"},
            "123": {"description": "SPI PMU RPC Write Failure", "severity": "warning"},
            "124": {"description": "SPI PMU RPC Erase Failure", "severity": "warning"},
            "125": {"description": "Inforom FS Failure", "severity": "warning"},
            "126": {"description": "Reserved", "severity": "warning"},
            "127": {"description": "Reserved", "severity": "warning"},
            "128": {"description": "Reserved", "severity": "warning"},
            "129": {"description": "Reserved", "severity": "warning"},
            "130": {"description": "Reserved", "severity": "warning"},
            "131": {"description": "Reserved", "severity": "warning"},
            "132": {"description": "Reserved", "severity": "warning"},
            "133": {"description": "Reserved", "severity": "warning"},
            "134": {"description": "Reserved", "severity": "warning"},
            "135": {"description": "Reserved", "severity": "warning"},
            "136": {"description": "Reserved", "severity": "warning"},
            "137": {"description": "Reserved", "severity": "warning"},
            "138": {"description": "Reserved", "severity": "warning"},
            "139": {"description": "Reserved", "severity": "warning"},
            "140": {"description": "ECC Unrecovered Error", "severity": "gpu_reset_reboot"},
            "141": {"description": "Reserved", "severity": "warning"},
            "142": {"description": "Reserved", "severity": "warning"},
            "143": {"description": "GPU Initialization Error", "severity": "gpu_reset_reboot"},
            "149": {"description": "NVLINK: NETIR Error", "severity": "warning"},
        }

    def get_dmesg(self):
        dmesg_cmd_list = shlex.split(self.dmesg_cmd)
        dmesg_output = ""
        try:
            result = subprocess.run(dmesg_cmd_list, check=True, capture_output=True, text=True, timeout=10)
            dmesg_output = result.stdout
        except subprocess.CalledProcessError as e:
            logger.info("Error running Xid check command dmesg -T:", e)
        except subprocess.TimeoutExpired as e:
            logger.info("dmesg -T command timed out:", e)
        return dmesg_output
    
    # Get the timestamp from the dmesg line. This will help when checking whether GPU was reset in the last 24 hours in the healthcheck script.
    @staticmethod
    def parse_dmesg_timestamp(line):
        # Extract timestamp from start of line (e.g., "Thu May  9 14:00:43 2024 ...")
        match = re.match(r"\[([A-Za-z]{3} [A-Za-z]{3}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\]", line)
        if match:
            timestamp_str = match.group(1)
            try:
                return datetime.strptime(timestamp_str, "%a %b %d %H:%M:%S %Y")
            except ValueError:
                return None
        return None

    def check_gpu_xid(self):
        # buckets we’ll return
        categorized_results = {
            "critical": {},
            "gpu_reset_reboot": {},
            "warning": {},
        }

        dmesg_output = self.get_dmesg()

        if dmesg_output == "":
            return {
                "categories": categorized_results,
                "results": self.results,
            } 

        if "NVRM: Xid" not in dmesg_output:
            logger.info("Xid Check: Passed")
            # Still return empty buckets + whatever self.results you maintain
            return {
                "categories": categorized_results,
                "results": self.results,
            }

        # We found at least one "NVRM: Xid" string in dmesg, walk all known XIDs
        for XID in self.XID_EC.keys():
            logger.debug(f"Checking for GPU Xid {XID} error in dmesg")

            # Example line:
            # NVRM: Xid (PCI:0000:08:00): 79, GPU has fallen off the bus
            matches = re.findall(
                rf"NVRM: Xid \(PCI:(.*?): {XID},",  # capture PCI location
                dmesg_output,
            )

            tmp_dict = {}
            for match in matches:
                if match not in tmp_dict:
                    tmp_dict[match] = 1
                else:
                    tmp_dict[match] += 1

            if not matches:
                logger.debug(f"No GPU Xid {XID} error found in dmesg")
                continue

            # We have at least one hit for this XID
            desc = self.XID_EC[XID]["description"]
            severity = self.XID_EC[XID]["severity"]  # 'critical', 'gpu_reset_reboot', 'warning'

            # Do not display the errors here as we are summarizing those later
            # for pci in tmp_dict.keys():
            #     logger.info(f"{XID} : count: {tmp_dict[pci]}, {desc} - PCI: {pci}")

            # Store in the global results structure (if you still want it)
            self.results[XID] = {
                "results": tmp_dict,
                "description": desc,
                "severity": severity,
            }

            # Add to severity bucket
            if severity not in categorized_results:
                # safety net if something unexpected sneaks in
                logger.warning(
                    f"Unknown severity '{severity}' for XID {XID}, defaulting to 'warning'"
                )
                severity_key = "warning"
            else:
                severity_key = severity

            categorized_results[severity_key][XID] = {
                "results": tmp_dict,
                "description": desc,
            }

        # Final return: 3 buckets + raw per-XID results
        return {
            "categories": categorized_results,
            "results": self.results,
        }


if __name__ == '__main__':
    # Argument parsing
    parser = argparse.ArgumentParser(description='Check for GPU Xid errors.')
    parser.add_argument('--dmesg_cmd', default='dmesg -T', help='Dmesg file to check. Default is dmesg -T.')
    args = parser.parse_args()
    logger.debug(f"Using dmesg command: {args.dmesg_cmd}")
    
    try:
        xc = XidChecker(dmesg_cmd=args.dmesg_cmd)
        results = xc.check_gpu_xid()
        logger.debug("Status: {}, Results: {}".format(results["status"], results["results"]))
    except PermissionError:
        pass