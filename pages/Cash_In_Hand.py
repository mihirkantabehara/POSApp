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


# ---------------------------------------------------------------------------
# Professional POS styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .pos-header {
        padding: 6px 0 14px 0;
        margin-bottom: 8px;
    }
    .pos-title {
        font-size: 1.75rem;
        font-weight: 750;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .pos-subtitle {
        color: #6b7280;
        font-size: 0.9rem;
        margin-top: 3px;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin: 0 0 3px 0;
    }
    .section-help {
        color: #6b7280;
        font-size: 0.82rem;
        margin-bottom: 10px;
    }
    div[data-testid="stMetric"] {
        background: rgba(128,128,128,0.07);
        border: 1px solid rgba(128,128,128,0.16);
        border-radius: 10px;
        padding: 10px 12px;
        min-height: 88px;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.15rem;
    }
    .status-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 650;
        background: rgba(34,197,94,0.10);
        border: 1px solid rgba(34,197,94,0.22);
    }
    .balance-box {
        border: 1px solid rgba(128,128,128,0.18);
        border-radius: 12px;
        padding: 12px 14px;
        margin: 8px 0 12px 0;
    }
    .balance-label {
        color: #6b7280;
        font-size: 0.8rem;
    }
    .balance-value {
        font-size: 1.45rem;
        font-weight: 750;
        margin-top: 2px;
    }
    .small-note {
        color: #6b7280;
        font-size: 0.78rem;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 650;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)








# =========================================================



# HELPERS



# =========================================================



def get_open_drawer():



    with engine.connect() as connection:



        return connection.execute(



            text("""



                SELECT



                    "CashDrawerID",



                    "UserID",



                    "OpenDateTime",



                    "OpeningCash"



                FROM "CashDrawers"



                WHERE "UserID" = :user_id



                  AND "Status" = 'Open'



                ORDER BY "CashDrawerID" DESC



                LIMIT 1



            """),



            {"user_id": user["UserID"]}



        ).mappings().first()



def get_cash_sales(drawer_open_time):



    with engine.connect() as connection:



        value = connection.execute(



            text("""



                SELECT COALESCE(SUM("GrandTotal"), 0)



                FROM "Sales"



                WHERE "UserID" = :user_id



                  AND "PaymentMode" = 'Cash'



                  AND "SaleDate" >= :open_time



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



                    "CashTransactionID",



                    "TransactionType",



                    "Amount",



                    "Reason",



                    "TransactionDateTime"



                FROM "CashTransactions"



                WHERE "CashDrawerID" = :drawer_id



                ORDER BY "CashTransactionID" DESC



            """),



            {"drawer_id": drawer_id}



        )



        return pd.DataFrame(result.fetchall(), columns=result.keys())



def get_bank_sales(drawer_open_time):

    """Return UPI + Card sales since this cash drawer was opened."""

    with engine.connect() as connection:

        value = connection.execute(

            text("""

                SELECT COALESCE(SUM("GrandTotal"), 0)

                FROM "Sales"

                WHERE "UserID" = :user_id

                  AND "PaymentMode" IN ('UPI', 'Card')

                  AND "SaleDate" >= :open_time

            """),

            {

                "user_id": user["UserID"],

                "open_time": drawer_open_time

            }

        ).scalar()

    return float(value or 0)



# =========================================================



# BANK TRANSACTIONS



def ensure_bank_transactions_table():

    with engine.begin() as connection:

        connection.execute(text("""

            CREATE TABLE IF NOT EXISTS "BankTransactions" (

                "BankTransactionID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

                "CashDrawerID" BIGINT NULL,

                "UserID" BIGINT NOT NULL,

                "TransactionType" VARCHAR(50) NOT NULL,

                "Amount" NUMERIC(18, 2) NOT NULL CHECK ("Amount" > 0),

                "Reason" VARCHAR(500),

                "TransactionDateTime" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

            )

        """))



def get_bank_withdrawals(drawer_open_time):

    with engine.connect() as connection:

        value = connection.execute(text("""

            SELECT COALESCE(SUM("Amount"), 0)

            FROM "BankTransactions"

            WHERE "UserID" = :user_id

              AND "TransactionType" = 'Bank Withdrawal'

              AND "TransactionDateTime" >= :open_time

        """), {"user_id": user["UserID"], "open_time": drawer_open_time}).scalar()

    return float(value or 0)



def get_bank_deposits(drawer_open_time):

    with engine.connect() as connection:

        value = connection.execute(text("""

            SELECT COALESCE(SUM("Amount"), 0)

            FROM "BankTransactions"

            WHERE "UserID" = :user_id

              AND "TransactionType" = 'Bank Deposit'

              AND "TransactionDateTime" >= :open_time

        """), {"user_id": user["UserID"], "open_time": drawer_open_time}).scalar()

    return float(value or 0)



