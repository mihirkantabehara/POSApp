import streamlit as st
from logging_config import log_exception
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_role

# =========================================================
# ACCESS
# =========================================================
user = require_role("Sales Boy", "Manager", "Admin")

#st.title("💰 Cash in Hand")
st.caption(f"Cashier: {user['FullName']} • {user['Role']}")

# =========================================================
# HELPERS
# =========================================================
def get_open_drawer():
    with engine.connect() as connection:
        return connection.execute(
            text("""
                SELECT TOP 1
                    CashDrawerID,
                    UserID,
                    OpenDateTime,
                    OpeningCash
                FROM CashDrawers
                WHERE UserID = :user_id
                  AND Status = 'Open'
                ORDER BY CashDrawerID DESC
            """),
            {"user_id": user["UserID"]}
        ).mappings().first()


def get_cash_sales(drawer_open_time):
    with engine.connect() as connection:
        value = connection.execute(
            text("""
                SELECT COALESCE(SUM(GrandTotal), 0)
                FROM Sales
                WHERE UserID = :user_id
                  AND PaymentMode = 'Cash'
                  AND SaleDate >= :open_time
            """),
            {
                "user_id": user["UserID"],
                "open_time": drawer_open_time
            }
        ).scalar()
    return float(value or 0)


def get_cash_transactions(drawer_id):
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    CashTransactionID,
                    TransactionType,
                    Amount,
                    Reason,
                    TransactionDateTime
                FROM CashTransactions
                WHERE CashDrawerID = :drawer_id
                ORDER BY CashTransactionID DESC
            """),
            {"drawer_id": drawer_id}
        )
        return pd.DataFrame(result.fetchall(), columns=result.keys())


# =========================================================
# CURRENT DRAWER
# =========================================================
try:
    drawer = get_open_drawer()
except Exception as e:
    st.error("Cash module tables are not available yet.")
    st.info("Run the supplied cash_in_hand.sql file in SQL Server Management Studio first.")
    log_exception(e)
    st.exception(e)
    st.stop()

# =========================================================
# OPEN DRAWER
# =========================================================
if not drawer:

    st.subheader("🔓 Open Cash Drawer")

    st.info(
        "Enter the cash physically available in the drawer before starting billing."
    )

    opening_cash = st.number_input(
        "Opening Cash",
        min_value=0.0,
        value=0.0,
        step=100.0
    )

    notes = st.text_input(
        "Opening Notes",
        placeholder="Optional"
    )

    if st.button(
        "💰 OPEN CASH DRAWER",
        type="primary",
        use_container_width=True
    ):
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO CashDrawers
                        (
                            UserID,
                            OpeningCash,
                            Notes,
                            Status
                        )
                        VALUES
                        (
                            :user_id,
                            :opening_cash,
                            :notes,
                            'Open'
                        )
                    """),
                    {
                        "user_id": user["UserID"],
                        "opening_cash": opening_cash,
                        "notes": notes.strip()
                    }
                )

            st.success("Cash drawer opened successfully.")
            st.rerun()

        except Exception as e:
            st.error("Could not open cash drawer.")
            log_exception(e)
            st.exception(e)

    st.stop()

# =========================================================
# OPEN DRAWER DASHBOARD
# =========================================================
drawer_id = int(drawer["CashDrawerID"])
opening_cash = float(drawer["OpeningCash"])
open_time = drawer["OpenDateTime"]

cash_sales = get_cash_sales(open_time)

transactions = get_cash_transactions(drawer_id)

cash_in = 0.0
cash_out = 0.0

if not transactions.empty:
    cash_in = float(
        transactions.loc[
            transactions["TransactionType"] == "Cash In",
            "Amount"
        ].sum()
    )

    cash_out = float(
        transactions.loc[
            transactions["TransactionType"].isin(
                ["Expense", "Cash Out"]
            ),
            "Amount"
        ].sum()
    )

expected_cash = opening_cash + cash_sales + cash_in - cash_out

# =========================================================
# SUMMARY
# =========================================================
st.subheader("📊 Current Cash Position")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Opening Cash", f"₹{opening_cash:,.2f}")
c2.metric("Cash Sales", f"₹{cash_sales:,.2f}")
c3.metric("Expenses / Cash Out", f"₹{cash_out:,.2f}")
c4.metric("Expected Cash", f"₹{expected_cash:,.2f}")

st.caption(f"Drawer opened: {open_time}")

# =========================================================
# CASH EXPENSE / CASH IN
# =========================================================
st.divider()
st.subheader("➕ / ➖ Cash Transaction")

transaction_type = st.radio(
    "Transaction Type",
    ["Expense", "Cash In", "Cash Out"],
    horizontal=True
)

amount = st.number_input(
    "Amount",
    min_value=0.01,
    value=100.0,
    step=10.0
)

reason = st.text_input(
    "Reason",
    placeholder="Example: Tea expense / cash received / supplier payment"
)

if st.button(
    "SAVE CASH TRANSACTION",
    use_container_width=True
):
    if not reason.strip():
        st.error("Please enter a reason.")
    else:
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO CashTransactions
                        (
                            CashDrawerID,
                            UserID,
                            TransactionType,
                            Amount,
                            Reason
                        )
                        VALUES
                        (
                            :drawer_id,
                            :user_id,
                            :transaction_type,
                            :amount,
                            :reason
                        )
                    """),
                    {
                        "drawer_id": drawer_id,
                        "user_id": user["UserID"],
                        "transaction_type": transaction_type,
                        "amount": amount,
                        "reason": reason.strip()
                    }
                )

            st.success("Cash transaction saved.")
            st.rerun()

        except Exception as e:
            st.error("Could not save cash transaction.")
            log_exception(e)
            st.exception(e)

# =========================================================
# TRANSACTION HISTORY
# =========================================================
st.divider()
st.subheader("📋 Today's Cash Transactions")

if transactions.empty:
    st.info("No manual cash transactions.")
else:
    st.dataframe(
        transactions,
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# CLOSE DRAWER
# =========================================================
st.divider()
st.subheader("🔒 Close Cash Drawer")

actual_cash = st.number_input(
    "Actual Cash Counted",
    min_value=0.0,
    value=float(expected_cash),
    step=100.0
)

difference = actual_cash - expected_cash

if difference > 0:
    st.info(f"Excess cash: ₹{difference:,.2f}")
elif difference < 0:
    st.warning(f"Cash shortage: ₹{abs(difference):,.2f}")
else:
    st.success("Cash matches expected amount.")

closing_notes = st.text_input(
    "Closing Notes",
    placeholder="Optional"
)

if st.button(
    "🔒 CLOSE CASH DRAWER",
    type="primary",
    use_container_width=True
):
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE CashDrawers
                    SET
                        ClosingDateTime = GETDATE(),
                        ExpectedCash = :expected_cash,
                        ActualCash = :actual_cash,
                        DifferenceAmount = :difference,
                        Status = 'Closed',
                        Notes = CASE
                            WHEN :notes = '' THEN Notes
                            WHEN Notes IS NULL OR Notes = '' THEN :notes
                            ELSE Notes + ' | ' + :notes
                        END
                    WHERE CashDrawerID = :drawer_id
                      AND Status = 'Open'
                """),
                {
                    "drawer_id": drawer_id,
                    "expected_cash": expected_cash,
                    "actual_cash": actual_cash,
                    "difference": difference,
                    "notes": closing_notes.strip()
                }
            )

        st.success("Cash drawer closed successfully.")
        st.rerun()

    except Exception as e:
        st.error("Could not close cash drawer.")
        log_exception(e)
        st.exception(e)
