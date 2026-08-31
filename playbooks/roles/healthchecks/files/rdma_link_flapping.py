#!/usr/bin/env python3

import os
import time
import datetime
import re
import argparse
import subprocess
from shared_logging import logger


class LinkFlappingTest:
    EVENT_THRESHOLD = 2

    def __init__(self, time_interval=6):
        self.results = None
        self.time_interval = int(time_interval)
        self.link_data = None

            
        # Check if the log file exists
        msg_file = "/var/log/messages"
        if not os.path.exists(msg_file):
            msg_file = "/var/log/syslog"
        self.log_file = msg_file

    @staticmethod
    def _reverse_readlines(path, block_size=1024 * 1024):
        with open(path, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            position = log_file.tell()
            buffer = b""
            while position > 0:
                read_size = min(block_size, position)
                position -= read_size
                log_file.seek(position)
                data = log_file.read(read_size) + buffer
                lines = data.split(b"\n")
                buffer = lines[0]
                for line in reversed(lines[1:]):
                    if line:
                        yield line.decode("utf-8", errors="replace")
            if buffer:
                yield buffer.decode("utf-8", errors="replace")

    def get_rdma_link_failures(self):
        timestamp_pattern = (
            r"(?:\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
            r"|"
            r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)"
        )
        interface_pattern = r"([\w.-]+)"
        timestamp_re = re.compile(rf"^({timestamp_pattern})")
        auth_failure_re = re.compile(
            rf"({timestamp_pattern})\s+\S+\s+wpa_supplicant(?:\[\d+\])?: "
            rf"{interface_pattern}: CTRL-EVENT-EAP-FAILURE EAP authentication failed"
        )
        link_down_re = re.compile(
            rf"({timestamp_pattern})\s+\S+\s+kernel: (?:\[\d+\.\d+\]\s)?"
            rf"mlx5_core \S+ {interface_pattern}: Link down"
        )

        self.link_data = {}
        current_date = datetime.datetime.now()
        cutoff = current_date - datetime.timedelta(hours=self.time_interval)
        scanned = 0

        try:
            for line in self._reverse_readlines(self.log_file):
                scanned += 1
                timestamp_match = timestamp_re.match(line)
                if timestamp_match:
                    try:
                        line_time = self.parse_log_timestamp(timestamp_match.group(1), current_date)
                        if line_time < cutoff:
                            break
                    except (ValueError, TypeError):
                        pass

                match = auth_failure_re.search(line)
                if match:
                    time_str = match.group(1)
                    interface = match.group(2)
                    logger.debug(f"time: {time_str}, interface: {interface}")
                    self.link_data.setdefault(interface, {"failures": [], "link_down": []})["failures"].append(time_str)
                    continue

                match = link_down_re.search(line)
                if match:
                    time_str = match.group(1)
                    interface = match.group(2)
                    logger.debug(f"time: {time_str}, interface: {interface}")
                    self.link_data.setdefault(interface, {"failures": [], "link_down": []})["link_down"].append(time_str)
        except FileNotFoundError:
            logger.info(f"No RDMA link failures entry in {self.log_file}")

        for data in self.link_data.values():
            data["failures"].reverse()
            data["link_down"].reverse()

        logger.debug(f"Scanned {scanned} recent lines from {self.log_file}")
        logger.debug("Link Data: {}".format(self.link_data))
        return self.link_data


    @staticmethod
    def parse_log_timestamp(time_str, current_date):
        if "T" in time_str:
            normalized = time_str.replace("Z", "+00:00")
            parsed = datetime.datetime.fromisoformat(normalized)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed

        candidate_dates = []
        for event_year in (current_date.year, current_date.year - 1):
            try:
                candidate_dates.append(
                    datetime.datetime.strptime(
                        f"{event_year} {time_str}",
                        "%Y %b %d %H:%M:%S",
                    )
                )
            except ValueError:
                continue

        if not candidate_dates:
            raise ValueError(f"Invalid syslog timestamp: {time_str}")

        past_dates = [event_date for event_date in candidate_dates if event_date <= current_date]
        return max(past_dates) if past_dates else min(candidate_dates)

    def _recent_events(self, timestamps, current_date, bootup_time_grace_period):
        current_date_sec = int(current_date.timestamp())
        window_start_sec = current_date_sec - (self.time_interval * 60 * 60)
        recent_events = []

        for time_str in timestamps:
            try:
                event_time_sec = int(self.parse_log_timestamp(time_str, current_date).timestamp())
            except ValueError as exc:
                logger.warning(str(exc))
                continue

            if (
                window_start_sec <= event_time_sec <= current_date_sec
                and event_time_sec > bootup_time_grace_period
            ):
                recent_events.append(time_str)

        return recent_events

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

            for interface in self.link_data:
                failure_timestamps = self.link_data[interface]["failures"]
                recent_failures = self._recent_events(
                    failure_timestamps,
                    current_date,
                    bootup_time_grace_period,
                )

                logger.debug(f"{interface}: {len(failure_timestamps)} RDMA authentication failure entries in {self.log_file}")
                logger.debug(f"{interface}: {len(recent_failures)} RDMA authentication failure entries within the past {self.time_interval} hours")

                if len(recent_failures) >= self.EVENT_THRESHOLD:
                    logger.debug(f"{interface}: recent RDMA authentication flap events: {recent_failures}")
                    link_issues["failures"].append(f"{interface}: {len(recent_failures)}")
                    status = -1

            for interface in self.link_data:
                link_down_timestamps = self.link_data[interface]["link_down"]
                recent_link_downs = self._recent_events(
                    link_down_timestamps,
                    current_date,
                    bootup_time_grace_period,
                )

                logger.debug(f"{interface}: {len(link_down_timestamps)} RDMA kernel link-down entries in {self.log_file}")
                logger.debug(f"{interface}: {len(recent_link_downs)} RDMA kernel link-down entries within the past {self.time_interval} hours")

                if len(recent_link_downs) >= self.EVENT_THRESHOLD:
                    logger.debug(f"{interface}: recent RDMA link carrier flap events: {recent_link_downs}")
                    link_issues["link_down"].append(f"{interface}: {len(recent_link_downs)}")
                    status = -2
            if status == -1:
                logger.debug(f"{self.EVENT_THRESHOLD} or more RDMA authentication failures on an interface within the past {self.time_interval} hours")
            if status == -2:
                logger.debug(f"{self.EVENT_THRESHOLD} or more RDMA kernel link-down events on an interface within the past {self.time_interval} hours")

        else:
            logger.info("No RDMA authentication or kernel link-down entries in /var/log/messages")
        if status == 0:    
            logger.info("RDMA authentication/link flap test: Passed")
        else:
            logger.warning("RDMA authentication/link flap test: Failed")
        return link_issues


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process RDMA authentication and link flap data")
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
