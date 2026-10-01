import streamlit as st
from sqlalchemy import URL, create_engine, text
from logging_config import get_logger

logger = get_logger(__name__)

SERVER = "100.76.103.109"
PORT = 1433
DATABASE = "POSDB"

database_credentials = st.secrets["database"]

CONNECTION_STRING = URL.create(
    "mssql+pyodbc",
    username=database_credentials["username"],
    password=database_credentials["password"],
    host=SERVER,
    port=PORT,
    database=DATABASE,
    query={
        "driver": "ODBC Driver 18 for SQL Server",
        "TrustServerCertificate": "yes",
    },
)

engine = create_engine(CONNECTION_STRING, hide_parameters=True)


def test_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            return result.fetchone()[0] == 1

    except Exception:
        logger.exception("Database connection test failed")
        return False