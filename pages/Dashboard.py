import streamlit as st
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_login

user = require_login()
role = user["Role"]

#st.title("🏠 POS Dashboard")
st.caption(f"Welcome, {user['FullName']} • {role}")

# =========================================================
# SALES BOY DASHBOARD
# =========================================================
# Sales Boy sees billing-related information only.
if role == "Sales Boy":

    try:
        with engine.connect() as connection:
            sales = connection.execute(text("""
                SELECT
                    COUNT(*) AS TotalBills,
                    COALESCE(SUM(GrandTotal), 0) AS TotalSales
                FROM Sales
                WHERE CAST(SaleDate AS DATE) = CAST(GETDATE() AS DATE)
                  AND UserID = :user_id
            """), {"user_id": user["UserID"]}).mappings().first()

        c1, c2 = st.columns(2)

        c1.metric(
            "My Sales Today",
            f"₹{float(sales['TotalSales'] or 0):,.2f}"
        )

        c2.metric(
            "My Bills Today",
            int(sales["TotalBills"] or 0)
        )

        st.info("Use 🧾 Billing to create new bills.")

    except Exception as e:
        st.error("Unable to load your sales dashboard.")
        st.exception(e)

# =========================================================
# MANAGER / ADMIN DASHBOARD
# =========================================================
else:

    try:
        with engine.connect() as connection:

            sales = connection.execute(text("""
                SELECT
                    COUNT(*) AS TotalBills,
                    COALESCE(SUM(GrandTotal), 0) AS TotalSales
                FROM Sales
                WHERE CAST(SaleDate AS DATE) = CAST(GETDATE() AS DATE)
            """)).mappings().first()

            product_count = connection.execute(text("""
                SELECT COUNT(*) AS ProductCount
                FROM Products
            """)).scalar()

            low_stock_count = connection.execute(text("""
                SELECT COUNT(*) AS LowStock
                FROM Products
                WHERE ISNULL(Stock, 0) <= 10
            """)).scalar()

        # =================================================
        # KPI CARDS
        # =================================================
        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Today's Sales",
            f"₹{float(sales['TotalSales'] or 0):,.2f}"
        )

        c2.metric(
            "Today's Bills",
            int(sales["TotalBills"] or 0)
        )

        c3.metric(
            "Products",
            int(product_count or 0)
        )

        c4.metric(
            "Low Stock",
            int(low_stock_count or 0)
        )

        # =================================================
        # LOW STOCK
        # =================================================
        st.subheader("⚠️ Low Stock Products")

        low_stock = pd.read_sql(text("""
            SELECT
                ProductID,
                ProductName,
                Barcode,
                Stock,
                SellingPrice
            FROM Products
            WHERE ISNULL(Stock, 0) <= 10
            ORDER BY Stock ASC, ProductName
        """), engine)

        if low_stock.empty:
            st.success("No low-stock products.")
        else:
            st.dataframe(
                low_stock,
                use_container_width=True,
                hide_index=True
            )

        # =================================================
        # TODAY'S SALES BY PAYMENT MODE
        # =================================================
        st.subheader("💳 Today's Payment Summary")

        payment_summary = pd.read_sql(text("""
            SELECT
                PaymentMode,
                COUNT(*) AS Bills,
                COALESCE(SUM(GrandTotal), 0) AS Amount
            FROM Sales
            WHERE CAST(SaleDate AS DATE) = CAST(GETDATE() AS DATE)
            GROUP BY PaymentMode
            ORDER BY PaymentMode
        """), engine)

        if payment_summary.empty:
            st.info("No sales recorded today.")
        else:
            st.dataframe(
                payment_summary,
                use_container_width=True,
                hide_index=True
            )

    except Exception as e:
        st.error("Unable to load dashboard data.")
        st.exception(e)
