import logging
from logging.handlers import RotatingFileHandler


def setup_logging(root):
    folder = root / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kakao")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        folder / "agent.log", maxBytes=2 * 1024**2, backupCount=4, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
