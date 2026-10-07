import pyodbc
import psycopg
from psycopg import sql
from getpass import getpass
from decimal import Decimal
from datetime import datetime, date, time
from collections import defaultdict, deque


# ============================================================
# CONFIGURATION
# ============================================================

SQL_SERVER = r".\SQLEXPRESS"
SQL_DATABASE = "POSDB"

PG_HOST = "localhost"
PG_PORT = 5432
PG_DATABASE = "POSDB"
PG_USER = "postgres"


# ============================================================
# SQL SERVER CONNECTION
# ============================================================

sql_connection_string = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


print("=" * 70)
print(" SQL SERVER -> POSTGRESQL POSDB MIGRATION")
print("=" * 70)

print("\nConnecting to SQL Server...")

sql_conn = pyodbc.connect(
    sql_connection_string,
    timeout=10
)

sql_cursor = sql_conn.cursor()

print("SQL Server connected successfully.")


# ============================================================
# POSTGRES PASSWORD
# ============================================================

PG_PASSWORD = getpass("Enter PostgreSQL password for user 'postgres': ")


print("\nConnecting to PostgreSQL...")

pg_conn = psycopg.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DATABASE,
    user=PG_USER,
    password=PG_PASSWORD,
    connect_timeout=10,
)

pg_cursor = pg_conn.cursor()

print("PostgreSQL connected successfully.")


# ============================================================
# GET TABLES
# ============================================================

print("\nReading SQL Server tables...")

sql_cursor.execute("""
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_NAME
""")

tables = [(row[0], row[1]) for row in sql_cursor.fetchall()]

print(f"Found {len(tables)} tables.")

for schema, table in tables:
    print("  -", table)


# ============================================================
# GET COLUMNS
# ============================================================

sql_cursor.execute("""
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMNPROPERTY(
        OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME),
        COLUMN_NAME,
        'IsIdentity'
    ) AS IsIdentity,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_NAME, ORDINAL_POSITION
""")

column_rows = sql_cursor.fetchall()

columns = defaultdict(list)

for row in column_rows:
    (
        schema,
        table,
        column,
        data_type,
        char_length,
        numeric_precision,
        numeric_scale,
        nullable,
        default_value,
        is_identity,
        ordinal_position,
    ) = row

    columns[table].append({
        "name": column,
        "data_type": data_type.lower(),
        "char_length": char_length,
        "numeric_precision": numeric_precision,
        "numeric_scale": numeric_scale,
        "nullable": nullable == "YES",
        "default": default_value,
        "identity": bool(is_identity),
    })


# ============================================================
# SQL SERVER TYPE -> POSTGRES TYPE
# ============================================================

def postgres_type(column):

    data_type = column["data_type"]
    length = column["char_length"]
    precision = column["numeric_precision"]
    scale = column["numeric_scale"]

    if data_type == "bigint":
        return "BIGINT"

    if data_type == "int":
        return "INTEGER"

    if data_type == "smallint":
        return "SMALLINT"

    if data_type == "tinyint":
        return "SMALLINT"

    if data_type == "bit":
        return "BOOLEAN"

    if data_type in ("decimal", "numeric"):
        if precision:
            if scale is not None:
                return f"NUMERIC({precision},{scale})"
            return f"NUMERIC({precision})"
        return "NUMERIC"

    if data_type == "money":
        return "NUMERIC(19,4)"

    if data_type == "smallmoney":
        return "NUMERIC(10,4)"

    if data_type in ("float",):
        return "DOUBLE PRECISION"

    if data_type == "real":
        return "REAL"

    if data_type in ("nvarchar", "nchar"):
        if length == -1:
            return "TEXT"
        return f"VARCHAR({length})"

    if data_type in ("varchar", "char"):
        if length == -1:
            return "TEXT"
        return f"VARCHAR({length})"

    if data_type == "text":
        return "TEXT"

    if data_type == "ntext":
        return "TEXT"

    if data_type == "date":
        return "DATE"

    if data_type in ("datetime", "datetime2", "smalldatetime"):
        return "TIMESTAMP"

    if data_type == "datetimeoffset":
        return "TIMESTAMPTZ"

    if data_type == "time":
        return "TIME"

    if data_type in ("binary", "varbinary", "image"):
        return "BYTEA"

    if data_type == "uniqueidentifier":
        return "UUID"

    if data_type == "xml":
        return "TEXT"

    # Safe fallback
    print(
        f"WARNING: Unknown SQL Server type '{data_type}' "
        f"for column '{column['name']}'. Using TEXT."
    )

    return "TEXT"


