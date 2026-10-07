import streamlit as st
import pandas as pd
import hashlib
from sqlalchemy import text
from database.database import engine
from auth import require_role

st.set_page_config(
    page_title="User Management",
    page_icon="👥",
    layout="wide"
)

require_role("Admin")


# =========================================================
# PASSWORD HELPER
# =========================================================

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# =========================================================
# USER DATABASE FUNCTIONS
# =========================================================

def create_user(username, password, full_name, role):
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO "Users"
                    ("Username", "PasswordHash", "FullName", "Role", "IsActive")
                VALUES
                    (:username, :password_hash, :full_name, :role, TRUE)
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
                UPDATE "Users"
                SET
                    "FullName" = :full_name,
                    "Role" = :role,
                    "IsActive" = :is_active
                WHERE "UserID" = :user_id
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
                UPDATE "Users"
                SET "PasswordHash" = :password_hash
                WHERE "UserID" = :user_id
            """),
            {
                "user_id": int(user_id),
                "password_hash": hash_password(new_password),
            },
        )


# =========================================================
# PAGE
# =========================================================

st.title("👥 User Management")
st.caption("Manage Sales Boy, Manager and Admin accounts.")


# =========================================================
# ADD NEW USER
# =========================================================

st.subheader("➕ Add New User")

with st.form("add_user_form", clear_on_submit=True):

    c1, c2 = st.columns(2)

    with c1:
        username = st.text_input("Username")
        full_name = st.text_input("Full Name")

    with c2:
        password = st.text_input("Password", type="password")
        role = st.selectbox(
            "Role",
            ["Sales Boy", "Manager", "Admin"]
        )

    submitted = st.form_submit_button(
        "Create User",
        use_container_width=True,
        type="primary"
    )


if submitted:

    if not username.strip() or not full_name.strip() or not password:
        st.warning("Please fill all fields.")

    elif len(password) < 6:
        st.warning("Password must contain at least 6 characters.")

    else:
        try:
            create_user(
                username,
                password,
                full_name,
                role
            )

            st.success("User created successfully.")
            st.rerun()

        except Exception as e:
            st.error(
                "Could not create user. Username may already exist."
            )
            st.exception(e)


# =========================================================
# EXISTING USERS
# =========================================================

st.divider()
st.subheader("👤 Existing Users")


try:

    users_query = text("""
        SELECT
            "UserID",
            "Username",
            "FullName",
            "Role",
            "IsActive",
            "CreatedDate"
        FROM "Users"
        ORDER BY "UserID"
    """)

    with engine.connect() as connection:
        users = pd.read_sql(users_query, connection)

    st.dataframe(
        users,
        use_container_width=True,
        hide_index=True
    )


    # =====================================================
    # EDIT USER
    # =====================================================

    if not users.empty:

        st.divider()
        st.subheader("✏️ Edit User")

        labels = {
            f"{r.Username} — {r.FullName}": int(r.UserID)
            for _, r in users.iterrows()
        }

        label = st.selectbox(
            "Select User",
            list(labels.keys())
        )

        uid = labels[label]

        row = users[
            users["UserID"] == uid
        ].iloc[0]


        c1, c2, c3 = st.columns(3)

        with c1:
            name = st.text_input(
                "Full Name",
                value=str(row["FullName"]),
                key=f"name_{uid}"
            )

        with c2:
            roles = [
                "Sales Boy",
                "Manager",
                "Admin"
            ]

            current_role = str(row["Role"])

            role_index = (
                roles.index(current_role)
                if current_role in roles
                else 0
            )

            role_edit = st.selectbox(
                "Role",
                roles,
                index=role_index,
                key=f"role_{uid}"
            )

        with c3:
            active = st.checkbox(
                "Account Active",
                value=bool(row["IsActive"]),
                key=f"active_{uid}"
            )


        if st.button(
            "💾 Update User",
            use_container_width=True
        ):

            if not name.strip():
                st.warning("Full Name cannot be empty.")

            else:
                try:

                    update_user(
                        uid,
                        name,
                        role_edit,
                        active
                    )

                    st.success("User updated.")
                    st.rerun()

                except Exception as e:

                    st.error("Could not update user.")
                    st.exception(e)


        # =================================================
        # RESET PASSWORD
        # =================================================

        st.divider()
        st.subheader("🔑 Reset Password")

        new_password = st.text_input(
            "New Password",
            type="password",
            key=f"pw_{uid}"
        )


        if st.button(
            "🔄 Reset Password",
            use_container_width=True
        ):

            if len(new_password) < 6:
                st.warning(
                    "Password must contain at least 6 characters."
                )

            else:

                try:

                    reset_password(
                        uid,
                        new_password
                    )

                    st.success(
                        "Password reset successfully."
                    )

                except Exception as e:

                    st.error(
                        "Could not reset password."
                    )
                    st.exception(e)


except Exception as e:

    st.error("Could not load users.")
    st.exception(e)
