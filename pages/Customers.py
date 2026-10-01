import streamlit as st
from logging_config import log_exception
import pandas as pd
from database.database import engine


#st.title("👥 Customers")
from auth import require_role
require_role("Manager", "Admin")

# =========================
# ADD CUSTOMER
# =========================

st.subheader("Add Customer")

col1, col2 = st.columns(2)

with col1:
    customer_name = st.text_input("Customer Name")

with col2:
    mobile = st.text_input("Mobile Number")

address = st.text_area("Address")


if st.button("➕ Add Customer"):

    if customer_name.strip() == "":
        st.error("Please enter customer name.")

    else:

        query = """
        INSERT INTO Customers
        (CustomerName, Mobile, Address)
        VALUES (?, ?, ?)
        """

        try:

            with engine.begin() as connection:

                connection.exec_driver_sql(
                    query,
                    (
                        customer_name,
                        mobile,
                        address
                    )
                )

            st.success("Customer added successfully!")

            st.rerun()

        except Exception as e:

            st.error("Error adding customer.")
            log_exception(e)
            st.exception(e)


# =========================
# CUSTOMER LIST
# =========================

st.divider()

st.subheader("Customer List")


try:

    query = """
    SELECT
        CustomerID,
        CustomerName,
        Mobile,
        Address,
        CreatedDate
    FROM Customers
    ORDER BY CustomerID DESC
    """

    df = pd.read_sql(query, engine)

    if df.empty:

        st.info("No customers found.")

    else:

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

except Exception as e:

    st.error("Database connection error.")
    log_exception(e)
    log_exception(e)
    st.exception(e)