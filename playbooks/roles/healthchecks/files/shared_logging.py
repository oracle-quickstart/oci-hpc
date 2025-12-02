#!/usr/bin/env python3

import logging
import os
import stat
logging.basicConfig(level="INFO", format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nhc')


if os.geteuid() == 0:
    os.makedirs("/var/log/healthchecks", exist_ok=True)
    os.chmod("/var/log/healthchecks", stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

    file_handler = logging.FileHandler("/var/log/healthchecks/latest_healthcheck.log",mode='w')
    logger.addHandler(file_handler)