def get_bank_transactions(drawer_open_time):

    with engine.connect() as connection:

        result = connection.execute(text("""

            SELECT "BankTransactionID", "TransactionType", "Amount",

                   "Reason", "TransactionDateTime"

            FROM "BankTransactions"

            WHERE "UserID" = :user_id

              AND "TransactionDateTime" >= :open_time

            ORDER BY "BankTransactionID" DESC

        """), {"user_id": user["UserID"], "open_time": drawer_open_time})

        return pd.DataFrame(result.fetchall(), columns=result.keys())



# Initialize bank transaction storage

try:

    ensure_bank_transactions_table()

except Exception as e:

    st.error("Could not initialize bank transaction table.")

    log_exception(e)

    st.exception(e)

    st.stop()



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
    st.markdown('<div class="section-title">🔓 Open Cash Drawer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-help">Enter the physical cash available before starting billing.</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        open_col1, open_col2 = st.columns([1, 1.6], gap="medium")
        with open_col1:
            opening_cash = st.number_input(
                "Opening Cash",
                min_value=0.0,
                value=0.0,
                step=100.0,
            )
        with open_col2:
            notes = st.text_input(
                "Opening Notes",
                placeholder="Optional note",
            )

        if st.button(
            "💰 Open Cash Drawer",
            type="primary",
            use_container_width=True,
        ):
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            INSERT INTO "CashDrawers"
                            (
                                "UserID",
                                "OpeningCash",
                                "Notes",
                                "Status"
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



bank_sales = get_bank_sales(open_time)

bank_deposits = get_bank_deposits(open_time)

bank_withdrawals = get_bank_withdrawals(open_time)

bank_balance = max(0.0, bank_sales + bank_deposits - bank_withdrawals)

transactions = get_cash_transactions(drawer_id)

bank_transactions = get_bank_transactions(open_time)



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

st.markdown('<div class="section-title">📊 Current Position</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="section-help">Drawer #{drawer_id} • Opened {open_time}</div>',
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3, gap="small")
c1.metric("Opening Cash", f"₹{opening_cash:,.2f}")
c2.metric("Cash Sales", f"₹{cash_sales:,.2f}")
c3.metric("Expected Cash", f"₹{expected_cash:,.2f}")

c4, c5, c6 = st.columns(3, gap="small")
c4.metric("UPI + Card", f"₹{bank_sales:,.2f}")
c5.metric("Bank Deposit", f"₹{bank_deposits:,.2f}")
c6.metric("Bank Withdrawal", f"₹{bank_withdrawals:,.2f}")

st.markdown(
    f"""
    <div class="balance-box">
        <div class="balance-label">Current Bank Balance</div>
        <div class="balance-value">₹{bank_balance:,.2f}</div>
        <div class="small-note">
            UPI + Card sales + Bank deposits − Bank withdrawals.
            Bank transactions are separate from physical cash.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================



# CASH EXPENSE / CASH IN
# =========================================================

st.markdown('<div class="section-title">➕ / ➖ Cash Transaction</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-help">Record cash received, expenses, or cash removed from the drawer.</div>',
    unsafe_allow_html=True,
)

with st.container(border=True):
    cash_type_col, cash_amount_col, cash_reason_col, cash_action_col = st.columns(
        [1.0, 0.9, 1.8, 1.0], gap="small"
    )

    with cash_type_col:
        transaction_type = st.radio(
            "Transaction Type",
            ["Expense", "Cash In", "Cash Out"],
            horizontal=True,
        )

    with cash_amount_col:
        amount = st.number_input(
            "Amount",
            min_value=0.01,
            value=100.0,
            step=10.0,
        )

    with cash_reason_col:
        reason = st.text_input(
            "Reason",
            placeholder="Tea expense / cash received / supplier payment",
        )

    with cash_action_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        save_cash_transaction = st.button(
            "Save Cash",
            use_container_width=True,
        )

    if save_cash_transaction:
        if not reason.strip():
            st.error("Please enter a reason.")
        else:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            INSERT INTO "CashTransactions"
                            (
                                "CashDrawerID",
                                "UserID",
                                "TransactionType",
                                "Amount",
                                "Reason"
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



# BANK DEPOSIT / WITHDRAWAL
# =========================================================

st.markdown('<div class="section-title">🏦 Bank Transactions</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-help">Bank transactions affect Bank Balance only; they do not change Expected Cash.</div>',
    unsafe_allow_html=True,
)

bank_dep_col, bank_wd_col = st.columns(2, gap="medium")

with bank_dep_col:
    with st.container(border=True):
        st.markdown("**💰 Bank Deposit**")
        bank_deposit_amount = st.number_input(
            "Deposit Amount",
            min_value=0.01,
            value=100.0,
            step=10.0,
            key="bank_deposit_amount",
        )
        bank_deposit_reason = st.text_input(
            "Deposit Reason",
            placeholder="Owner deposit / opening capital / other credit",
            key="bank_deposit_reason",
        )

        if st.button(
            "💰 Save Deposit",
            use_container_width=True,
            key="save_bank_deposit",
        ):
            if not bank_deposit_reason.strip():
                st.error("Please enter a deposit reason.")
            else:
                try:
                    with engine.begin() as connection:
                        connection.execute(text("""
                            INSERT INTO "BankTransactions"
                            ("CashDrawerID", "UserID", "TransactionType", "Amount", "Reason")
                            VALUES (:drawer_id, :user_id, 'Bank Deposit', :amount, :reason)
                        """), {
                            "drawer_id": drawer_id,
                            "user_id": user["UserID"],
                            "amount": bank_deposit_amount,
                            "reason": bank_deposit_reason.strip()
                        })

                    st.success("Bank deposit saved successfully.")
                    st.rerun()

                except Exception as e:
                    st.error("Error saving bank deposit.")
                    log_exception(e)
                    st.exception(e)

with bank_wd_col:
    with st.container(border=True):
        st.markdown("**🏦 Bank Withdrawal**")
        bank_withdrawal_amount = st.number_input(
            "Withdrawal Amount",
            min_value=0.01,
            value=100.0,
            step=10.0,
            key="bank_withdrawal_amount",
        )
        bank_withdrawal_reason = st.text_input(
            "Withdrawal Reason",
            placeholder="Transfer / bank charges / withdrawal",
            key="bank_withdrawal_reason",
        )

        if st.button(
            "🏦 Save Withdrawal",
            use_container_width=True,
            key="save_bank_withdrawal",
        ):
            if bank_withdrawal_amount > bank_balance:
                st.error(
                    f"Withdrawal cannot exceed the current bank balance of ₹{bank_balance:,.2f}."
                )
            elif not bank_withdrawal_reason.strip():
                st.error("Please enter a withdrawal reason.")
            else:
                try:
                    with engine.begin() as connection:
                        connection.execute(text("""
                            INSERT INTO "BankTransactions"
                            ("CashDrawerID", "UserID", "TransactionType", "Amount", "Reason")
                            VALUES (:drawer_id, :user_id, 'Bank Withdrawal', :amount, :reason)
                        """), {
                            "drawer_id": drawer_id,
                            "user_id": user["UserID"],
                            "amount": bank_withdrawal_amount,
                            "reason": bank_withdrawal_reason.strip()
                        })

                    st.success("Bank withdrawal saved successfully.")
                    st.rerun()

                except Exception as e:
                    st.error("Could not save bank withdrawal.")
                    log_exception(e)
                    st.exception(e)

# TRANSACTION HISTORY
# =========================================================

st.markdown('<div class="section-title">📋 Transaction History</div>', unsafe_allow_html=True)

cash_tab, bank_tab = st.tabs(["💵 Cash Transactions", "🏦 Bank Transactions"])

with cash_tab:
    if transactions.empty:
        st.info("No manual cash transactions for the current drawer.")
    else:
        st.dataframe(
            transactions,
            use_container_width=True,
            hide_index=True,
        )

with bank_tab:
    if bank_transactions.empty:
        st.info("No bank transactions for the current drawer period.")
    else:
        st.dataframe(
            bank_transactions,
            use_container_width=True,
            hide_index=True,
        )

# CLOSE DRAWER
# =========================================================

st.markdown('<div class="section-title">🔒 Close Cash Drawer</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-help">Count the physical cash, review the variance, and close this drawer.</div>',
    unsafe_allow_html=True,
)

with st.container(border=True):
    close_col1, close_col2 = st.columns([1, 1.7], gap="medium")

    with close_col1:
        actual_cash = st.number_input(
            "Actual Cash Counted",
            min_value=0.0,
            value=float(expected_cash),
            step=100.0,
        )

        difference = actual_cash - expected_cash

        if difference > 0:
            st.info(f"Excess cash: ₹{difference:,.2f}")
        elif difference < 0:
            st.warning(f"Cash shortage: ₹{abs(difference):,.2f}")
        else:
            st.success("Cash matches expected amount.")

    with close_col2:
        closing_notes = st.text_input(
            "Closing Notes",
            placeholder="Optional closing note",
        )

        st.markdown(
            f"""
            <div class="balance-box">
                <div class="balance-label">Expected Cash</div>
                <div class="balance-value">₹{expected_cash:,.2f}</div>
                <div class="small-note">Actual counted: ₹{actual_cash:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "🔒 Close Cash Drawer",
            type="primary",
            use_container_width=True,
        ):
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            UPDATE "CashDrawers"
                            SET
                                "ClosingDateTime" = CURRENT_TIMESTAMP,
                                "ExpectedCash" = :expected_cash,
                                "ActualCash" = :actual_cash,
                                "DifferenceAmount" = :difference,
                                "Status" = 'Closed',
                                "Notes" = CASE
                                    WHEN :notes = '' THEN "Notes"
                                    WHEN "Notes" IS NULL OR "Notes" = '' THEN :notes
                                    ELSE "Notes" || ' | ' || :notes
                                END
                            WHERE "CashDrawerID" = :drawer_id
                              AND "Status" = 'Open'
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
