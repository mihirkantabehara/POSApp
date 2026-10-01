import streamlit as st
from logging_config import log_exception
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_role

st.set_page_config(
    page_title="Sales Return",
    page_icon="↩️",
    layout="wide",
)

# Compact POS typography
st.markdown(
    """
    <style>
    /* Main section headings */
    h2 {
        font-size: 1.15rem !important;
        margin-top: 0.55rem !important;
        margin-bottom: 0.35rem !important;
    }

    /* Smaller Streamlit subheaders */
    [data-testid="stSubheader"] {
        font-size: 1.05rem !important;
    }

    /* General page text */
    .stMarkdown,
    .stCaption,
    label,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"] {
        font-size: 0.88rem !important;
    }

    /* Metric values should remain readable but compact */
    [data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
    }

    /* Buttons */
    .stButton > button {
        font-size: 0.88rem !important;
        min-height: 2.25rem !important;
        padding: 0.25rem 0.7rem !important;
    }

    /* Inputs and select boxes */
    input,
    textarea,
    [data-baseweb="select"] *,
    [data-testid="stNumberInput"] input {
        font-size: 0.88rem !important;
    }

    /* Dataframe text */
    [data-testid="stDataFrame"] {
        font-size: 0.82rem !important;
    }

    /* Reduce vertical spacing */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# ACCESS
# =========================================================
user = require_role("Sales Boy", "Manager", "Admin")

#st.title("↩️ Sales Return")
st.caption(
    f"Process sales returns • {user['FullName']} • {user['Role']}"
)

# =========================================================
# HELPERS
# =========================================================
def money(value):
    try:
        return f"₹{float(value or 0):,.2f}"
    except Exception:
        return "₹0.00"


def load_sale(sale_id):
    sql = text("""
        SELECT
            s.SaleID,
            s.SaleDate,
            s.CustomerName,
            s.PaymentMode,
            s.GrandTotal
        FROM Sales s
        WHERE s.SaleID = :sale_id
    """)

    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"sale_id": int(sale_id)}
        ).mappings().first()

    return dict(row) if row else None


def load_sale_items(sale_id):
    sql = text("""
        SELECT
            si.SaleID,
            si.ProductID,
            p.ProductName,
            p.Barcode,
            si.BatchID,
            pb.BatchNo,
            pb.ExpiryDate,
            SUM(si.Quantity) AS SoldQuantity,
            COALESCE((
                SELECT SUM(sri.Quantity)
                FROM SalesReturnItems sri
                INNER JOIN SalesReturns sr
                    ON sr.ReturnID = sri.ReturnID
                WHERE sr.SaleID = si.SaleID
                  AND sri.ProductID = si.ProductID
                  AND ISNULL(sri.BatchID, 0)
                      = ISNULL(si.BatchID, 0)
            ), 0) AS ReturnedQuantity,
            MAX(si.Price) AS Price,
            MAX(si.GSTPercent) AS GSTPercent,
            SUM(si.Amount) AS OriginalAmount
        FROM SaleItems si
        INNER JOIN Products p
            ON p.ProductID = si.ProductID
        LEFT JOIN ProductBatches pb
            ON pb.BatchID = si.BatchID
        WHERE si.SaleID = :sale_id
        GROUP BY
            si.SaleID,
            si.ProductID,
            p.ProductName,
            p.Barcode,
            si.BatchID,
            pb.BatchNo,
            pb.ExpiryDate
        ORDER BY
            p.ProductName,
            si.BatchID
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"sale_id": int(sale_id)}
        ).mappings().all()

    return pd.DataFrame(rows)


def get_open_drawer(conn, user_id):
    return conn.execute(
        text("""
            SELECT TOP 1
                CashDrawerID,
                OpeningCash,
                OpenDateTime
            FROM CashDrawers
            WHERE UserID = :user_id
              AND Status = 'Open'
            ORDER BY CashDrawerID DESC
        """),
        {"user_id": int(user_id)}
    ).mappings().first()


# =========================================================
# SEARCH BILL
# =========================================================
st.subheader("🔎 Find Original Bill")

