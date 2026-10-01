import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIRECTORY = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIRECTORY / "posapp.log"


def configure_logging():
    logger = logging.getLogger("posapp")
    if getattr(logger, "_posapp_configured", False):
        return logger

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._posapp_configured = True
    return logger


def get_logger(name):
    configure_logging()
    return logging.getLogger(f"posapp.{name}")


def log_exception(error):
    get_logger("pages").error(
        "page_exception",
        exc_info=(type(error), error, error.__traceback__),
    )


def log_page_view(page_name, user):
    import streamlit as st

    if st.session_state.get("_posapp_last_logged_page") == page_name:
        return

    get_logger("navigation").info(
        "page_view page=%s user_id=%s role=%s",
        page_name,
        user.get("UserID", "unknown"),
        user.get("Role", "unknown"),
    )
    st.session_state["_posapp_last_logged_page"] = page_name