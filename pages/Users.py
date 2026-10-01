import streamlit as st
from logging_config import log_exception
import pandas as pd
from database.database import engine
from auth import require_role, create_user, update_user, reset_password

st.set_page_config(page_title="User Management", page_icon="👥", layout="wide")
require_role("Admin")

#st.title("👥 User Management")
st.caption("Manage Sales Boy, Manager and Admin accounts.")

st.caption("➕ Add New User")
with st.form("add_user_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        username = st.text_input("Username")
        full_name = st.text_input("Full Name")
    with c2:
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["Sales Boy", "Manager", "Admin"])
    submitted = st.form_submit_button("Create User", use_container_width=True, type="primary")

if submitted:
    if not username.strip() or not full_name.strip() or not password:
        st.warning("Please fill all fields.")
    elif len(password) < 6:
        st.warning("Password must contain at least 6 characters.")
    else:
        try:
            create_user(username, password, full_name, role)
            st.success("User created successfully.")
            st.rerun()
        except Exception as e:
            st.error("Could not create user. Username may already exist.")
            log_exception(e)
            st.exception(e)

st.divider()
st.caption("👤 Existing Users")

try:
    users = pd.read_sql("""
        SELECT UserID, Username, FullName, Role, IsActive, CreatedDate
        FROM Users ORDER BY UserID
    """, engine)

    st.dataframe(users, use_container_width=True, hide_index=True)

    if not users.empty:
        st.divider()
        st.caption("✏️ Edit User")

        labels = {
            f"{r.Username} — {r.FullName}": int(r.UserID)
            for _, r in users.iterrows()
        }
        label = st.selectbox("Select User", list(labels.keys()))
        uid = labels[label]
        row = users[users["UserID"] == uid].iloc[0]

        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Full Name", value=str(row["FullName"]), key=f"name_{uid}")
        with c2:
            roles = ["Sales Boy", "Manager", "Admin"]
            role_edit = st.selectbox("Role", roles, index=roles.index(str(row["Role"])), key=f"role_{uid}")
        with c3:
            active = st.checkbox("Account Active", value=bool(row["IsActive"]), key=f"active_{uid}")

        if st.button("💾 Update User", use_container_width=True):
            try:
                update_user(uid, name, role_edit, active)
                st.success("User updated.")
                st.rerun()
            except Exception as e:
                st.error("Could not update user.")
                log_exception(e)
                st.exception(e)

        st.divider()
        st.caption("🔑 Reset Password")
        new_password = st.text_input("New Password", type="password", key=f"pw_{uid}")

        if st.button("🔄 Reset Password", use_container_width=True):
            if len(new_password) < 6:
                st.warning("Password must contain at least 6 characters.")
            else:
                try:
                    reset_password(uid, new_password)
                    st.success("Password reset successfully.")
                except Exception as e:
                    st.error("Could not reset password.")
                    log_exception(e)
                    st.exception(e)

except Exception as e:
    st.error("Could not load users.")
    log_exception(e)
    st.exception(e)