c1, c2 = st.columns([2, 1])

with c1:
    sale_id = st.number_input(
        "Bill / Sale ID",
        min_value=1,
        step=1,
        value=st.session_state.get("return_sale_id", 1),
    )

with c2:
    st.write("")
    search_clicked = st.button(
        "🔎 Search Bill",
        type="primary",
        use_container_width=True,
    )

if search_clicked:
    st.session_state["return_sale_id"] = int(sale_id)

current_sale_id = st.session_state.get("return_sale_id")

if not current_sale_id:
    st.info("Enter a Bill / Sale ID and click Search Bill.")
    st.stop()

# =========================================================
# LOAD BILL
# =========================================================
try:
    sale = load_sale(current_sale_id)
    items = load_sale_items(current_sale_id)
except Exception as e:
    st.error("Unable to load the bill.")
    log_exception(e)
    st.exception(e)
    st.stop()

if not sale:
    st.error(f"Bill / Sale ID {current_sale_id} was not found.")
    st.stop()

if items.empty:
    st.warning("No sale items were found for this bill.")
    st.stop()

# =========================================================
# BILL HEADER
# =========================================================
st.subheader("🧾 Original Bill")

customer = sale.get("CustomerName") or "Walk-in Customer"
payment = sale.get("PaymentMode") or "-"
grand_total = sale.get("GrandTotal") or 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Bill No.", str(sale["SaleID"]))
c2.metric("Customer", str(customer))
c3.metric("Date", str(sale.get("SaleDate") or "-")[:19])
c4.metric("Payment", str(payment))
c5.metric("Bill Total", money(grand_total))

# =========================================================
# RETURNABLE QUANTITIES
# =========================================================
items = items.copy()

for col in ["SoldQuantity", "ReturnedQuantity", "Price", "GSTPercent"]:
    items[col] = pd.to_numeric(
        items[col], errors="coerce"
    ).fillna(0)

items["AvailableReturn"] = (
    items["SoldQuantity"] - items["ReturnedQuantity"]
)

st.subheader("📦 Items on Bill")

display_df = items[
    [
        "ProductName",
        "Barcode",
        "BatchNo",
        "ExpiryDate",
        "SoldQuantity",
        "ReturnedQuantity",
        "AvailableReturn",
        "Price",
    ]
].copy()

display_df.columns = [
    "Product",
    "Barcode",
    "Batch",
    "Expiry",
    "Sold Qty",
    "Already Returned",
    "Available",
    "Price",
]

display_df["Expiry"] = display_df["Expiry"].apply(
    lambda x: str(x)[:10] if pd.notna(x) else "-"
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)

# =========================================================
# RETURN QUANTITY
# =========================================================
st.subheader("↩️ Enter Return Quantities")

st.caption(
    "Enter the quantity being returned. "
    "The system prevents returning more than the remaining quantity."
)

return_items = []

for idx, row in items.iterrows():

    available = float(row["AvailableReturn"])

    if available <= 0:
        continue

    batch_name = (
        str(row["BatchNo"])
        if pd.notna(row["BatchNo"])
        else "Legacy / No Batch"
    )

    c1, c2, c3, c4, c5 = st.columns(
        [3, 1.2, 1.2, 1.4, 1.3]
    )

    with c1:
        st.write(f"**{row['ProductName']}**")
        st.caption(
            f"Barcode: {row['Barcode'] or '-'} | Batch: {batch_name}"
        )

    with c2:
        st.write(f"Sold: **{float(row['SoldQuantity']):g}**")

    with c3:
        st.write(f"Available: **{available:g}**")

    with c4:
        qty = st.number_input(
            "Return Qty",
            min_value=0.0,
            max_value=available,
            value=0.0,
            step=1.0,
            key=f"return_qty_{current_sale_id}_{idx}",
        )

    # Refund amount includes GST because the customer paid the GST-inclusive bill.
    with c5:
        gst_rate = float(row["GSTPercent"])
        amount_including_gst = (
            qty * float(row["Price"]) * (1 + gst_rate / 100)
        )
        st.write(
            f"Return: **{money(amount_including_gst)}**"
        )

    if qty > 0:
        return_items.append(
            {
                "ProductID": int(row["ProductID"]),
                "ProductName": str(row["ProductName"]),
                "BatchID": (
                    int(row["BatchID"])
                    if pd.notna(row["BatchID"])
                    else None
                ),
                "BatchNo": batch_name,
                "Quantity": float(qty),
                "Price": float(row["Price"]),
                "GSTPercent": gst_rate,
            }
        )