# ============================================================
# GET PRIMARY KEYS
# ============================================================

print("\nReading primary keys...")

sql_cursor.execute("""
SELECT
    tc.TABLE_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
WHERE tc.TABLE_SCHEMA = 'dbo'
  AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
ORDER BY tc.TABLE_NAME, kcu.ORDINAL_POSITION
""")

primary_keys = defaultdict(list)

for row in sql_cursor.fetchall():
    table, column, position = row
    primary_keys[table].append(column)


# ============================================================
# GET UNIQUE CONSTRAINTS
# ============================================================

print("Reading unique constraints...")

sql_cursor.execute("""
SELECT
    tc.CONSTRAINT_NAME,
    tc.TABLE_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
WHERE tc.TABLE_SCHEMA = 'dbo'
  AND tc.CONSTRAINT_TYPE = 'UNIQUE'
ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
""")

unique_constraints = defaultdict(list)

for row in sql_cursor.fetchall():
    constraint_name, table, column, position = row
    unique_constraints[(table, constraint_name)].append(column)


# ============================================================
# GET FOREIGN KEYS
# ============================================================

print("Reading foreign keys...")

sql_cursor.execute("""
SELECT
    fk.name AS ForeignKeyName,
    OBJECT_NAME(fk.parent_object_id) AS ChildTable,
    COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS ChildColumn,
    OBJECT_NAME(fk.referenced_object_id) AS ParentTable,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ParentColumn
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc
    ON fk.object_id = fkc.constraint_object_id
ORDER BY ChildTable, ForeignKeyName
""")

foreign_keys = []

for row in sql_cursor.fetchall():
    (
        fk_name,
        child_table,
        child_column,
        parent_table,
        parent_column,
    ) = row

    foreign_keys.append({
        "name": fk_name,
        "child_table": child_table,
        "child_column": child_column,
        "parent_table": parent_table,
        "parent_column": parent_column,
    })


# ============================================================
# GET SQL SERVER DEFAULTS
# ============================================================

def convert_default(default_value, data_type):

    if not default_value:
        return None

    value = str(default_value).strip()

    # Remove SQL Server's outer parentheses
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()

    lower = value.lower()

    # Date/time defaults
    if "getdate()" in lower:
        return "CURRENT_TIMESTAMP"

    if "getutcdate()" in lower:
        return "CURRENT_TIMESTAMP"

    # NULL
    if lower == "null":
        return None

    # BIT columns: SQL Server 0/1 -> PostgreSQL FALSE/TRUE
    if data_type == "bit":

        if lower in ("0", "false"):
            return "FALSE"

        if lower in ("1", "true"):
            return "TRUE"

    # String defaults
    if lower.startswith("n'") and value.endswith("'"):
        return value[1:]

    if value.startswith("'") and value.endswith("'"):
        return value

    # Numeric defaults
    if data_type in (
        "int",
        "bigint",
        "smallint",
        "tinyint",
        "decimal",
        "numeric",
        "money",
        "smallmoney",
        "float",
        "real",
    ):
        try:
            Decimal(value)
            return value
        except Exception:
            return None

    return None

# ============================================================
# DROP EXISTING POSTGRES TABLES
# ============================================================

print("\nChecking PostgreSQL POSDB...")

print("""
IMPORTANT:
The PostgreSQL POSDB database will be cleared before migration.
The SQL Server POSDB database will NOT be changed.
""")

