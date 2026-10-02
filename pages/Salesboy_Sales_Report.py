
import streamlit as st
from logging_config import log_exception
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text

from database.database import engine
from auth import require_role


# ---------------------------------------------------------
# PAGE ACCESS
# ---------------------------------------------------------
require_role("Sales Boy", "Manager", "Admin")

#st.title("📊 My Sales Report")
st.caption("View your sales date-wise and open any bill as an itemized invoice.")

user = st.session_state.get("user", {})
user_id = int(user.get("UserID", 0))


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def money(value):
    try:
        return f"₹{float(value):,.2f}"
    except Exception:
        return "₹0.00"


def load_sales(from_date, to_date):
    query = text("""
        SELECT
            s.SaleID,
            s.SaleDate,
            s.CustomerName,
            s.SubTotal,
            s.GSTAmount,
            s.GrandTotal,
            s.PaymentMode,
            s.AmountPaid,
            s.BalanceAmount
        FROM Sales s
        WHERE s.UserID = :user_id
          AND CAST(s.SaleDate AS DATE) BETWEEN :from_date AND :to_date
        ORDER BY s.SaleDate DESC, s.SaleID DESC
    """)

    with engine.connect() as conn:
        return pd.read_sql(
            query,
            conn,
            params={
                "user_id": user_id,
                "from_date": from_date,
                "to_date": to_date,
            },
        )


def load_cash_transactions(from_date, to_date):
    query = text("""
        SELECT
            ct.CashTransactionID,
            ct.TransactionDateTime,
            ct.TransactionType,
            ct.Amount,
            ct.Reason,
            ct.CashDrawerID
        FROM CashTransactions ct
        INNER JOIN CashDrawers cd
            ON cd.CashDrawerID = ct.CashDrawerID
        WHERE ct.UserID = :user_id
          AND CAST(ct.TransactionDateTime AS DATE)
              BETWEEN :from_date AND :to_date
        ORDER BY ct.TransactionDateTime DESC,
                 ct.CashTransactionID DESC
    """)

    with engine.connect() as conn:
        return pd.read_sql(
            query,
            conn,
            params={
                "user_id": user_id,
                "from_date": from_date,
                "to_date": to_date,
            },
        )


def load_bill_items(sale_id):
    query = text("""
        SELECT
            si.SaleItemID,
            si.ProductID,
            p.ProductName,
            si.BatchID,
            pb.BatchNo,
            pb.ExpiryDate,
            si.Quantity,
            si.Price,
            si.GSTPercent,
            si.Amount,
            (si.Amount * si.GSTPercent / 100.0) AS GSTAmount,
            (si.Amount + (si.Amount * si.GSTPercent / 100.0)) AS LineTotal
        FROM SaleItems si
        LEFT JOIN Products p
            ON p.ProductID = si.ProductID
        LEFT JOIN ProductBatches pb
            ON pb.BatchID = si.BatchID
        WHERE si.SaleID = :sale_id
        ORDER BY si.SaleItemID
    """)

    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"sale_id": int(sale_id)})