# =========================================================
# RETURN DETAILS
# =========================================================
st.subheader("📝 Return Details")

reason_options = [
    "Customer Return",
    "Damaged Product",
    "Wrong Product",
    "Wrong Quantity",
    "Expired / Near Expiry",
    "Billing Error",
    "Other",
]

reason = st.selectbox("Return Reason", reason_options)

if reason == "Other":
    reason_text = st.text_input("Specify Reason")
    final_reason = reason_text.strip() or "Other"
else:
    final_reason = reason

# GST-inclusive refund value.
total_return = sum(
    item["Quantity"]
    * item["Price"]
    * (1 + item["GSTPercent"] / 100)
    for item in return_items
)

c1, c2 = st.columns([2, 1])

with c1:
    st.write(f"**Items to Return:** {len(return_items)}")

with c2:
    st.markdown(f"### Return Amount: {money(total_return)}")

if payment == "Cash":
    st.warning(
        f"💵 Cash sale: processing this return will deduct "
        f"{money(total_return)} from the current cash drawer."
    )
else:
    st.info(
        f"Payment mode is **{payment}**. "
        "The return will restore stock, but will not deduct cash "
        "from the cash drawer."
    )

process_return = st.button(
    "↩️ PROCESS RETURN",
    type="primary",
    use_container_width=True,
)

