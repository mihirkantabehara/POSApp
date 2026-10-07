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

# st.title("💰 Cash Register & Daily Closing")
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
                cd."CashDrawerID",
                cd."UserID",
                u."FullName" AS "Cashier",
                cd."OpenDateTime",
                cd."ClosingDateTime",
                cd."OpeningCash",
                cd."ExpectedCash",
                cd."ActualCash",
                cd."DifferenceAmount",
                cd."Status",
                cd."Notes"
            FROM "CashDrawers" cd
            INNER JOIN "Users" u
                ON u."UserID" = cd."UserID"
            WHERE CAST(cd."OpenDateTime" AS DATE) = :business_date
            ORDER BY cd."CashDrawerID" DESC
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