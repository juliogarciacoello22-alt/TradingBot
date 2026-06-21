import logging
import os
from core.biumolo_config import BASIC_LOG_ONLY

logger = logging.getLogger("biumolo")
logger.setLevel(logging.INFO if BASIC_LOG_ONLY else logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s — %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

log_file = os.path.join(os.getcwd(), "biumolo.log")
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log(message, level="INFO"):
    level = level.upper()

    if level == "DEBUG":
        logger.debug(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "ERROR":
        logger.error(message)
    else:
        logger.info(message)