# =========================================================
# PROCESS RETURN
# =========================================================
if process_return:

    if not return_items:
        st.error("Please enter a return quantity for at least one item.")
        st.stop()

    if total_return <= 0:
        st.error("Return amount must be greater than zero.")
        st.stop()

    try:
        with engine.begin() as conn:

            # Verify bill and lock it during the transaction.
            bill = conn.execute(
                text("""
                    SELECT
                        SaleID,
                        PaymentMode
                    FROM Sales WITH (UPDLOCK, ROWLOCK)
                    WHERE SaleID = :sale_id
                """),
                {"sale_id": int(current_sale_id)},
            ).mappings().first()

            if not bill:
                raise ValueError("The selected bill no longer exists.")

            actual_payment_mode = str(
                bill["PaymentMode"] or ""
            )

            # Every sales return reduces the logged-in user's
            # Cash in Hand, regardless of the original payment mode.
            # Therefore an open cash drawer is required for every return.
            drawer = get_open_drawer(
                conn,
                user["UserID"],
            )

            if not drawer:
                raise ValueError(
                    "Please open your Cash Drawer before processing "
                    "a sales return. The return amount will be deducted "
                    "from Cash in Hand."
                )

            # Create return header.
            result = conn.execute(
                text("""
                    INSERT INTO SalesReturns
                    (
                        SaleID,
                        UserID,
                        Reason,
                        TotalReturnAmount
                    )
                    OUTPUT INSERTED.ReturnID
                    VALUES
                    (
                        :sale_id,
                        :user_id,
                        :reason,
                        :total_amount
                    )
                """),
                {
                    "sale_id": int(current_sale_id),
                    "user_id": int(user["UserID"]),
                    "reason": final_reason,
                    "total_amount": total_return,
                },
            )

            return_id = int(result.scalar_one())

            # Process each returned item.
            for item in return_items:

                sold_qty = conn.execute(
                    text("""
                        SELECT COALESCE(SUM(Quantity), 0)
                        FROM SaleItems
                        WHERE SaleID = :sale_id
                          AND ProductID = :product_id
                          AND ISNULL(BatchID, 0)
                              = ISNULL(:batch_id, 0)
                    """),
                    {
                        "sale_id": int(current_sale_id),
                        "product_id": item["ProductID"],
                        "batch_id": item["BatchID"],
                    },
                ).scalar()

                sold_qty = float(sold_qty or 0)

                returned_qty = conn.execute(
                    text("""
                        SELECT COALESCE(SUM(sri.Quantity), 0)
                        FROM SalesReturnItems sri
                        INNER JOIN SalesReturns sr
                            ON sr.ReturnID = sri.ReturnID
                        WHERE sr.SaleID = :sale_id
                          AND sri.ProductID = :product_id
                          AND ISNULL(sri.BatchID, 0)
                              = ISNULL(:batch_id, 0)
                    """),
                    {
                        "sale_id": int(current_sale_id),
                        "product_id": item["ProductID"],
                        "batch_id": item["BatchID"],
                    },
                ).scalar()

                returned_qty = float(returned_qty or 0)
                remaining = sold_qty - returned_qty

                if item["Quantity"] > remaining + 0.000001:
                    raise ValueError(
                        f"Return quantity for {item['ProductName']} "
                        f"exceeds the remaining quantity ({remaining:g})."
                    )

                # SaleItems.Amount is kept as the line amount before GST.
                line_amount = (
                    item["Quantity"] * item["Price"]
                )

                conn.execute(
                    text("""
                        INSERT INTO SalesReturnItems
                        (
                            ReturnID,
                            ProductID,
                            BatchID,
                            Quantity,
                            Price,
                            GSTPercent,
                            Amount
                        )
                        VALUES
                        (
                            :return_id,
                            :product_id,
                            :batch_id,
                            :quantity,
                            :price,
                            :gst_percent,
                            :amount
                        )
                    """),
                    {
                        "return_id": return_id,
                        "product_id": item["ProductID"],
                        "batch_id": item["BatchID"],
                        "quantity": item["Quantity"],
                        "price": item["Price"],
                        "gst_percent": item["GSTPercent"],
                        "amount": line_amount,
                    },
                )

                # Restore exact original batch.
                if item["BatchID"] is not None:

                    result = conn.execute(
                        text("""
                            UPDATE ProductBatches
                            SET
                                Quantity = Quantity + :quantity,
                                IsActive = 1
                            WHERE BatchID = :batch_id
                        """),
                        {
                            "quantity": item["Quantity"],
                            "batch_id": item["BatchID"],
                        },
                    )

                    if result.rowcount == 0:
                        raise ValueError(
                            f"Original batch for {item['ProductName']} "
                            "was not found."
                        )

                # Restore product summary stock.
                result = conn.execute(
                    text("""
                        UPDATE Products
                        SET Stock = Stock + :quantity
                        WHERE ProductID = :product_id
                    """),
                    {
                        "quantity": item["Quantity"],
                        "product_id": item["ProductID"],
                    },
                )

                if result.rowcount == 0:
                    raise ValueError(
                        f"Product {item['ProductName']} was not found."
                    )

            # =================================================
            # CASH-IN-HAND DEDUCTION
            # =================================================
            # Every sales return is recorded as Cash Out,
            # regardless of whether the original bill was
            # Cash, UPI, or Card.
            drawer_id = int(drawer["CashDrawerID"])

            conn.execute(
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
                        'Cash Out',
                        :amount,
                        :reason
                    )
                """),
                {
                    "drawer_id": drawer_id,
                    "user_id": int(user["UserID"]),
                    "amount": total_return,
                    "reason": (
                        f"Sales Return #{return_id} "
                        f"for Bill #{current_sale_id} "
                        f"(Original Payment: {actual_payment_mode})"
                    ),
                },
            )

        st.success(
            f"Return #{return_id} processed successfully."
        )

        st.success(
            f"💵 Cash in Hand reduced by {money(total_return)} "
            f"for this {payment} sale return."
        )

        st.info(
            f"Return amount: {money(total_return)}"
        )

        st.session_state.pop("return_sale_id", None)

    except Exception as e:
        st.error("Sales return failed. No changes were saved.")
        log_exception(e)
        st.exception(e)
