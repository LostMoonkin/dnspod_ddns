import logging


def get_logger():
    logger = logging.getLogger("ddns_server")
    logger.setLevel(logging.INFO)

    log_file = logging.FileHandler("log.log")
    log_file.setLevel(logging.INFO)

    log_stream = logging.StreamHandler()
    log_stream.setLevel(logging.INFO)

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s : %(message)s")
    log_file.setFormatter(formatter)
    log_stream.setFormatter(formatter)
    logger.addHandler(log_file)
    logger.addHandler(log_stream)

    return logger
