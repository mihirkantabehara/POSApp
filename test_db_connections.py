import pyodbc
import psycopg

# =========================
# SQL SERVER
# =========================

SQL_SERVER = r".\SQLEXPRESS"
SQL_DATABASE = "POSDB"

sql_connection_string = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

print("Testing SQL Server...")

try:
    conn = pyodbc.connect(sql_connection_string, timeout=5)
    cursor = conn.cursor()

    cursor.execute("SELECT DB_NAME(), @@VERSION")
    row = cursor.fetchone()

    print("✅ SQL Server connected")
    print("Database:", row[0])

    conn.close()

except Exception as e:
    print("❌ SQL Server connection failed")
    print(e)


# =========================
# POSTGRESQL
# =========================

PG_HOST = "localhost"
PG_PORT = 5432
PG_DATABASE = "POSDB"
PG_USER = "postgres"

# Enter your PostgreSQL password here temporarily
PG_PASSWORD = "Mihir@123"

print("\nTesting PostgreSQL...")

try:
    conn = psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        connect_timeout=5,
    )

    cursor = conn.cursor()

    cursor.execute("SELECT current_database(), version()")
    row = cursor.fetchone()

    print("✅ PostgreSQL connected")
    print("Database:", row[0])

    conn.close()

except Exception as e:
    print("❌ PostgreSQL connection failed")
    print(e)