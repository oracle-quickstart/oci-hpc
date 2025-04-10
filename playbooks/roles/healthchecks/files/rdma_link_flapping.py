#!/usr/bin/env python3

import os
import sys
import time
import datetime
import re
import argparse
import subprocess
from shared_logging import logger

class LinkFlappingTest:
    def __init__(self, time_interval=6):
        self.results = None
        self.time_interval = int(time_interval)
        self.link_data = None

        self.log_file = "/var/log/messages"
        if not os.path.exists(self.log_file):
            self.log_file = "/var/log/syslog"

    def get_rdma_link_failures(self):
        pattern1 = "CTRL-EVENT-EAP-FAILURE EAP authentication failed"
        pattern2 = "mlx5_core.*Link down"

        cmd1 = f"grep '{pattern1}' {self.log_file}"
        cmd2 = f"grep '{pattern2}' {self.log_file}"

        self.link_data = {}

        for cmd, key in [(cmd1, "failures"), (cmd2, "link_down")]:
            try:
                output = subprocess.check_output(cmd, shell=True, text=True).splitlines()
            except subprocess.CalledProcessError:
                output = []

            for line in output:
                if key == "failures":
                    match = re.search(r"(\w{3}\s+\d+\s+\d+:\d+:\d+)\s+.*?:\s*(\w+): CTRL-EVENT-EAP-FAILURE", line)
                else:
                    match = re.search(r"(\w{3}\s+\d+\s+\d+:\d+:\d+)\s+.*?mlx5_core .*? (\w+): Link down", line)

                if match:
                    time_str, interface = match.groups()
                    logger.debug(f"time: {time_str}, interface: {interface}")
                    if interface not in self.link_data:
                        self.link_data[interface] = {"failures": [], "link_down": []}
                    self.link_data[interface][key].append(time_str)

        logger.debug(f"Link Data: {self.link_data}")
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

                    if last_date_failure.month > current_date.month:
                        last_date_failure = last_date_failure.replace(year=current_date.year - 1)
                    else:
                        last_date_failure = last_date_failure.replace(year=current_date.year)

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

                        if last_date_down.month > current_date.month:
                            last_date_down = last_date_down.replace(year=current_date.year - 1)
                        else:
                            last_date_down = last_date_down.replace(year=current_date.year)

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
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO")
    args = parser.parse_args()

    logger.setLevel(args.log_level)

    lft = LinkFlappingTest(time_interval=6)
    lft.get_rdma_link_failures()
    lft.process_rdma_link_flapping()