import html
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import text

from auth import require_role
from database.database import engine

try:
    st.set_page_config(page_title="Customer Credit Management", page_icon="💳", layout="wide")
except Exception:
    pass

user = require_role("Sales Boy","Manager", "Admin")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; max-width: 1450px;}
    h2, h3 {font-size: 1.05rem !important; line-height: 1.3 !important;}
    div[data-testid="stMetricLabel"] {font-size: .75rem !important;}
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e2e8f0;
        padding: 12px 14px; border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.caption("Review outstanding credit bills and record payments received later.")

# Create the payment history table if it does not already exist.
# PostgreSQL syntax; all operations below use the existing SQLAlchemy engine.
try:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS "CreditPayments" (
                "CreditPaymentID" BIGSERIAL PRIMARY KEY,
                "SaleID" BIGINT NOT NULL REFERENCES "Sales"("SaleID"),
                "CustomerName" TEXT NOT NULL,
                "Amount" NUMERIC(12,2) NOT NULL CHECK ("Amount" > 0),
                "PaymentMode" VARCHAR(20) NOT NULL
                    CHECK ("PaymentMode" IN ('Cash', 'UPI', 'Card')),
                "ReceivedByUserID" INTEGER,
                "PaymentDateTime" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "Notes" TEXT
            )
        """))
except Exception as exc:
    st.error("Could not prepare the credit-payment history table.")
    st.exception(exc)
    st.stop()

try:
    sales = pd.read_sql(
        text("""
            SELECT
                s."SaleID",
                s."CustomerName",
                s."GrandTotal",
                s."AmountPaid",
                s."BalanceAmount",
                s."PaymentMode",
                s."UserID"
            FROM "Sales" s
            WHERE COALESCE(s."BalanceAmount", 0) < 0
            ORDER BY s."SaleID" DESC
        """),
        engine,
    )
except Exception as exc:
    st.error("Could not load outstanding bills. Verify the Sales table columns.")
    st.exception(exc)
    st.stop()

if not sales.empty:
    sales["BalanceAmount"] = pd.to_numeric(sales["BalanceAmount"], errors="coerce").fillna(0).abs()
    sales["GrandTotal"] = pd.to_numeric(sales["GrandTotal"], errors="coerce").fillna(0)
    sales["AmountPaid"] = pd.to_numeric(sales["AmountPaid"], errors="coerce").fillna(0)

total_due = float(sales["BalanceAmount"].sum()) if not sales.empty else 0.0
customer_count = int(sales["CustomerName"].nunique()) if not sales.empty else 0
bill_count = int(len(sales))

m1, m2, m3 = st.columns(3)
m1.metric("Total Outstanding", f"₹{total_due:,.2f}")
m2.metric("Customers With Dues", customer_count)
m3.metric("Unpaid / Part-paid Bills", bill_count)

st.divider()
st.subheader("Outstanding credit bills")

search = st.text_input("Search customer or bill number", placeholder="Enter customer name or bill number")
view = sales.copy()
if search.strip():
    term = search.strip()
    view = view[
        view["CustomerName"].astype(str).str.contains(term, case=False, na=False)
        | view["SaleID"].astype(str).str.contains(term, case=False, na=False)
    ]

if view.empty:
    st.success("No outstanding credit bills found.")
else:
    display = view[["SaleID", "CustomerName", "GrandTotal", "AmountPaid", "BalanceAmount", "PaymentMode"]].copy()
    display.columns = ["Bill No.", "Customer", "Bill Total (₹)", "Paid (₹)", "Due (₹)", "Original Mode"]
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Bill Total (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            "Paid (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            "Due (₹)": st.column_config.NumberColumn(format="₹%.2f"),
        },
    )

    st.divider()
    st.subheader("Record a customer payment")
    st.caption("Select the specific bill being paid. A payment cannot exceed that bill's current outstanding balance.")

    options = view.to_dict("records")
    def bill_label(row):
        return f"Bill #{int(row['SaleID'])} · {row['CustomerName']} · Due ₹{float(row['BalanceAmount']):,.2f}"

    selected_label = st.selectbox("Select bill", [bill_label(row) for row in options])
    selected = options[[bill_label(row) for row in options].index(selected_label)]
    due_now = float(selected["BalanceAmount"])

    with st.form("credit_payment_form", clear_on_submit=True):
        left, middle, right = st.columns(3)
        with left:
            amount = st.number_input(
                "Amount received (₹)", min_value=0.01, max_value=due_now,
                value=min(due_now, max(0.01, due_now)), step=1.0, format="%.2f"
            )
        with middle:
            payment_mode = st.selectbox("Received by", ["Cash", "UPI", "Card"])
        with right:
            notes = st.text_input("Notes (optional)", placeholder="Reference / remarks")
        st.info(f"Bill #{int(selected['SaleID'])}: outstanding ₹{due_now:,.2f}. After this payment, remaining due will be ₹{max(0.0, due_now - float(amount)):,.2f}.")
        submitted = st.form_submit_button("💾 Record payment", type="primary", use_container_width=True)

    if submitted:
        payment_amount = round(float(amount), 2)
        try:
            with engine.begin() as conn:
                locked = conn.execute(
                    text("""
                        SELECT "CustomerName", "GrandTotal", "AmountPaid", "BalanceAmount"
                        FROM "Sales"
                        WHERE "SaleID" = :sale_id
                        FOR UPDATE
                    """),
                    {"sale_id": int(selected["SaleID"])},
                ).mappings().first()

                if not locked:
                    raise ValueError("The selected bill no longer exists.")

                current_due = round(abs(float(locked["BalanceAmount"] or 0)), 2)
                if current_due <= 0:
                    raise ValueError("This bill has already been fully paid. Refresh the page.")
                if payment_amount <= 0 or payment_amount > current_due:
                    raise ValueError(f"Payment must be between ₹0.01 and ₹{current_due:,.2f}.")

                # For cash collections, require an open drawer and record the
                # collection in the existing Cash in Hand transaction ledger.
                cash_drawer_id = None
                if payment_mode == "Cash":
                    cash_drawer_id = conn.execute(
                        text("""
                            SELECT "CashDrawerID"
                            FROM "CashDrawers"
                            WHERE "UserID" = :user_id AND "Status" = 'Open'
                            ORDER BY "CashDrawerID" DESC
                            LIMIT 1
                            FOR UPDATE
                        """),
                        {"user_id": int(user["UserID"])},
                    ).scalar()
                    if not cash_drawer_id:
                        raise ValueError(
                            "Open your cash drawer before recording a cash credit payment."
                        )

                conn.execute(
                    text("""
                        INSERT INTO "CreditPayments"
                            ("SaleID", "CustomerName", "Amount", "PaymentMode",
                             "ReceivedByUserID", "Notes")
                        VALUES
                            (:sale_id, :customer, :amount, :mode, :user_id, :notes)
                    """),
                    {
                        "sale_id": int(selected["SaleID"]),
                        "customer": str(locked["CustomerName"]),
                        "amount": payment_amount,
                        "mode": payment_mode,
                        "user_id": int(user["UserID"]),
                        "notes": notes.strip() or None,
                    },
                )

                conn.execute(
                    text("""
                        UPDATE "Sales"
                        SET "AmountPaid" = COALESCE("AmountPaid", 0) + :amount,
                            "BalanceAmount" = LEAST(COALESCE("BalanceAmount", 0) + :amount, 0)
                        WHERE "SaleID" = :sale_id
                    """),
                    {"amount": payment_amount, "sale_id": int(selected["SaleID"])},
                )

                if payment_mode == "Cash":
                    conn.execute(
                        text("""
                            INSERT INTO "CashTransactions"
                                ("CashDrawerID", "UserID", "TransactionType", "Amount", "Reason")
                            VALUES
                                (:drawer_id, :user_id, 'Cash In', :amount, :reason)
                        """),
                        {
                            "drawer_id": int(cash_drawer_id),
                            "user_id": int(user["UserID"]),
                            "amount": payment_amount,
                            "reason": (
                                f"Credit payment for bill #{int(selected['SaleID'])} - "
                                f"{locked['CustomerName']}"
                            ),
                        },
                    )

            st.success(
                f"Payment of ₹{payment_amount:,.2f} recorded for bill #{int(selected['SaleID'])}. "
                f"Remaining due: ₹{max(0.0, due_now - payment_amount):,.2f}."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Payment was not recorded: {exc}")

st.divider()
st.subheader("Recent credit-payment history")
try:
    history = pd.read_sql(
        text("""
            SELECT
                cp."CreditPaymentID",
                cp."PaymentDateTime",
                cp."SaleID",
                cp."CustomerName",
                cp."Amount",
                cp."PaymentMode",
                u."FullName" AS "ReceivedBy",
                cp."Notes"
            FROM "CreditPayments" cp
            LEFT JOIN "Users" u ON u."UserID" = cp."ReceivedByUserID"
            ORDER BY cp."PaymentDateTime" DESC, cp."CreditPaymentID" DESC
            LIMIT 200
        """),
        engine,
    )
    if history.empty:
        st.info("No later credit payments have been recorded yet.")
    else:
        history["Amount"] = pd.to_numeric(history["Amount"], errors="coerce").fillna(0)
        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Amount": st.column_config.NumberColumn("Amount (₹)", format="₹%.2f"),
                "PaymentDateTime": st.column_config.DatetimeColumn("Payment date/time", format="DD MMM YYYY, HH:mm"),
            },
        )
        csv = history.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export payment history (CSV)", csv, "credit_payment_history.csv", "text/csv")
except Exception as exc:
    st.warning("Payment history is not available right now.")
    st.exception(exc)