answer = input(
    "Type MIGRATE to continue, or anything else to cancel: "
).strip()

if answer != "MIGRATE":
    print("\nMigration cancelled.")
    sql_conn.close()
    pg_conn.close()
    raise SystemExit


# Disable foreign-key checks by dropping existing tables
print("\nRemoving existing PostgreSQL tables...")

for _, table in reversed(tables):

    pg_cursor.execute(
        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
            sql.Identifier(table)
        )
    )

pg_conn.commit()

print("PostgreSQL tables cleared.")


# ============================================================
# CREATE TABLES
# ============================================================

print("\nCreating PostgreSQL tables...")

for _, table in tables:

    definitions = []

    for column in columns[table]:

        column_name = column["name"]

        pg_type = postgres_type(column)

        if column["identity"]:
            definition = (
                sql.SQL("{} {} GENERATED BY DEFAULT AS IDENTITY")
                .format(
                    sql.Identifier(column_name),
                    sql.SQL(pg_type),
                )
            )
        else:
            definition = sql.SQL("{} {}").format(
                sql.Identifier(column_name),
                sql.SQL(pg_type),
            )

        if not column["nullable"]:
            definition += sql.SQL(" NOT NULL")

        default_value = convert_default(
                column["default"],
                column["data_type"]
            )

        if default_value:
            definition += sql.SQL(" DEFAULT " + default_value)

        definitions.append(definition)

    # Primary key
    if table in primary_keys:

        pk_columns = [
            sql.Identifier(column)
            for column in primary_keys[table]
        ]

        definitions.append(
            sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(pk_columns)
            )
        )

    # Unique constraints
    for (constraint_table, constraint_name), constraint_columns in unique_constraints.items():

        if constraint_table != table:
            continue

        columns_sql = [
            sql.Identifier(column)
            for column in constraint_columns
        ]

        definitions.append(
            sql.SQL("CONSTRAINT {} UNIQUE ({})").format(
                sql.Identifier(constraint_name),
                sql.SQL(", ").join(columns_sql)
            )
        )

    create_sql = sql.SQL(
        "CREATE TABLE {} ({})"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(definitions),
    )

    pg_cursor.execute(create_sql)

    print("  Created:", table)


pg_conn.commit()


# ============================================================
# DETERMINE INSERT ORDER
# ============================================================

print("\nDetermining table dependency order...")

table_names = [table for _, table in tables]

dependencies = defaultdict(set)
dependents = defaultdict(set)

for fk in foreign_keys:

    child = fk["child_table"]
    parent = fk["parent_table"]

    if child != parent:
        dependencies[child].add(parent)
        dependents[parent].add(child)


in_degree = {
    table: len(dependencies[table])
    for table in table_names
}

queue = deque(
    table
    for table in table_names
    if in_degree[table] == 0
)

insert_order = []

while queue:

    table = queue.popleft()

    insert_order.append(table)

    for child in dependents[table]:

        in_degree[child] -= 1

        if in_degree[child] == 0:
            queue.append(child)


# If there are cycles, append remaining tables
if len(insert_order) != len(table_names):

    print(
        "WARNING: Circular dependency detected. "
        "Using remaining tables afterward."
    )

    for table in table_names:

        if table not in insert_order:
            insert_order.append(table)


print("\nInsert order:")

for index, table in enumerate(insert_order, start=1):
    print(f"  {index:02d}. {table}")


# ============================================================
# COPY DATA
# ============================================================

print("\nCopying data...")
print("-" * 70)

total_rows = 0

