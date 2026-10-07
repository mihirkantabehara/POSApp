import html

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

# =========================================================
# STYLES
# =========================================================
st.markdown(
    """
    <style>
    :root{
      --sr-blue:#2563eb;
      --sr-green:#15803d;
      --sr-red:#dc2626;
      --sr-amber:#b45309;
      --sr-ink:#0f172a;
      --sr-muted:#64748b;
      --sr-line:#e2e8f0;
      --sr-surface:#ffffff;
      --sr-bg:#f6f8fb;
    }
    .stApp{background:var(--sr-bg);}
    .block-container{padding-top:2.6rem !important;padding-bottom:1rem !important;max-width:1400px;}
    header[data-testid="stHeader"]{background:transparent;}

    /* tighter rhythm */
    div[data-testid="stVerticalBlock"]{gap:.5rem;}
    div[data-testid="stHorizontalBlock"]{gap:.6rem;}
    div[data-testid="stElementContainer"]{margin:0;}
    div[data-testid="stVerticalBlockBorderWrapper"]{
      background:var(--sr-surface);border-radius:12px;
      box-shadow:0 1px 2px rgba(15,23,42,.05);
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"]{gap:.4rem;}

    /* Streamlit pulls markdown up by -1rem; our blocks are plain divs */
    div[data-testid="stMarkdown"],
    div[data-testid="stMarkdownContainer"],
    .stMarkdown{margin-bottom:0 !important;}

    /* page header */
    .sr-head{display:flex;align-items:center;justify-content:space-between;
             flex-wrap:wrap;gap:8px;margin-bottom:2px;}
    .sr-title{font-size:1.25rem;font-weight:800;color:var(--sr-ink);line-height:1.2;}
    .sr-sub{font-size:.76rem;color:var(--sr-muted);}
    .sr-chips{display:flex;gap:8px;flex-wrap:wrap;}
    .sr-chip{background:var(--sr-surface);border:1px solid var(--sr-line);
             border-radius:10px;padding:4px 12px;min-width:110px;}
    .sr-chip span{display:block;font-size:.66rem;color:var(--sr-muted);}
    .sr-chip strong{display:block;font-size:.82rem;color:var(--sr-ink);}

    /* section title */
    .sr-h{margin:0;padding:2px 0 4px 0;font-size:.85rem;font-weight:700;
          color:var(--sr-ink);display:flex;align-items:center;gap:6px;line-height:1.2;}

    /* bill summary strip */
    .sr-bill{display:grid;grid-template-columns:.8fr 1.6fr 1.5fr .9fr 1.1fr;gap:10px;
             background:var(--sr-surface);border:1px solid var(--sr-line);
             border-radius:12px;padding:10px 14px;box-shadow:0 1px 2px rgba(15,23,42,.05);}
    .sr-bill div{min-width:0;}
    .sr-bill span{display:block;font-size:.68rem;color:var(--sr-muted);margin-bottom:2px;}
    .sr-bill strong{display:block;font-size:.95rem;color:var(--sr-ink);
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .sr-bill strong.total{color:var(--sr-green);}
    .sr-badge{display:inline-block;padding:1px 10px;border-radius:999px;
              background:#eff6ff;color:var(--sr-blue);font-size:.78rem;font-weight:700;}

    /* return rows */
    .sr-th{font-size:.7rem;font-weight:700;color:var(--sr-muted);
           text-transform:none;padding:0 2px;}
    .sr-prod{font-size:.88rem;font-weight:700;color:var(--sr-ink);line-height:1.25;}
    .sr-meta{font-size:.72rem;color:var(--sr-muted);line-height:1.25;}
    .sr-num{font-size:.88rem;color:var(--sr-ink);padding-top:6px;}
    .sr-refund{font-size:.9rem;font-weight:700;color:var(--sr-ink);padding-top:6px;text-align:right;}
    .sr-row-sep{border:0;border-top:1px solid var(--sr-line);margin:2px 0;}

    /* totals panel */
    .sr-total{display:grid;grid-template-columns:1fr 1fr;gap:10px;
              background:linear-gradient(180deg,#eff6ff 0%,#ffffff 80%);
              border:1px solid #dbe6fb;border-radius:12px;padding:10px 14px;}
    .sr-total .label{font-size:.75rem;color:#334155;}
    .sr-total .big{font-size:1.6rem;font-weight:800;color:var(--sr-red);line-height:1.15;}
    .sr-total .count{font-size:1.6rem;font-weight:800;color:var(--sr-ink);line-height:1.15;}

    /* inputs and buttons */
    .stTextInput input,.stNumberInput input{
      font-size:.85rem;padding:5px 10px;height:34px;border-radius:8px;}
    div[data-baseweb="select"]>div{font-size:.85rem;min-height:34px;border-radius:8px;}
    .stNumberInput button{height:17px;}
    .stTextInput label,.stNumberInput label,.stSelectbox label{
      font-size:.75rem;color:var(--sr-muted);margin-bottom:0;}
    div[data-testid="stWidgetLabel"]{min-height:0;margin-bottom:0;}
    div[data-testid="stCaptionContainer"]{margin:0;line-height:1.2;}
    .stButton>button{
      border-radius:8px;font-weight:600;border:1px solid var(--sr-line);
      font-size:.85rem;min-height:36px;padding:4px 12px;}
    .stButton>button p{white-space:nowrap;}
    .stButton>button[kind="primary"]{
      background:var(--sr-blue);border-color:var(--sr-blue);color:#fff;}
    [data-testid="stDataFrame"]{font-size:.82rem;}
    div[data-testid="stAlert"]{padding:.45rem .8rem;border-radius:10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# ACCESS
# =========================================================
user = require_role("Sales Boy", "Manager", "Admin")

st.markdown(
    f"""
    <div class="sr-head">
      <div>
        <div class="sr-title">↩️ Sales Return</div>
        <div class="sr-sub">Look up the original bill, choose the items coming back, and process the refund.</div>
      </div>
      <div class="sr-chips">
        <div class="sr-chip"><span>User</span><strong>{html.escape(str(user['FullName']))}</strong></div>
        <div class="sr-chip"><span>Role</span><strong>{html.escape(str(user['Role']))}</strong></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def section(title: str) -> None:
    st.markdown(f'<div class="sr-h">{title}</div>', unsafe_allow_html=True)


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
            s."SaleID",
            s."SaleDate",
            s."CustomerName",
            s."PaymentMode",
            s."GrandTotal"
        FROM "Sales" s
        WHERE s."SaleID" = :sale_id
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
            si."SaleID",
            si."ProductID",
            p."ProductName",
            p."Barcode",
            si."BatchID",
            pb."BatchNo",
            pb."ExpiryDate",
            SUM(si."Quantity") AS "SoldQuantity",
            COALESCE((
                SELECT SUM(sri."Quantity")
                FROM "SalesReturnItems" sri
                INNER JOIN "SalesReturns" sr
                    ON sr."ReturnID" = sri."ReturnID"
                WHERE sr."SaleID" = si."SaleID"
                  AND sri."ProductID" = si."ProductID"
                  AND COALESCE(sri."BatchID", 0)
                      = COALESCE(si."BatchID", 0)
            ), 0) AS "ReturnedQuantity",
            MAX(si."Price") AS "Price",
            MAX(si."GSTPercent") AS "GSTPercent",
            SUM(si."Amount") AS OriginalAmount
        FROM "SaleItems" si
        INNER JOIN "Products" p
            ON p."ProductID" = si."ProductID"
        LEFT JOIN "ProductBatches" pb
            ON pb."BatchID" = si."BatchID"
        WHERE si."SaleID" = :sale_id
        GROUP BY
            si."SaleID",
            si."ProductID",
            p."ProductName",
            p."Barcode",
            si."BatchID",
            pb."BatchNo",
            pb."ExpiryDate"
        ORDER BY
            p."ProductName",
            si."BatchID"
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
            SELECT
                "CashDrawerID",
                "OpeningCash",
                "OpenDateTime"
            FROM "CashDrawers"
            WHERE "UserID" = :user_id
              AND "Status" = 'Open'
            ORDER BY "CashDrawerID" DESC
        """),
        {"user_id": int(user_id)}
    ).mappings().first()


# =========================================================
# SEARCH BILL
# =========================================================
with st.container(border=True):
    section("🔎 Find original bill")

    c1, c2, c3 = st.columns([1.2, 1, 2.2], gap="small")

    with c1:
        sale_id = st.number_input(
            "Bill / Sale ID",
            min_value=1,
            step=1,
            value=st.session_state.get("return_sale_id", 1),
            label_visibility="collapsed",
        )

    with c2:
        search_clicked = st.button(
            "🔎 Search bill",
            type="primary",
            use_container_width=True,
        )

    with c3:
        st.caption("Enter the Bill / Sale ID printed on the customer's receipt.")

if search_clicked:
    st.session_state["return_sale_id"] = int(sale_id)

current_sale_id = st.session_state.get("return_sale_id")

if not current_sale_id:
    st.info("Enter a Bill / Sale ID and click Search bill.")
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
customer = sale.get("CustomerName") or "Walk-in Customer"
payment = sale.get("PaymentMode") or "-"
grand_total = sale.get("GrandTotal") or 0

st.markdown(
    f"""
    <div class="sr-bill">
      <div><span>Bill no.</span><strong>#{html.escape(str(sale['SaleID']))}</strong></div>
      <div><span>Customer</span><strong>{html.escape(str(customer))}</strong></div>
      <div><span>Date</span><strong>{html.escape(str(sale.get('SaleDate') or '-')[:19])}</strong></div>
      <div><span>Payment</span><strong><span class="sr-badge">{html.escape(str(payment))}</span></strong></div>
      <div><span>Bill total</span><strong class="total">{money(grand_total)}</strong></div>
    </div>
    """,
    unsafe_allow_html=True,
)

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

with st.container(border=True):
    section("📦 Items on bill")

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
        column_config={
            "Sold Qty": st.column_config.NumberColumn("Sold Qty", format="%g"),
            "Already Returned": st.column_config.NumberColumn(
                "Already Returned", format="%g"
            ),
            "Available": st.column_config.NumberColumn("Available", format="%g"),
            "Price": st.column_config.NumberColumn("Price (₹)", format="%.2f"),
        },
    )

# =========================================================
# RETURN QUANTITY
# =========================================================
return_items = []

with st.container(border=True):
    section("↩️ Enter return quantities")
    st.caption(
        "Enter the quantity being returned. "
        "The system prevents returning more than the remaining quantity."
    )

    ROW_WIDTHS = [3, 1, 1.1, 1.4, 1.5]

    h1, h2, h3, h4, h5 = st.columns(ROW_WIDTHS, gap="small")
    h1.markdown('<div class="sr-th">Product</div>', unsafe_allow_html=True)
    h2.markdown('<div class="sr-th">Sold</div>', unsafe_allow_html=True)
    h3.markdown('<div class="sr-th">Available</div>', unsafe_allow_html=True)
    h4.markdown('<div class="sr-th">Return qty</div>', unsafe_allow_html=True)
    h5.markdown(
        '<div class="sr-th" style="text-align:right">Refund (incl. GST)</div>',
        unsafe_allow_html=True,
    )

    any_returnable = False

    for idx, row in items.iterrows():

        available = float(row["AvailableReturn"])

        if available <= 0:
            continue

        any_returnable = True

        batch_name = (
            str(row["BatchNo"])
            if pd.notna(row["BatchNo"])
            else "Legacy / No Batch"
        )

        st.markdown('<hr class="sr-row-sep">', unsafe_allow_html=True)

        c1, c2, c3, c4, c5 = st.columns(ROW_WIDTHS, gap="small")

        with c1:
            st.markdown(
                f'<div class="sr-prod">{html.escape(str(row["ProductName"]))}</div>'
                f'<div class="sr-meta">Barcode: {html.escape(str(row["Barcode"] or "-"))}'
                f' &nbsp;|&nbsp; Batch: {html.escape(batch_name)}</div>',
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown(
                f'<div class="sr-num">{float(row["SoldQuantity"]):g}</div>',
                unsafe_allow_html=True,
            )

        with c3:
            st.markdown(
                f'<div class="sr-num">{available:g}</div>',
                unsafe_allow_html=True,
            )

        with c4:
            qty = st.number_input(
                "Return Qty",
                min_value=0.0,
                max_value=available,
                value=0.0,
                step=1.0,
                key=f"return_qty_{current_sale_id}_{idx}",
                label_visibility="collapsed",
            )

        # Refund amount includes GST because the customer paid the GST-inclusive bill.
        with c5:
            gst_rate = float(row["GSTPercent"])
            amount_including_gst = (
                qty * float(row["Price"]) * (1 + gst_rate / 100)
            )
            st.markdown(
                f'<div class="sr-refund">{money(amount_including_gst)}</div>',
                unsafe_allow_html=True,
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

    if not any_returnable:
        st.info("Every item on this bill has already been returned.")

# =========================================================
# RETURN DETAILS
# =========================================================
reason_options = [
    "Customer Return",
    "Damaged Product",
    "Wrong Product",
    "Wrong Quantity",
    "Expired / Near Expiry",
    "Billing Error",
    "Other",
]

with st.container(border=True):
    section("📝 Return details")

    r1, r2 = st.columns([1, 1], gap="small")

    with r1:
        reason = st.selectbox("Return Reason", reason_options)

    if reason == "Other":
        with r2:
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

with st.container(border=True):
    section("💳 Refund summary")

    left, right = st.columns([2, 1], gap="small")

    with left:
        st.markdown(
            f'<div class="sr-total">'
            f'<div><div class="label">Items to return</div>'
            f'<div class="count">{len(return_items)}</div></div>'
            f'<div><div class="label">Return amount</div>'
            f'<div class="big">{money(total_return)}</div></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    with right:
        process_return = st.button(
            "↩️ PROCESS RETURN",
            type="primary",
            use_container_width=True,
        )

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
                        "SaleID",
                        "PaymentMode"
                    FROM "Sales"
                    WHERE "SaleID" = :sale_id
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
                    INSERT INTO "SalesReturns"
                    (
                        "SaleID",
                        "UserID",
                        "Reason",
                        "TotalReturnAmount"
                    )
                    VALUES
                    (
                        :sale_id,
                        :user_id,
                        :reason,
                        :total_amount
                    )
                    RETURNING "ReturnID"
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
                        SELECT COALESCE(SUM("Quantity"), 0)
                        FROM "SaleItems"
                        WHERE "SaleID" = :sale_id
                          AND "ProductID" = :product_id
                          AND COALESCE("BatchID", 0)
                              = COALESCE(:batch_id, 0)
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
                        SELECT COALESCE(SUM(sri."Quantity"), 0)
                        FROM "SalesReturnItems" sri
                        INNER JOIN "SalesReturns" sr
                            ON sr."ReturnID" = sri."ReturnID"
                        WHERE sr."SaleID" = :sale_id
                          AND sri."ProductID" = :product_id
                          AND COALESCE(sri."BatchID", 0)
                              = COALESCE(:batch_id, 0)
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
                        INSERT INTO "SalesReturnItems"
                        (
                            "ReturnID",
                            "ProductID",
                            "BatchID",
                            "Quantity",
                            "Price",
                            "GSTPercent",
                            "Amount"
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
                            UPDATE "ProductBatches"
                            SET
                                "Quantity" = "Quantity" + :quantity,
                                "IsActive" = TRUE
                            WHERE "BatchID" = :batch_id
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
                        UPDATE "Products"
                        SET "Stock" = "Stock" + :quantity
                        WHERE "ProductID" = :product_id
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