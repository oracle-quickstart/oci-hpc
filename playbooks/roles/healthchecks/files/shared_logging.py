#!/usr/bin/env python3

import logging
logging.basicConfig(level="INFO", format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nhc')

file_handler = logging.FileHandler("/tmp/latest_healthcheck.log",mode='w')
logger.addHandler(file_handler)
