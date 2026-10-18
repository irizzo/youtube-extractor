import logging
from logging.handlers import RotatingFileHandler
import os

EXTRACTION_LOGGER_NAME = "extraction_logger"


def get_pipeline_logger(logger_name="pipeline_logger", log_file="data/pipeline.log"):
    """
    Sets up a logger that streams to both the console and a rotating log file.
    """
    logger = logging.getLogger(logger_name)

    # Check this logger's own handlers only. hasHandlers() also counts the
    # root logger's, so any logging.basicConfig() (a notebook, pytest) would
    # make this return early and the log file would never be created.
    if logger.handlers:
        return logger

    print("Logging into file ", log_file)

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()  # still logs in terminal
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_extraction_logger():
    """Returns the extraction logger, without configuring anything.

    Safe to call at import time: no config read, no directory created, no
    file opened. Until the composition root calls
    configure_extraction_logger(), this logger simply has no handlers.
    """

    return logging.getLogger(EXTRACTION_LOGGER_NAME)


def configure_extraction_logger(log_file):
    """Attaches console and rotating-file handlers to the extraction logger.

    Call once, from whatever composes the run, with a path the caller chose.
    """

    return get_pipeline_logger(EXTRACTION_LOGGER_NAME, log_file)
