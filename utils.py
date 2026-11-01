import logging
from logging.handlers import RotatingFileHandler
import os

class _SecretFilter(logging.Filter):
    def __init__(self, secret):
        super().__init__()
        self.secret = secret

    def filter(self, record):
        if self.secret:
            record.msg = record.getMessage().replace(self.secret, "[redacted]")
            record.args = ()
        return True


def setup_logging(secret=None):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    path = os.getenv('QBT_LOG_FILE')
    if path and not any(isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers):
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(handler)
    if secret:
        for handler in logging.getLogger().handlers:
            handler.addFilter(_SecretFilter(secret))

def log_info(message: str):
    logging.info(message)

def log_error(message: str):
    logging.error(message)