# ---------------------------------------------------------
# BILL POPUP
# ---------------------------------------------------------
@st.dialog("🧾 Bill Details", width="small")
def show_bill_popup(sale_id):
    header_query = text("""
        SELECT
            s.SaleID,
            s.SaleDate,
            s.CustomerName,
            s.SubTotal,
            s.GSTAmount,
            s.GrandTotal,
            s.PaymentMode,
            s.AmountPaid,
            s.BalanceAmount,
            u.FullName AS SalesPerson
        FROM Sales s
        LEFT JOIN Users u
            ON u.UserID = s.UserID
        WHERE s.SaleID = :sale_id
          AND s.UserID = :user_id
    """)

    with engine.connect() as conn:
        header = conn.execute(
            header_query,
            {
                "sale_id": int(sale_id),
                "user_id": user_id,
            },
        ).mappings().first()

    if not header:
        st.error("Bill not found.")
        return

    items = load_bill_items(sale_id)

    bill_date = pd.to_datetime(header["SaleDate"])
    customer = header["CustomerName"] or "Walk-in Customer"
    payment = header["PaymentMode"] or "-"
    salesperson = header["SalesPerson"] or "-"

    # Thermal receipt styling
    st.markdown(
        """
        <style>
        .thermal-receipt {
            width: 320px;
            max-width: 100%;
            margin: 0 auto;
            padding: 18px 16px;
            background: #ffffff;
            color: #111111;
            font-family: "Courier New", monospace;
            font-size: 12px;
            line-height: 1.35;
            box-sizing: border-box;
            border: 1px solid #dddddd;
            box-shadow: 0 3px 12px rgba(0,0,0,0.10);
        }

        .thermal-center {
            text-align: center;
        }

        .thermal-shop {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 1px;
        }

        .thermal-title {
            font-size: 15px;
            font-weight: 800;
            margin-top: 5px;
        }

        .thermal-line {
            border-top: 1px dashed #333;
            margin: 8px 0;
        }

        .thermal-meta {
            display: grid;
            grid-template-columns: 76px 1fr;
            column-gap: 5px;
            row-gap: 2px;
            word-break: break-word;
        }

        .thermal-items {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }

        .thermal-items th,
        .thermal-items td {
            padding: 2px 0;
            vertical-align: top;
            border: 0;
            font-family: "Courier New", monospace;
            font-size: 11px;
        }

        .thermal-items th {
            border-bottom: 1px dashed #333;
            padding-bottom: 4px;
        }

        .thermal-items .item {
            width: 43%;
            text-align: left;
            word-break: break-word;
        }

        .thermal-items .qty {
            width: 12%;
            text-align: right;
        }

        .thermal-items .rate {
            width: 20%;
            text-align: right;
        }

        .thermal-items .amt {
            width: 25%;
            text-align: right;
        }

        .thermal-total {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
            text-align: right;
        }

        .thermal-grand {
            font-size: 16px;
            font-weight: 800;
            padding: 6px 0;
        }

        .thermal-thanks {
            text-align: center;
            font-weight: 700;
            margin-top: 10px;
        }

        .thermal-note {
            text-align: center;
            font-size: 10px;
            margin-top: 6px;
        }

        @media print {
            body * {
                visibility: hidden !important;
            }

            [role="dialog"],
            [role="dialog"] * {
                visibility: visible !important;
            }

            [role="dialog"] {
                position: absolute !important;
                left: 0 !important;
                top: 0 !important;
                width: 80mm !important;
                max-width: 80mm !important;
                min-width: 80mm !important;
                margin: 0 !important;
                padding: 0 !important;
                box-shadow: none !important;
                border: 0 !important;
                background: white !important;
            }

            [role="dialog"] button {
                display: none !important;
            }

            .thermal-receipt {
                width: 72mm !important;
                max-width: 72mm !important;
                margin: 0 auto !important;
                padding: 3mm 2mm !important;
                border: 0 !important;
                box-shadow: none !important;
                font-size: 10px !important;
            }

            .thermal-shop {
                font-size: 17px !important;
            }

            .thermal-items th,
            .thermal-items td {
                font-size: 9px !important;
            }

            .thermal-grand {
                font-size: 13px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    item_rows = ""

    if not items.empty:
        for _, item in items.iterrows():
            product = str(item["ProductName"] or f"Product #{item['ProductID']}")
            qty = float(item["Quantity"])
            rate = float(item["Price"])
            total = float(item["LineTotal"])

            # Keep receipt compact; long names wrap naturally.
            item_rows += f"""
                <tr>
                    <td class="item">{product}</td>
                    <td class="qty">{qty:g}</td>
                    <td class="rate">{rate:,.2f}</td>
                    <td class="amt">{total:,.2f}</td>
                </tr>
            """

    receipt_html = f"""
    <div class="thermal-receipt">
        <div class="thermal-center thermal-shop">MY SHOP</div>
        <div class="thermal-center">TAX INVOICE</div>

        <div class="thermal-line"></div>

        <div class="thermal-meta">
            <div><b>Bill No</b></div><div>: {header['SaleID']}</div>
            <div><b>Date</b></div><div>: {bill_date.strftime('%d-%m-%Y %H:%M')}</div>
            <div><b>Customer</b></div><div>: {customer}</div>
            <div><b>Sales Boy</b></div><div>: {salesperson}</div>
            <div><b>Payment</b></div><div>: {payment}</div>
        </div>

        <div class="thermal-line"></div>

        <table class="thermal-items">
            <thead>
                <tr>
                    <th class="item">Item</th>
                    <th class="qty">Qty</th>
                    <th class="rate">Rate</th>
                    <th class="amt">Amt</th>
                </tr>
            </thead>
            <tbody>
                {item_rows}
            </tbody>
        </table>

        <div class="thermal-line"></div>

        <div class="thermal-total">
            <div>Subtotal</div>
            <div>{float(header['SubTotal']):,.2f}</div>

            <div>GST</div>
            <div>{float(header['GSTAmount']):,.2f}</div>

            <div class="thermal-grand">TOTAL</div>
            <div class="thermal-grand">₹{float(header['GrandTotal']):,.2f}</div>

            <div>Paid</div>
            <div>{float(header['AmountPaid']):,.2f}</div>

            <div>Balance</div>
            <div>{float(header['BalanceAmount']):,.2f}</div>
        </div>

        <div class="thermal-line"></div>

        <div class="thermal-thanks">Thank You!</div>
        <div class="thermal-center">Visit Again</div>
        <div class="thermal-note">*** KEEP THIS BILL FOR YOUR RECORDS ***</div>
    </div>
    """

    # Use a browser-side button so the click directly triggers
    # window.open() and window.print(). This avoids Streamlit reruns
    # and prevents the receipt HTML from being referenced too early.
    import streamlit.components.v1 as components
    import json

    print_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Bill #{sale_id}</title>
        <style>
            @page {{
                size: 80mm auto;
                margin: 0;
            }}

            html, body {{
                margin: 0;
                padding: 0;
                background: white;
            }}

            body {{
                width: 80mm;
                font-family: "Courier New", monospace;
                color: #111;
            }}

            .thermal-receipt {{
                width: 72mm;
                margin: 0 auto;
                padding: 3mm 2mm;
                box-sizing: border-box;
                font-family: "Courier New", monospace;
                font-size: 10px;
                line-height: 1.35;
            }}

            .thermal-center {{ text-align: center; }}
            .thermal-shop {{
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            .thermal-line {{
                border-top: 1px dashed #000;
                margin: 7px 0;
            }}
            .thermal-meta {{
                display: grid;
                grid-template-columns: 22mm 1fr;
                gap: 1px 2px;
                word-break: break-word;
            }}
            .thermal-items {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
            }}
            .thermal-items th,
            .thermal-items td {{
                padding: 2px 0;
                vertical-align: top;
                font-family: "Courier New", monospace;
                font-size: 9px;
            }}
            .thermal-items th {{
                border-bottom: 1px dashed #000;
            }}
            .thermal-items .item {{
                width: 43%;
                text-align: left;
                word-break: break-word;
            }}
            .thermal-items .qty {{
                width: 12%;
                text-align: right;
            }}
            .thermal-items .rate {{
                width: 20%;
                text-align: right;
            }}
            .thermal-items .amt {{
                width: 25%;
                text-align: right;
            }}
            .thermal-total {{
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 5px;
                text-align: right;
            }}
            .thermal-grand {{
                font-size: 13px;
                font-weight: bold;
                padding: 4px 0;
            }}
            .thermal-thanks {{
                text-align: center;
                font-weight: bold;
                margin-top: 8px;
            }}
            .thermal-note {{
                text-align: center;
                font-size: 8px;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        {receipt_html}
    </body>
    </html>
    """

    encoded_print_html = json.dumps(print_html)

    components.html(
        f"""
        <button
            onclick="printBill()"
            style="
                width:100%;
                height:40px;
                border:1px solid #d0d5dd;
                border-radius:8px;
                background:#f8fafc;
                color:#374151;
                font-size:14px;
                cursor:pointer;
            "
        >
            🖨️ Print Bill
        </button>

        <script>
        function printBill() {{
            const billHtml = {encoded_print_html};

            const printWindow = window.open(
                "",
                "thermal_bill_{sale_id}",
                "width=420,height=800,scrollbars=yes"
            );

            if (!printWindow) {{
                alert(
                    "Pop-up blocked. Please allow pop-ups for localhost and try again."
                );
                return;
            }}

            printWindow.document.open();
            printWindow.document.write(billHtml);
            printWindow.document.close();

            printWindow.onload = function() {{
                setTimeout(function() {{
                    printWindow.focus();
                    printWindow.print();
                }}, 250);
            }};
        }}
        </script>
        """,
        height=48,
        scrolling=False,
    )

    # Render as real HTML. Do NOT use st.write/st.code here,
    # otherwise the receipt markup appears as source code.
    st.html(
        f"""
        <style>
            .thermal-receipt {{
                width: 320px;
                max-width: 100%;
                margin: 0 auto;
                padding: 18px 16px;
                background: #ffffff;
                color: #111111;
                font-family: "Courier New", monospace;
                font-size: 12px;
                line-height: 1.35;
                box-sizing: border-box;
                border: 1px solid #dddddd;
                box-shadow: 0 3px 12px rgba(0,0,0,0.10);
            }}

            .thermal-center {{ text-align: center; }}
            .thermal-shop {{
                font-size: 20px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            .thermal-line {{
                border-top: 1px dashed #333;
                margin: 8px 0;
            }}
            .thermal-meta {{
                display: grid;
                grid-template-columns: 76px 1fr;
                column-gap: 5px;
                row-gap: 2px;
                word-break: break-word;
            }}
            .thermal-items {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
            }}
            .thermal-items th,
            .thermal-items td {{
                padding: 2px 0;
                vertical-align: top;
                border: 0;
                font-family: "Courier New", monospace;
                font-size: 11px;
            }}
            .thermal-items th {{
                border-bottom: 1px dashed #333;
                padding-bottom: 4px;
            }}
            .thermal-items .item {{
                width: 43%;
                text-align: left;
                word-break: break-word;
            }}
            .thermal-items .qty {{
                width: 12%;
                text-align: right;
            }}
            .thermal-items .rate {{
                width: 20%;
                text-align: right;
            }}
            .thermal-items .amt {{
                width: 25%;
                text-align: right;
            }}
            .thermal-total {{
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 8px;
                text-align: right;
            }}
            .thermal-grand {{
                font-size: 16px;
                font-weight: 800;
                padding: 6px 0;
            }}
            .thermal-thanks {{
                text-align: center;
                font-weight: 700;
                margin-top: 10px;
            }}
            .thermal-note {{
                text-align: center;
                font-size: 10px;
                margin-top: 6px;
            }}

            @media print {{
                .thermal-receipt {{
                    width: 72mm !important;
                    max-width: 72mm !important;
                    margin: 0 !important;
                    padding: 3mm 2mm !important;
                    border: 0 !important;
                    box-shadow: none !important;
                    font-size: 10px !important;
                }}

                .thermal-shop {{
                    font-size: 17px !important;
                }}

                .thermal-items th,
                .thermal-items td {{
                    font-size: 9px !important;
                }}

                .thermal-grand {{
                    font-size: 13px !important;
                }}
            }}
        </style>

        {receipt_html}
        """
    )


# ---------------------------------------------------------
# COMMON PERIOD FILTER
# ---------------------------------------------------------
st.subheader("📅 Report Period")

period_col1, period_col2 = st.columns([1.2, 3])

with period_col1:
    report_period = st.selectbox(
        "Show",
        [
            "Today",
            "This Week",
            "This Month",
            "This Year",
            "All",
        ],
        key="my_sales_report_period",
    )

today = date.today()

if report_period == "Today":
    from_date = today
    to_date = today

elif report_period == "This Week":
    # Monday through Sunday
    from_date = today - timedelta(days=today.weekday())
    to_date = from_date + timedelta(days=6)

elif report_period == "This Month":
    from_date = today.replace(day=1)

    if today.month == 12:
        next_month = today.replace(
            year=today.year + 1,
            month=1,
            day=1,
        )
    else:
        next_month = today.replace(
            month=today.month + 1,
            day=1,
        )

    to_date = next_month - timedelta(days=1)

elif report_period == "This Year":
    from_date = today.replace(month=1, day=1)
    to_date = today.replace(month=12, day=31)

else:
    # "All" uses a broad historical range. The SQL query still
    # remains date-safe while effectively including all records.
    from_date = date(2000, 1, 1)
    to_date = today

with period_col2:
    if report_period == "All":
        st.info("Showing all available sales and cash transactions.")
    else:
        st.info(
            f"Showing {report_period.lower()}: "
            f"{from_date.strftime('%d-%m-%Y')} to "
            f"{to_date.strftime('%d-%m-%Y')}"
        )


# ---------------------------------------------------------
# LOAD SALES
# ---------------------------------------------------------
try:
    sales = load_sales(from_date, to_date)
except Exception as e:
    st.error(f"Unable to load sales data: {e}")
    st.stop()

try:
    cash_transactions = load_cash_transactions(from_date, to_date)
except Exception as e:
    st.error(f"Unable to load cash transaction history: {e}")
    cash_transactions = pd.DataFrame(
        columns=[
            "CashTransactionID",
            "TransactionDateTime",
            "TransactionType",
            "Amount",
            "Reason",
            "CashDrawerID",
        ]
    )


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------
total_bills = len(sales)
total_sales = (
    float(sales["GrandTotal"].sum())
    if not sales.empty
    else 0
)
total_gst = (
    float(sales["GSTAmount"].sum())
    if not sales.empty
    else 0
)
average_bill = (
    total_sales / total_bills
    if total_bills
    else 0
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("Bills", total_bills)
c2.metric("Total Sales", money(total_sales))
c3.metric("GST", money(total_gst))
c4.metric("Average Bill", money(average_bill))


st.divider()


# ---------------------------------------------------------
# PAYMENT SUMMARY
# ---------------------------------------------------------
if not sales.empty:
    st.subheader("Payment Summary")

    payment_summary = (
        sales.groupby("PaymentMode", dropna=False)["GrandTotal"]
        .sum()
        .reset_index()
    )

    payment_summary["PaymentMode"] = payment_summary["PaymentMode"].fillna(
        "Unknown"
    )
    payment_summary["GrandTotal"] = payment_summary["GrandTotal"].apply(money)

    st.dataframe(
        payment_summary,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# PROFESSIONAL PAGINATED BILL TABLE
# ---------------------------------------------------------
st.divider()
st.subheader("🧾 My Bills")

st.caption("Click 👁️ to view the complete itemized bill.")

# Professional table styling
st.markdown(
    """
    <style>
    .sales-table-header {
        background: linear-gradient(90deg, #1f2937, #374151);
        color: white;
        padding: 9px 6px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 13px;
        text-align: left;
        margin-bottom: 5px;
        white-space: nowrap;
        overflow: hidden;
    }

    .sales-row {
        border-bottom: 1px solid #e5e7eb;
        padding: 7px 3px;
        min-height: 42px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 14px;
    }

    .sales-row:hover {
        background-color: rgba(128, 128, 128, 0.08);
    }

    .bill-number {
        font-weight: 600;
    }

    .bill-total {
        font-weight: 700;
    }

    .pagination-info {
        text-align: center;
        padding-top: 8px;
        font-weight: 600;
    }

    @media print {
        body * {
            visibility: hidden !important;
        }

        [role="dialog"],
        [role="dialog"] * {
            visibility: visible !important;
        }

        [role="dialog"] {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            box-shadow: none !important;
        }

        [role="dialog"] button {
            display: none !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Pagination settings
PAGE_SIZE_OPTIONS = [10, 20, 30, 50]

pagination_col1, pagination_col2, pagination_col3 = st.columns([1, 1, 2])

with pagination_col1:
    page_size = st.selectbox(
        "Bills per page",
        PAGE_SIZE_OPTIONS,
        index=0,
        key="my_sales_page_size",
    )

total_records = len(sales)
total_pages = max(1, (total_records + page_size - 1) // page_size)

# Reset page when page size changes or date range changes
filter_key = f"{from_date}_{to_date}_{page_size}"
if st.session_state.get("my_sales_filter_key") != filter_key:
    st.session_state.my_sales_filter_key = filter_key
    st.session_state.my_sales_page = 1

current_page = int(st.session_state.get("my_sales_page", 1))

if current_page > total_pages:
    current_page = total_pages
    st.session_state.my_sales_page = current_page

with pagination_col2:
    if total_pages > 1:
        page_number = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            key="my_sales_page_number",
        )

        if page_number != current_page:
            st.session_state.my_sales_page = int(page_number)
            st.rerun()

with pagination_col3:
    first_record = ((current_page - 1) * page_size) + 1
    last_record = min(current_page * page_size, total_records)

    st.markdown(
        f"""
        <div class="pagination-info">
            Showing {first_record}–{last_record} of {total_records} bills
            &nbsp; • &nbsp; Page {current_page} of {total_pages}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Previous / Next controls
nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])

with nav1:
    if st.button(
        "⏮ First",
        disabled=current_page <= 1,
        use_container_width=True,
        key="sales_first",
    ):
        st.session_state.my_sales_page = 1
        st.rerun()

with nav2:
    if st.button(
        "◀ Previous",
        disabled=current_page <= 1,
        use_container_width=True,
        key="sales_previous",
    ):
        st.session_state.my_sales_page = current_page - 1
        st.rerun()

with nav3:
    st.markdown(
        f"""
        <div class="pagination-info">
            Page {current_page} / {total_pages}
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav4:
    if st.button(
        "Next ▶",
        disabled=current_page >= total_pages,
        use_container_width=True,
        key="sales_next",
    ):
        st.session_state.my_sales_page = current_page + 1
        st.rerun()

with nav5:
    if st.button(
        "Last ⏭",
        disabled=current_page >= total_pages,
        use_container_width=True,
        key="sales_last",
    ):
        st.session_state.my_sales_page = total_pages
        st.rerun()

st.write("")

# Current page records
start_index = (current_page - 1) * page_size
end_index = start_index + page_size
page_sales = sales.iloc[start_index:end_index]

# Header
h = st.columns(
    [0.65, 0.90, 1.25, 1.65, 0.85, 1.05, 0.95, 0.95],
    wrap=False,
)

headers = [
    "View",
    "Bill No.",
    "Date",
    "Customer",
    "Payment",
    "Total",
    "Paid",
    "Balance",
]

for col, header in zip(h, headers):
    with col:
        st.markdown(
            f'<div class="sales-table-header">{header}</div>',
            unsafe_allow_html=True,
        )

# Rows
for _, row in page_sales.iterrows():
    sale_id = int(row["SaleID"])
    sale_date = pd.to_datetime(row["SaleDate"])

    cols = st.columns(
        [0.65, 0.90, 1.25, 1.65, 0.85, 1.05, 0.95, 0.95],
        wrap=False,
    )

    with cols[0]:
        if st.button(
            "👁️",
            key=f"view_bill_{sale_id}",
            help=f"View Bill #{sale_id}",
            use_container_width=True,
        ):
            show_bill_popup(sale_id)

    with cols[1]:
        st.markdown(
            f'<div class="sales-row bill-number">#{sale_id}</div>',
            unsafe_allow_html=True,
        )

    with cols[2]:
        st.markdown(
            f'<div class="sales-row">{sale_date.strftime("%d-%m-%y %H:%M")}</div>',
            unsafe_allow_html=True,
        )

    with cols[3]:
        customer = str(row["CustomerName"] or "Walk-in Customer")
        customer_short = (
            customer if len(customer) <= 22 else customer[:20] + "…"
        )
        st.markdown(
            f'<div class="sales-row" title="{customer}">{customer_short}</div>',
            unsafe_allow_html=True,
        )

    with cols[4]:
        st.markdown(
            f'<div class="sales-row">{row["PaymentMode"] or "-"}</div>',
            unsafe_allow_html=True,
        )

    with cols[5]:
        st.markdown(
            f'<div class="sales-row bill-total">{money(row["GrandTotal"])}</div>',
            unsafe_allow_html=True,
        )

    with cols[6]:
        st.markdown(
            f'<div class="sales-row">{money(row["AmountPaid"])}</div>',
            unsafe_allow_html=True,
        )

    with cols[7]:
        st.markdown(
            f'<div class="sales-row">{money(row["BalanceAmount"])}</div>',
            unsafe_allow_html=True,
        )

# Bottom pagination
st.write("")
bottom1, bottom2, bottom3 = st.columns([1, 2, 1])

with bottom1:
    if st.button(
        "◀ Previous",
        disabled=current_page <= 1,
        use_container_width=True,
        key="sales_previous_bottom",
    ):
        st.session_state.my_sales_page = current_page - 1
        st.rerun()

with bottom2:
    st.markdown(
        f"""
        <div class="pagination-info">
            Showing <b>{first_record}</b> to <b>{last_record}</b>
            of <b>{total_records}</b> bills
        </div>
        """,
        unsafe_allow_html=True,
    )

with bottom3:
    if st.button(
        "Next ▶",
        disabled=current_page >= total_pages,
        use_container_width=True,
        key="sales_next_bottom",
    ):
        st.session_state.my_sales_page = current_page + 1
        st.rerun()


# ---------------------------------------------------------
# CASH TRANSACTION HISTORY
# ---------------------------------------------------------
st.divider()
st.subheader("💵 Cash Transaction History")
st.caption(
    "Cash In and Cash Out transactions recorded for your account "
    "during the selected date range."
)

if cash_transactions.empty:
    st.info("No cash transactions found for the selected date range.")
else:
    tx = cash_transactions.copy()
    tx["TransactionType"] = tx["TransactionType"].fillna("-")
    tx["Reason"] = tx["Reason"].fillna("-")
    tx["TransactionDateTime"] = pd.to_datetime(tx["TransactionDateTime"])

    cash_in = float(
        tx.loc[
            tx["TransactionType"].str.strip().str.lower() == "cash in",
            "Amount",
        ].sum()
    )
    cash_out = float(
        tx.loc[
            tx["TransactionType"].str.strip().str.lower().isin(
                ["cash out", "expense"]
            ),
            "Amount",
        ].sum()
    )

    ci, co, net = st.columns(3)
    ci.metric("Cash In", money(cash_in))
    co.metric("Cash Out", money(cash_out))
    net.metric("Net Transactions", money(cash_in - cash_out))

    tx_display = tx.copy()
    tx_display["Date & Time"] = tx_display["TransactionDateTime"].apply(
        lambda x: x.strftime("%d-%m-%Y %H:%M")
    )
    tx_display["Type"] = tx_display["TransactionType"]
    tx_display["Amount"] = tx_display["Amount"].apply(money)
    tx_display["Reason"] = tx_display["Reason"].apply(
        lambda x: str(x) if len(str(x)) <= 70 else str(x)[:67] + "..."
    )

    tx_display = tx_display[
        [
            "CashTransactionID",
            "Date & Time",
            "Type",
            "Amount",
            "Reason",
            "CashDrawerID",
        ]
    ].rename(
        columns={
            "CashTransactionID": "Txn ID",
            "CashDrawerID": "Drawer",
        }
    )

    st.dataframe(
        tx_display,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Download Cash Transaction History",
        data=tx_display.to_csv(index=False).encode("utf-8"),
        file_name=f"my_cash_transactions_{report_period.replace(" ", "_").lower()}.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ---------------------------------------------------------
# DAILY SALES
# ---------------------------------------------------------
st.divider()
st.subheader("Daily Sales")

daily = (
    sales.assign(
        Date=pd.to_datetime(sales["SaleDate"]).dt.date
    )
    .groupby("Date")["GrandTotal"]
    .sum()
    .sort_index()
)

if not daily.empty:
    st.bar_chart(daily)


# ---------------------------------------------------------
# CSV
# ---------------------------------------------------------
csv_data = sales.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇️ Download Sales CSV",
    data=csv_data,
    file_name=f"my_sales_{report_period.replace(" ", "_").lower()}.csv",
    mime="text/csv",
    use_container_width=True,
)
