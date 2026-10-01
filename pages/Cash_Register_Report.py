import streamlit as st
from logging_config import log_exception
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_role

# =========================================================
# ACCESS
# =========================================================
user = require_role("Manager", "Admin")

#st.title("💰 Cash Register & Daily Closing")
st.caption(f"Logged in as: {user['FullName']} • {user['Role']}")

# =========================================================
# SELECT DATE
# =========================================================
selected_date = st.date_input(
    "📅 Business Date",
    value=pd.Timestamp.today().date()
)

# =========================================================
# CASHIER / DRAWER HISTORY
# =========================================================
st.subheader("📋 Cash Register History")

try:
    drawers = pd.read_sql(
        text("""
            SELECT
                cd.CashDrawerID,
                cd.UserID,
                u.FullName AS Cashier,
                cd.OpenDateTime,
                cd.ClosingDateTime,
                cd.OpeningCash,
                cd.ExpectedCash,
                cd.ActualCash,
                cd.DifferenceAmount,
                cd.Status,
                cd.Notes
            FROM CashDrawers cd
            INNER JOIN Users u
                ON u.UserID = cd.UserID
            WHERE CAST(cd.OpenDateTime AS DATE) = :business_date
            ORDER BY cd.CashDrawerID DESC
        """),
        engine,
        params={"business_date": selected_date}
    )

except Exception as e:
    st.error("Unable to load cash register history.")
    log_exception(e)
    st.exception(e)
    st.stop()

if drawers.empty:
    st.info("No cash drawer records found for this date.")
else:

    # =====================================================
    # SUMMARY
    # =====================================================
    opened = float(drawers["OpeningCash"].fillna(0).sum())
    expected = float(drawers["ExpectedCash"].fillna(0).sum())
    actual = float(drawers["ActualCash"].fillna(0).sum())
    difference = float(drawers["DifferenceAmount"].fillna(0).sum())

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Opening Cash", f"₹{opened:,.2f}")
    c2.metric("Expected Cash", f"₹{expected:,.2f}")
    c3.metric("Actual Cash", f"₹{actual:,.2f}")

    if difference > 0:
        c4.metric("Excess Cash", f"₹{difference:,.2f}")
    elif difference < 0:
        c4.metric("Shortage", f"₹{abs(difference):,.2f}")
    else:
        c4.metric("Difference", "₹0.00")

    # =====================================================
    # DRAWER TABLE
    # =====================================================
    display = drawers.copy()

    display["OpeningCash"] = display["OpeningCash"].map(
        lambda x: f"₹{float(x or 0):,.2f}"
    )

    display["ExpectedCash"] = display["ExpectedCash"].map(
        lambda x: f"₹{float(x or 0):,.2f}"
    )

    display["ActualCash"] = display["ActualCash"].map(
        lambda x: f"₹{float(x or 0):,.2f}"
    )

    display["DifferenceAmount"] = display["DifferenceAmount"].map(
        lambda x: f"₹{float(x or 0):,.2f}"
    )

    st.dataframe(
        display[
            [
                "CashDrawerID",
                "Cashier",
                "OpenDateTime",
                "ClosingDateTime",
                "OpeningCash",
                "ExpectedCash",
                "ActualCash",
                "DifferenceAmount",
                "Status",
                "Notes"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# SALES BY CASHIER
# =========================================================
st.divider()
st.subheader("🧾 Cash Sales by Cashier")

try:
    cashier_sales = pd.read_sql(
        text("""
            SELECT
                u.FullName AS Cashier,
                COUNT(s.SaleID) AS CashBills,
                COALESCE(SUM(s.GrandTotal), 0) AS CashSales
            FROM Sales s
            INNER JOIN Users u
                ON u.UserID = s.UserID
            WHERE CAST(s.SaleDate AS DATE) = :business_date
              AND s.PaymentMode = 'Cash'
            GROUP BY u.FullName
            ORDER BY CashSales DESC
        """),
        engine,
        params={"business_date": selected_date}
    )

    if cashier_sales.empty:
        st.info("No cash sales found for this date.")
    else:
        cashier_sales["CashSales"] = cashier_sales["CashSales"].map(
            lambda x: f"₹{float(x or 0):,.2f}"
        )

        st.dataframe(
            cashier_sales,
            use_container_width=True,
            hide_index=True
        )

except Exception as e:
    st.error("Unable to load cashier sales.")
    log_exception(e)
    st.exception(e)

# =========================================================
# CASH TRANSACTIONS
# =========================================================
st.divider()
st.subheader("💸 Cash Expenses / Cash In / Cash Out")

try:
    transactions = pd.read_sql(
        text("""
            SELECT
                ct.CashTransactionID,
                u.FullName AS Cashier,
                ct.TransactionType,
                ct.Amount,
                ct.Reason,
                ct.TransactionDateTime
            FROM CashTransactions ct
            INNER JOIN Users u
                ON u.UserID = ct.UserID
            INNER JOIN CashDrawers cd
                ON cd.CashDrawerID = ct.CashDrawerID
            WHERE CAST(ct.TransactionDateTime AS DATE) = :business_date
            ORDER BY ct.CashTransactionID DESC
        """),
        engine,
        params={"business_date": selected_date}
    )

    if transactions.empty:
        st.info("No manual cash transactions found.")
    else:
        transactions["Amount"] = transactions["Amount"].map(
            lambda x: f"₹{float(x or 0):,.2f}"
        )

        st.dataframe(
            transactions,
            use_container_width=True,
            hide_index=True
        )

except Exception as e:
    st.error("Unable to load cash transactions.")
    log_exception(e)
    st.exception(e)

# =========================================================
# CSV EXPORT
# =========================================================
st.divider()

if not drawers.empty:

    csv = drawers.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download Cash Register CSV",
        data=csv,
        file_name=f"cash_register_{selected_date}.csv",
        mime="text/csv",
        use_container_width=True
    )
