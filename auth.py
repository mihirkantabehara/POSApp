import streamlit as st
import hashlib
from database.database import engine
from sqlalchemy import text

ROLE_PERMISSIONS = {
    "Sales Boy": {
        "billing": True,
        "products": False,
        "customers": False,
        "reports": False,
        "users": False,
        "Cash_In_Hand": True,
        "cash_register": False,
        "stock_audit": False,
        "admin_sales_report": False,
        "salesboy_sales_report":True,
    },
    "Manager": {
        "billing": False,
        "products": False,
        "customers": True,
        "reports": False,
        "users": False,
        "Cash_In_Hand": False,
        "cash_register": False,
        "stock_audit": False,
        "admin_sales_report": False,
        "salesboy_sales_report":True,
    },
    "Admin": {
        "billing": False,
        "products": True,
        "customers": True,
        "reports": True,
        "users": True,
        "Cash_In_Hand": True,
        "cash_register": True,
        "stock_audit": True,
        "admin_sales_report": True,
        "salesboy_sales_report":False,
    },
}


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def require_login():
    user = st.session_state.get("user")

    if not st.session_state.get("logged_in") or not user:
        st.error("🔒 Please login first.")
        st.stop()

    return user


def require_role(*allowed_roles):
    user = require_login()

    if user["Role"] not in allowed_roles:
        st.error("⛔ You do not have permission to access this page.")
        st.stop()

    return user


def create_user(username, password, full_name, role):
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO Users
                    (Username, PasswordHash, FullName, Role, IsActive)
                VALUES
                    (:username, :password_hash, :full_name, :role, 1)
            """),
            {
                "username": username.strip(),
                "password_hash": hash_password(password),
                "full_name": full_name.strip(),
                "role": role,
            },
        )


def update_user(user_id, full_name, role, is_active):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE Users
                SET FullName = :full_name,
                    Role = :role,
                    IsActive = :is_active
                WHERE UserID = :user_id
            """),
            {
                "user_id": int(user_id),
                "full_name": full_name.strip(),
                "role": role,
                "is_active": bool(is_active),
            },
        )


def reset_password(user_id, new_password):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE Users
                SET PasswordHash = :password_hash
                WHERE UserID = :user_id
            """),
            {
                "user_id": int(user_id),
                "password_hash": hash_password(new_password),
            },
        )