for table in insert_order:

    column_list = [column["name"] for column in columns[table]]

    column_sql = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in column_list
    )

    placeholders = sql.SQL(", ").join(
        sql.Placeholder()
        for _ in column_list
    )

    insert_query = sql.SQL(
        "INSERT INTO {} ({}) VALUES ({})"
    ).format(
        sql.Identifier(table),
        column_sql,
        placeholders,
    )

    # Read SQL Server data
    sql_cursor.execute(
        "SELECT " +
        ", ".join(
            f"[{column}]"
            for column in column_list
        ) +
        f" FROM [dbo].[{table}]"
    )

    rows = sql_cursor.fetchall()

    row_count = len(rows)

    if row_count == 0:

        print(f"{table}: 0 rows")

        continue

    inserted = 0

    for row in rows:

        values = list(row)

        # Convert SQL Server BIT values
        for index, column in enumerate(columns[table]):

            if column["data_type"] == "bit":

                if values[index] is not None:
                    values[index] = bool(values[index])

        pg_cursor.execute(
            insert_query,
            values
        )

        inserted += 1

        if inserted % 500 == 0:

            print(
                f"  {table}: {inserted}/{row_count}"
            )

    pg_conn.commit()

    total_rows += row_count

    print(
        f"{table}: {row_count} rows copied"
    )


# ============================================================
# CREATE FOREIGN KEYS
# ============================================================

print("\nCreating foreign keys...")

for fk in foreign_keys:

    statement = sql.SQL("""
        ALTER TABLE {}
        ADD CONSTRAINT {}
        FOREIGN KEY ({})
        REFERENCES {} ({})
    """).format(
        sql.Identifier(fk["child_table"]),
        sql.Identifier(fk["name"]),
        sql.Identifier(fk["child_column"]),
        sql.Identifier(fk["parent_table"]),
        sql.Identifier(fk["parent_column"]),
    )

    pg_cursor.execute(statement)

    print(
        f"  {fk['child_table']}.{fk['child_column']} "
        f"-> {fk['parent_table']}.{fk['parent_column']}"
    )

pg_conn.commit()


# ============================================================
# RESET IDENTITY SEQUENCES
# ============================================================

print("\nResetting identity columns...")

for _, table in tables:

    for column in columns[table]:

        if not column["identity"]:
            continue

        column_name = column["name"]

        # Find maximum existing ID
        pg_cursor.execute(
            sql.SQL("""
                SELECT MAX({})
                FROM {}
            """).format(
                sql.Identifier(column_name),
                sql.Identifier(table),
            )
        )

        result = pg_cursor.fetchone()
        max_value = result[0]

        if max_value is None:
            next_value = 1
        else:
            next_value = int(max_value) + 1

        # Reset PostgreSQL identity safely
        pg_cursor.execute(
            sql.SQL("""
                ALTER TABLE {}
                ALTER COLUMN {}
                RESTART WITH {}
            """).format(
                sql.Identifier(table),
                sql.Identifier(column_name),
                sql.Literal(next_value),
            )
        )

        print(
            f"  {table}.{column_name} -> next value {next_value}"
        )

pg_conn.commit()


# ============================================================
# VERIFY ROW COUNTS
# ============================================================

print("\n")
print("=" * 70)
print(" VERIFYING DATA")
print("=" * 70)

verification_failed = False

for _, table in tables:

    sql_cursor.execute(
        f"SELECT COUNT(*) FROM [dbo].[{table}]"
    )

    sql_count = sql_cursor.fetchone()[0]

    pg_cursor.execute(
        sql.SQL(
            "SELECT COUNT(*) FROM {}"
        ).format(
            sql.Identifier(table)
        )
    )

    pg_count = pg_cursor.fetchone()[0]

    if sql_count == pg_count:

        print(
            f"OK   {table:<30} "
            f"SQL={sql_count:<8} "
            f"PG={pg_count}"
        )

    else:

        verification_failed = True

        print(
            f"FAIL {table:<30} "
            f"SQL={sql_count:<8} "
            f"PG={pg_count}"
        )


# ============================================================
# FINISH
# ============================================================

print("\n" + "=" * 70)

if verification_failed:

    print("MIGRATION COMPLETED WITH ROW COUNT DIFFERENCES")

else:

    print("MIGRATION COMPLETED SUCCESSFULLY")

print(f"Total source rows: {total_rows}")

print("=" * 70)


sql_conn.close()
pg_conn.close()

print("\nConnections closed.")
print("SQL Server POSDB was not modified.")