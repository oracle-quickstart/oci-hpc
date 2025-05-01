import logging
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("oci").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)