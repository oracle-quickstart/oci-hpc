#!/usr/bin/env python3

import logging
import os
logging.basicConfig(level="INFO", format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nhc')


if os.geteuid() == 0:
    file_handler = logging.FileHandler("/tmp/latest_healthcheck.log",mode='w')
    logger.addHandler(file_handler)
