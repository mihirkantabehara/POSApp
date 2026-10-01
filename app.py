import streamlit as st
from logging_config import get_logger

logger = get_logger(__name__)

import hashlib
import hmac
from sqlalchemy import text
from database.database import engine
from auth import ROLE_PERMISSIONS


st.set_page_config(
    page_title="POS System",
    page_icon="🧾",
    layout="wide",
)


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_login(username, password):
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT
                        UserID,
                        Username,
                        PasswordHash,
                        FullName,
                        Role,
                        IsActive
                    FROM Users
                    WHERE Username = :username
                """),
                {"username": username.strip()},
            ).mappings().first()

        if not row:
            return None

        if not bool(row["IsActive"]):
            return None

        stored_hash = str(row["PasswordHash"])

        if hmac.compare_digest(hash_password(password), stored_hash):
        #if hmac.compare_digest('abc', 'abc'):
            return {
                "UserID": int(row["UserID"]),
                "Username": str(row["Username"]),
                "FullName": str(row["FullName"]),
                "Role": str(row["Role"]),
            }

    except Exception:
        logger.exception("Login lookup failed")
        return None

    return None


def show_login():

    st.markdown(
        """
        <div style="text-align:center; margin-top:60px;">
            <h1>🧾 POS System</h1>
            <p>Please login to continue</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 1.2, 1])

    with center:
        with st.form("login_form"):
            username = st.text_input(
                "Username",
                placeholder="Enter username"
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password"
            )

            submitted = st.form_submit_button(
                "🔐 Login",
                use_container_width=True,
                type="primary"
            )

        if submitted:
            if not username or not password:
                st.warning("Please enter username and password.")
                return

            user = check_login(username, password)

            if user:
                logger.info(
                    "login_succeeded user_id=%s role=%s",
                    user["UserID"],
                    user["Role"],
                )
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                logger.warning("login_rejected")
                st.error(
                    "Invalid username, password, or inactive user."
                )

def logout():
    user = st.session_state.get("user") or {}
    logger.info(
        "logout user_id=%s role=%s",
        user.get("UserID", "unknown"),
        user.get("Role", "unknown"),
    )
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


# -----------------------------
# LOGIN
# -----------------------------
if not st.session_state.get("logged_in"):

    # Hide sidebar/navigation before login
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }

        [data-testid="stSidebarCollapsedControl"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    show_login()
    st.stop()


# -----------------------------
# CURRENT USER
# -----------------------------
user = st.session_state["user"]
role = user["Role"]
permissions = ROLE_PERMISSIONS.get(role, {})


# -----------------------------
# SIDEBAR USER INFO
# -----------------------------
with st.sidebar:
    st.title("🧾 POS System")
    st.divider()

    st.write(f"**User:** {user['FullName']}")
    st.write(f"**Role:** {role}")

    st.divider()

    if st.button("🚪 Logout", use_container_width=True):
        logout()


# -----------------------------
# ROLE-BASED NAVIGATION
# -----------------------------
pages = []

pages.append(
    st.Page(
        "pages/Dashboard.py",
        title="Dashboard",
        icon="🏠",
        default=True,
    )
)

if permissions.get("billing"):
    pages.append(
        st.Page(
            "pages/Billing.py",
            title="Billing",
            icon="🧾",
        )
    )
if permissions.get("billing"):
    pages.append(
        st.Page(
            "pages/Sales_Return.py",
            title="Sales Return",
            icon="↩️",
        )
    )
if permissions.get("products"):
    pages.append(
        st.Page(
            "pages/Products.py",
            title="Products",
            icon="📦",
        )
    )
if permissions.get("products"):
    pages.append(
        st.Page(
            "pages/Batch_Stock_In.py",
            title="Batch Stock In",
            icon="📦"
        )
    )

if permissions.get("customers"):
    pages.append(
        st.Page(
            "pages/Customers.py",
            title="Customers",
            icon="👥",
        )
    )

if permissions.get("reports"):
    pages.append(
        st.Page(
            "pages/Reports.py",
            title="Reports",
            icon="📊",
        )
    )

if permissions.get("users"):
    pages.append(
        st.Page(
            "pages/Users.py",
            title="User Management",
            icon="👤",
        )
    )

if permissions.get("Cash_In_Hand"):
    pages.append(
        st.Page(
            "pages/Cash_In_Hand.py",
            title="Cash in Hand",
            icon="💵",
        )
    )

if permissions.get("cash_register"):
    pages.append(
        st.Page(
            "pages/Cash_Register_Report.py",
            title="Cash Register",
            icon="📋",
        )
    )
if permissions.get("stock_audit"):
    pages.append(
        st.Page(
            "pages/Stock_Loss_Audit.py",
            title="Stock Loss & Audit",
            icon="🔍",
        )
    )
if permissions.get("admin_sales_report"):
    pages.append(
        st.Page(
            "pages/Admin_Sales_Report.py",
            title="Admin Sales Report",
            icon="🔍",
        )
    )
if permissions.get("salesboy_sales_report"):
    pages.append(
        st.Page(
            "pages/Salesboy_Sales_Report.py",
            title="My Sales Report",
            icon="🔍",
        )
    )   
pg = st.navigation(pages)
pg.run()
