import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from logging_config import get_logger

logger = get_logger(__name__)

database_credentials = st.secrets["database"]

DB_USER = database_credentials["username"]
DB_PASSWORD = database_credentials["password"]
DB_HOST = database_credentials.get("host", "localhost")
DB_PORT = database_credentials.get("port", 5432)
DB_NAME = database_credentials.get("database", "POSDB")

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)


def test_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            return result.fetchone()[0] == 1

    except Exception:
        logger.exception("Database connection test failed")
        return False