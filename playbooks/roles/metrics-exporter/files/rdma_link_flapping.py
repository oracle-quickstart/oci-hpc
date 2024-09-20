#!/usr/bin/env python3

import os
import sys
import time
import datetime
import re
import argparse
import socket
import subprocess
from shared_logging import logger


class LinkFlappingTest:
    def __init__(self, time_interval=6):
        self.results = None
        self.time_interval = int(time_interval)
        self.link_data = None

            
        # Check if the log file exists
        msg_file = "/var/log/messages"
        if not os.path.exists(msg_file):
            msg_file = "/var/log/syslog"
        self.log_file = msg_file

    def get_rdma_link_failures(self):

        pattern  = r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+wpa_supplicant(?:\[\d+\])?: (\w+): CTRL-EVENT-EAP-FAILURE EAP authentication failed"
        pattern2 = r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+kernel: (?:\[\d+\.\d+\]\s)?mlx5_core \S+ (\w+): Link down"
        
        self.link_data = {}
        with open(self.log_file, "r") as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    time_str = match.group(1)
                    interface = match.group(2)
                    logger.debug(f"time: {time_str}, interface: {interface}")
                    if interface not in self.link_data:
                        self.link_data[interface] = {"failures": [time_str], "link_down": []}
                    else:
                        self.link_data[interface]["failures"].append(time_str)

                
                match = re.search(pattern2, line)
                if match:
                    time_str = match.group(1)
                    interface = match.group(2)
                    logger.debug(f"time: {time_str}, interface: {interface}")
                    if interface not in self.link_data:
                        self.link_data[interface] = {"failures": [], "link_down": [time_str]}
                    else:
                        self.link_data[interface]["link_down"].append(time_str)
                        
        logger.debug("Link Data: {}".format(self.link_data))
        return self.link_data

    def process_rdma_link_flapping(self):

        link_issues = {"failures": [], "link_down": []}

        # Get the time stamp when the host came up
        bootup_time = subprocess.run(['uptime', '-s'], stdout=subprocess.PIPE)
        bootup_time = bootup_time.stdout.decode('utf-8').strip()
        bootup_time_str = datetime.datetime.strptime(bootup_time, "%Y-%m-%d %H:%M:%S")
        bootup_time_sec = int(time.mktime(bootup_time_str.timetuple()))
        bootup_time_grace_period = bootup_time_sec + 1800

        status = 0
        if len(self.link_data) >= 0:
            current_date = datetime.datetime.now()
            current_date_str = current_date.strftime("%Y-%b-%d %H:%M:%S")
            current_date_sec = int(time.mktime(datetime.datetime.strptime(current_date_str, "%Y-%b-%d %H:%M:%S").timetuple()))
            
            link_failures = False
            for interface in self.link_data:
                if len(self.link_data[interface]["failures"]) > 0:
                    link_failures = True
                    logger.debug(f"{interface}: {len(self.link_data[interface]['failures'])} RDMA link failure entries in {self.log_file}")
                    logger.debug(f"{interface}: {self.link_data[interface]['failures']}")        
                last_date_failure_str = None

                if len(self.link_data[interface]["failures"]) > 0:
                    last_date_failure_str = self.link_data[interface]["failures"][-1]
                    last_date_failure = datetime.datetime.strptime(last_date_failure_str, "%b %d %H:%M:%S")

                    # Compare the month of the last failure date with the current month
                    if last_date_failure.month > current_date.month:
                        # If the last failure month is greater than the current month, subtract one from the current year
                        last_date_failure = last_date_failure.replace(year=current_date.year - 1)
                    else:
                        # Otherwise, set the year of the last failure date to the current year
                        last_date_failure = last_date_failure.replace(year=current_date.year)

                    # Convert the last failure date to seconds since the epoch
                    last_date_failure_sec = int(time.mktime(last_date_failure.timetuple()))
                
                if last_date_failure_str != None and last_date_failure_str != current_date_str:
                    diff_secs = current_date_sec - last_date_failure_sec
                    diff_hours = diff_secs // (60 * 60)
                    logger.debug(f"RDMA link ({interface}) failed  {diff_hours} hours ago")

                    logger.debug(f"bootup_time_sec: {bootup_time_sec}, boot_time_grace_period: {bootup_time_grace_period}, current_date_sec: {current_date_sec}, diff_secs: {diff_secs}, diff_hours: {diff_hours}")
                    if diff_hours < self.time_interval and last_date_failure_sec > bootup_time_grace_period:
                        logger.debug(f"{interface}: one or more RDMA link flapping events within {self.time_interval} hours. Last flapping event: {last_date_failure_str})")
                        link_issues["failures"].append(f"{interface}: {len(self.link_data[interface]['failures'])}")
                        status = -1

            for interface in self.link_data:
                if len(self.link_data[interface]["link_down"]) > 0:
                    logger.debug(f"{interface}: {len(self.link_data[interface]['link_down'])} RDMA link down entries in {self.log_file}")
                    logger.debug(f"{interface}: {self.link_data[interface]['link_down']}")
                last_date_down_str = None

                if len(self.link_data[interface]["link_down"]) > 0:
                        last_date_down_str = self.link_data[interface]["link_down"][-1]
                        last_date_down = datetime.datetime.strptime(last_date_down_str, "%b %d %H:%M:%S")

                        # Compare the month of the last failure date with the current month
                        if last_date_down.month > current_date.month:
                            # If the last failure month is greater than the current month, subtract one from the current year
                            last_date_down = last_date_down.replace(year=current_date.year - 1)
                        else:
                            # Otherwise, set the year of the last failure date to the current year
                            last_date_down = last_date_down.replace(year=current_date.year)

                        # Convert the last failure date to seconds since the epoch
                        last_date_down_sec = int(time.mktime(last_date_down.timetuple()))


                if last_date_down_str != None and last_date_down_str != current_date_str:
                    diff_secs = current_date_sec - last_date_down_sec
                    diff_hours = diff_secs // (60 * 60)
                    logger.debug(f"RDMA link ({interface}) down  {diff_hours} hours ago")
                    
                    logger.debug(f"bootup_time_sec: {bootup_time_sec}, boot_time_grace_period: {bootup_time_grace_period}, current_date_sec: {current_date_sec}, diff_secs: {diff_secs}, diff_hours: {diff_hours}")
                    if diff_hours < self.time_interval and last_date_down_sec > bootup_time_grace_period:
                        logger.debug(f"{interface}, one or more RDMA link down events within {self.time_interval} hours. Last link down event: {last_date_down_str}")
                        link_issues["link_down"].append(f"{interface}: {len(self.link_data[interface]['link_down'])}")
                        status = -2
            if status == -1:
                logger.debug(f"One or more RDMA link flapping events within the past {self.time_interval} hours")
            if status == -2:
                logger.debug(f"One or more RDMA link down events within the past {self.time_interval} hours")

        else:
            logger.info("No RDMA link failures entry in /var/log/messages")
        if status == 0:    
            logger.info("RDMA link flapping/down test: Passed")
        else:
            logger.warning("RDMA link flapping/down test: Failed")
        return link_issues


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process RDMA link flapping data")
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level")
    args = parser.parse_args()

    logger.setLevel(args.log_level)

    auth_failure_file = "/tmp/last_auth_failure_date"
    msg_file = "/var/log/messages"
    if not os.path.exists(msg_file):
        msg_file = "/var/log/syslog"
    time_interval_hours = 6
    lft = LinkFlappingTest(time_interval=time_interval_hours)
    link_data = lft.get_rdma_link_failures()
    lft.process_rdma_link_flapping()
