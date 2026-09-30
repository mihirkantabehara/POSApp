import streamlit as st
from sqlalchemy import create_engine, text

SERVER = r"localhost\sqlexpress"
DATABASE = "POSDB"

CONNECTION_STRING = (
    "mssql+pyodbc://@"
    + SERVER
    + "/"
    + DATABASE
    + "?driver=ODBC+Driver+18+for+SQL+Server"
    "&trusted_connection=yes"
    "&TrustServerCertificate=yes"
)

engine = create_engine(CONNECTION_STRING)


def test_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            return result.fetchone()[0] == 1

    except Exception as e:
        print("Database error:", e)
        return False