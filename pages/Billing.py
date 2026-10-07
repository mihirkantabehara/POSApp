import html
from datetime import datetime
from urllib.parse import quote
import re

import pandas as pd
import streamlit as st
from logging_config import log_exception
import streamlit.components.v1 as components
from sqlalchemy import text

from auth import require_role
from database.database import engine

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
try:
    st.set_page_config(page_title="Billing / POS", page_icon="🧾", layout="wide")
except Exception:
    pass  # already configured by the main app

user = require_role("Sales Boy", "Manager", "Admin")

STYLES = """
<style>
:root{
  --pos-blue:#2563eb;
  --pos-green:#15803d;
  --pos-ink:#0f172a;
  --pos-muted:#64748b;
  --pos-line:#e2e8f0;
  --pos-surface:#ffffff;
  --pos-bg:#f6f8fb;
}
.stApp{background:var(--pos-bg);}
.block-container{padding-top:2.6rem;padding-bottom:1rem;max-width:1500px;}
header[data-testid="stHeader"]{background:transparent;}

/* tighter vertical rhythm everywhere */
div[data-testid="stVerticalBlock"]{gap:.5rem;}
div[data-testid="stHorizontalBlock"]{gap:.6rem;}
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--pos-surface);
  border-radius:12px;
  box-shadow:0 1px 2px rgba(15,23,42,.05);
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"]{gap:.4rem;}
div[data-testid="stElementContainer"]{margin:0;}
/* Streamlit pulls markdown up by -1rem to offset <p> margins; our blocks are
   plain divs, so cancel it or titles get overlapped by the next element. */
div[data-testid="stMarkdown"],
div[data-testid="stMarkdownContainer"],
.stMarkdown{margin-bottom:0 !important;}
div[data-testid="stMarkdownContainer"] > div{margin:0;}
.pos-h{padding:2px 0 4px 0;}

/* card title */
.pos-h{
  margin:0;font-size:.82rem;font-weight:700;color:var(--pos-ink);
  display:flex;align-items:center;gap:6px;line-height:1.2;
}

/* top bar */
.pos-top{display:flex;justify-content:flex-start;margin-bottom:2px;}
.pos-chips{display:flex;gap:8px;flex-wrap:wrap;}
.pos-chip{
  background:var(--pos-surface);border:1px solid var(--pos-line);border-radius:10px;
  padding:4px 12px;min-width:120px;
}
.pos-chip span{display:block;font-size:.66rem;color:var(--pos-muted);}
.pos-chip strong{display:block;font-size:.82rem;color:var(--pos-ink);}
.pos-chip strong.ok{color:var(--pos-green);}

/* payment totals */
.pos-pay{
  display:grid;grid-template-columns:1fr 1fr;gap:10px;
  background:linear-gradient(180deg,#eff6ff 0%,#ffffff 80%);
  border:1px solid #dbe6fb;border-radius:12px;padding:10px 14px;
}
.pos-pay .label{font-size:.75rem;color:#334155;}
.pos-pay .big{font-size:1.7rem;font-weight:800;color:var(--pos-green);line-height:1.15;}
.pos-pay .change{font-size:1.7rem;font-weight:800;color:var(--pos-blue);line-height:1.15;}
.pos-pay .change.due{color:#dc2626;}

/* summary strip */
.pos-summary{
  background:var(--pos-surface);
  border:1px solid var(--pos-line);
  border-radius:12px;
  padding:8px 12px;
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:8px;
  align-items:center;
  box-shadow:0 1px 2px rgba(15,23,42,.05);
}
.pos-summary div{min-width:0;text-align:center;}
.pos-summary div span{
  display:block;font-size:.68rem;color:var(--pos-muted);white-space:nowrap;margin-bottom:2px;
}
.pos-summary div strong{
  display:block;font-size:1rem;font-weight:800;color:var(--pos-ink);
  white-space:nowrap;line-height:1.2;
}
.pos-summary div strong.total{color:var(--pos-green);}

/* compact inputs */
.stTextInput input,
.stNumberInput input{
  font-size:.85rem;padding:5px 10px;height:34px;border-radius:8px;
}
div[data-baseweb="select"]>div{
  font-size:.85rem;min-height:34px;border-radius:8px;
}
div[data-baseweb="select"] div[role="button"]{padding-top:2px;padding-bottom:2px;}
.stNumberInput button{height:17px;}
.stTextInput label,.stNumberInput label,.stSelectbox label{
  font-size:.75rem;color:var(--pos-muted);margin-bottom:0;
}
div[data-testid="stWidgetLabel"]{min-height:0;margin-bottom:0;}
div[data-testid="stWidgetLabel"] p{font-size:.75rem;}
div[data-testid="stCaptionContainer"]{margin:0;line-height:1.2;}

.billing-stock{
  margin:0 0 0 2px;
  font-size:.74rem;
  font-weight:700;
  line-height:1.1;
  color:var(--pos-muted);
}

/* buttons */
.stButton>button,
.stFormSubmitButton>button,
.stLinkButton>a{
  border-radius:8px;font-weight:600;border:1px solid var(--pos-line);
  font-size:.82rem;padding:4px 10px;min-height:34px;
}
.stButton>button[kind="primary"],
.stFormSubmitButton>button[kind="primaryFormSubmit"],
.stFormSubmitButton>button[kind="primary"]{
  background:var(--pos-blue);border-color:var(--pos-blue);color:#fff;
}
.stButton>button p,.stFormSubmitButton>button p{white-space:nowrap;}
div[data-testid="stForm"]{border:0;padding:0;}

.pos-empty{
  border:1px dashed #cbd5e1;border-radius:10px;padding:18px 12px;text-align:center;
  color:var(--pos-muted);background:#fbfdff;font-size:.85rem;
}
</style>
"""
st.markdown(STYLES, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def money(value: float) -> str:
    return f"₹{value:,.2f}"


def build_whatsapp_bill_url(invoice: dict, mobile: str) -> str:
    digits = re.sub(r"\D", "", str(mobile or ""))
    if len(digits) == 10:
        digits = "91" + digits

    items_text = "\n".join(
        f"{item['Product']} x {item['Qty']:g} = ₹{item['Amount']:.2f}"
        for item in invoice["items"]
    )

    message = (
        "*MY SHOP - BILL*\n"
        f"Bill No: {invoice['sale_id']}\n"
        f"Date: {invoice['when']}\n"
        f"Customer: {invoice['customer']}\n"
        f"Salesperson: {invoice['salesperson']}\n\n"
        f"{items_text}\n\n"
        f"Subtotal: ₹{invoice['subtotal']:.2f}\n"
        f"GST: ₹{invoice['gst']:.2f}\n"
        f"*Total: ₹{invoice['grand_total']:.2f}*\n"
        f"Paid: ₹{invoice['amount_paid']:.2f}\n"
        f"Change: ₹{invoice['change']:.2f}\n\n"
        "Thank you, visit again!"
    )

    return f"https://web.whatsapp.com/send?phone={digits}&text={quote(message)}"


def build_invoice_html(invoice: dict) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(x['Product']))}</td>"
        f"<td class='right'>{x['Qty']:g}</td>"
        f"<td class='right'>₹{x['Price']:.2f}</td>"
        f"<td class='right'>₹{x['Amount']:.2f}</td></tr>"
        for x in invoice["items"]
    )

    phone_line = f" ({invoice['phone']})" if invoice.get("phone") else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Invoice {invoice['sale_id']}</title>
<style>
  *{{box-sizing:border-box;}}
  body{{font-family:'Courier New',Consolas,monospace;margin:0;padding:8px;
        background:#f1f5f9;color:#111;font-size:12px;}}
  .receipt{{max-width:280px;margin:0 auto;background:#fff;border:1px solid #ddd;
            border-radius:8px;padding:10px 12px;}}
  h2{{font-size:15px;margin:2px 0;text-align:center;}}
  .center{{text-align:center;}}
  p{{margin:4px 0;line-height:1.35;}}
  table{{width:100%;border-collapse:collapse;font-size:11px;margin-top:6px;}}
  th,td{{padding:2px 2px;text-align:left;}}
  th{{border-bottom:1px solid #000;}}
  td.right,th.right{{text-align:right;}}
  hr{{border:0;border-top:1px dashed #999;margin:6px 0;}}
  .total{{font-size:13px;font-weight:bold;}}
  h3{{font-size:12px;margin:4px 0;}}
  .print-btn{{
    display:block;width:100%;margin-top:10px;padding:7px;
    background:#2563eb;color:#fff;border:none;border-radius:7px;
    font-weight:700;font-size:12px;cursor:pointer;font-family:inherit;
  }}
  .print-btn:hover{{background:#1d4ed8;}}
  @media print{{
    body{{background:#fff;padding:0;}}
    .receipt{{border:none;border-radius:0;max-width:100%;padding:0;}}
    .print-btn{{display:none;}}
    @page{{size:80mm auto;margin:2mm;}}
  }}
</style></head><body>
<div class="receipt">
  <h2>MY SHOP</h2>
  <p class="center">Berhampur, Odisha</p>
  <hr>
  <p><b>Bill no:</b> {invoice['sale_id']}<br>
  <b>Date:</b> {invoice['when']}<br>
  <b>Customer:</b> {html.escape(str(invoice['customer']))}{phone_line}<br>
  <b>Salesperson:</b> {html.escape(str(invoice['salesperson']))}<br>
  <b>Payment:</b> {html.escape(str(invoice['payment_mode']))}</p>
  <hr>
  <table>
    <tr><th>Item</th><th class="right">Qty</th><th class="right">Rate</th><th class="right">Amt</th></tr>
    {rows}
  </table>
  <hr>
  <p class="right">Subtotal: ₹{invoice['subtotal']:.2f}<br>
  GST: ₹{invoice['gst']:.2f}<br>
  <span class="total">Total: ₹{invoice['grand_total']:.2f}</span></p>
  <p>Paid: ₹{invoice['amount_paid']:.2f}<br>Change: ₹{invoice['change']:.2f}</p>
  <hr>
  <h3 class="center">Thank you, visit again</h3>
  <button class="print-btn" onclick="window.print()">🖨️  Print</button>
</div>
</body></html>"""


@st.dialog("🧾 Invoice", width="small")
def invoice_dialog() -> None:
    invoice = st.session_state.last_invoice
    components.html(build_invoice_html(invoice), height=480, scrolling=True)


def card_title(title: str) -> None:
    """Small heading used at the top of each bordered card."""
    st.markdown(f'<div class="pos-h">{title}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=20, show_spinner=False)
def load_products() -> pd.DataFrame:
    return pd.read_sql(
        text("""
            SELECT
                "ProductID", "ProductName", "Barcode", "SellingPrice",
                "PurchasePrice", "Stock", "GSTPercent"
            FROM "Products"
            ORDER BY "ProductName"
            """),
        engine,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_customers() -> pd.DataFrame:
    return pd.read_sql(
        text("""
            SELECT "CustomerID", "CustomerName", "Mobile"
            FROM "Customers"
            ORDER BY "CustomerName"
            """),
        engine,
    )


def cart_totals(cart: list) -> tuple:
    subtotal = sum(x["Quantity"] * x["Price"] for x in cart)
    gst_total = sum(x["Quantity"] * x["Price"] * x["GSTPercent"] / 100 for x in cart)
    return subtotal, gst_total, subtotal + gst_total


def add_to_cart(row, quantity: float) -> str | None:
    """Add a product row to the cart. Returns an error message, or None on success."""
    product_id = int(row["ProductID"])
    stock = float(row["Stock"])
    existing = next(
        (x for x in st.session_state.cart if x["ProductID"] == product_id), None
    )
    in_cart = existing["Quantity"] if existing else 0.0

    if stock <= 0:
        return f"{row['ProductName']} is out of stock."

    if in_cart + quantity > stock:
        return f"Only {stock:g} left in stock for {row['ProductName']}."

    if existing:
        existing["Quantity"] += quantity
    else:
        st.session_state.cart.append(
            {
                "ProductID": product_id,
                "ProductName": str(row["ProductName"]),
                "Quantity": float(quantity),
                "Price": float(row["SellingPrice"]),
                "PurchasePrice": float(row["PurchasePrice"]),
                "GSTPercent": float(row["GSTPercent"]),
            }
        )
    return None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
st.session_state.setdefault("cart", [])
st.session_state.setdefault("held_bills", [])
st.session_state.setdefault("flash", None)

# Clear customer inputs (after a new customer's sale) before their widgets exist.
if st.session_state.pop("clear_customer_fields", False):
    st.session_state["customer_phone"] = ""
    st.session_state["customer_name_input"] = ""

# ---------------------------------------------------------------------------
# Cash drawer gate
# ---------------------------------------------------------------------------
try:
    with engine.connect() as connection:
        drawer = (
            connection.execute(
                text("""
                    SELECT "CashDrawerID", "OpeningCash", "OpenDateTime"
                    FROM "CashDrawers"
                    WHERE "UserID" = :user_id AND "Status" = 'Open'
                    ORDER BY "CashDrawerID" DESC
                    LIMIT 1
                    """),
                {"user_id": user["UserID"]},
            )
            .mappings()
            .first()
        )
except Exception as exc:
    st.error("Cannot reach the database to check your cash drawer.")
    log_exception(exc)
    st.exception(exc)
    st.stop()

if not drawer:
    st.warning("Open your cash drawer before you start billing.")
    st.info("Go to **Cash in Hand** and enter your opening cash.")
    st.stop()

drawer_id = int(drawer["CashDrawerID"])

try:
    products = load_products()
    customers = load_customers()
except Exception as exc:
    st.error("Could not load products. Check the database connection.")
    log_exception(exc)
    st.exception(exc)
    st.stop()

if products.empty:
    st.warning("No products found. Add products before billing.")
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    f"""
<div class="pos-top">
<div class="pos-chips">
<div class="pos-chip"><span>Salesperson</span><strong>{html.escape(str(user['FullName']))}</strong></div>
<div class="pos-chip"><span>Role</span><strong>{html.escape(str(user['Role']))}</strong></div>
<div class="pos-chip"><span>Drawer</span><strong class="ok">#{drawer_id} (Open)</strong></div>
<div class="pos-chip"><span>Date &amp; time</span><strong>{datetime.now():%d-%b-%Y %H:%M}</strong></div>
</div>
</div>
""",
    unsafe_allow_html=True,
)

if st.session_state.flash:
    kind, message = st.session_state.flash
    getattr(st, kind)(message)
    st.session_state.flash = None

# ---------------------------------------------------------------------------
# Row 1 — scan / select / totals
# ---------------------------------------------------------------------------
scan_col, pick_col, info_col = st.columns([1.1, 2.3, 1.4], gap="small")

with scan_col:
    with st.container(border=True):
        card_title("🔍 Scan barcode")
        with st.form("barcode_form", clear_on_submit=True):
            barcode_col, scan_btn_col = st.columns([1.5, 1], gap="small")
            with barcode_col:
                barcode = st.text_input(
                    "Barcode",
                    placeholder="Scan / enter barcode",
                    label_visibility="collapsed",
                )
            with scan_btn_col:
                scanned = st.form_submit_button(
                    "➕ Add",
                    type="primary",
                    use_container_width=True,
                )

with pick_col:
    with st.container(border=True):
        card_title("📦 Select product")
        name_col, qty_col, add_col = st.columns([2.0, 0.8, 1.5], gap="small")

        with name_col:
            selected_name = st.selectbox(
                "Product",
                products["ProductName"].tolist(),
                key="manual_product",
                label_visibility="collapsed",
                placeholder="Search product...",
            )

        selected = products[products["ProductName"] == selected_name].iloc[0]
        available_stock = float(selected["Stock"])

        with qty_col:
            manual_qty = st.number_input(
                "Qty",
                min_value=0.01,
                value=1.0,
                step=1.0,
                key="manual_quantity",
                label_visibility="collapsed",
            )

        with add_col:
            manual_add = st.button(
                "➕ Add Product",
                use_container_width=True,
                type="primary",
                disabled=available_stock <= 0,
            )

        stock_label = (
            f"🟢 Available: {available_stock:g}"
            if available_stock > 0
            else "🔴 Out of stock"
        )
        st.markdown(
            f'<div class="billing-stock">{stock_label}</div>',
            unsafe_allow_html=True,
        )

subtotal, gst_total, grand_total = cart_totals(st.session_state.cart)

with info_col:
    st.markdown(
        f"""
<div class="pos-summary">
<div><span>Items</span><strong>{len(st.session_state.cart)}</strong></div>
<div><span>Subtotal</span><strong>{money(subtotal)}</strong></div>
<div><span>GST</span><strong>{money(gst_total)}</strong></div>
<div><span>Total</span><strong class="total">{money(grand_total)}</strong></div>
</div>
""",
        unsafe_allow_html=True,
    )

# --- handle adds -----------------------------------------------------------
if scanned:
    code = (barcode or "").strip()
    match = (
        products[products["Barcode"].astype(str).str.strip() == code]
        if code
        else pd.DataFrame()
    )
    if not code:
        st.session_state.flash = ("error", "Scan or type a barcode first.")
    elif match.empty:
        st.session_state.flash = ("error", f"No product matches barcode {code}.")
    else:
        error = add_to_cart(match.iloc[0], 1.0)
        st.session_state.flash = ("error", error) if error else None
    st.rerun()

if manual_add:
    error = add_to_cart(selected, float(manual_qty))
    if error:
        st.session_state.flash = ("error", error)
    st.rerun()

# ---------------------------------------------------------------------------
# Row 2 — cart | customer + payment
# ---------------------------------------------------------------------------
cart_col, side_col = st.columns([1.7, 1.1], gap="small")

with cart_col:
    with st.container(border=True):
        card_title(f"🛒 Cart ({len(st.session_state.cart)} items)")

        if not st.session_state.cart:
            st.markdown(
                '<div class="pos-empty">Cart is empty. Scan a barcode or pick a product to begin.</div>',
                unsafe_allow_html=True,
            )
        else:
            editor_rows = [
                {
                    "#": i + 1,
                    "Product": x["ProductName"],
                    "Price": x["Price"],
                    "GST %": x["GSTPercent"],
                    "Qty": x["Quantity"],
                    "Total": x["Quantity"] * x["Price"] * (1 + x["GSTPercent"] / 100),
                    "Remove": False,
                }
                for i, x in enumerate(st.session_state.cart)
            ]

            edited = st.data_editor(
                pd.DataFrame(editor_rows),
                key="cart_editor",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "#": st.column_config.NumberColumn("#", width="small", disabled=True),
                    "Product": st.column_config.TextColumn("Product", disabled=True),
                    "Price": st.column_config.NumberColumn(
                        "Price (₹)", format="%.2f", disabled=True
                    ),
                    "GST %": st.column_config.NumberColumn(
                        "GST %", format="%g", disabled=True
                    ),
                    "Qty": st.column_config.NumberColumn(
                        "Qty", min_value=0.0, step=1.0, format="%g"
                    ),
                    "Total": st.column_config.NumberColumn(
                        "Total (₹)", format="%.2f", disabled=True
                    ),
                    "Remove": st.column_config.CheckboxColumn("Remove", width="small"),
                },
            )

            # sync edits back into the cart
            changed = False
            new_cart = []
            for item, row in zip(st.session_state.cart, edited.to_dict("records")):
                qty = float(row["Qty"] or 0)
                stock = float(
                    products.loc[
                        products["ProductID"] == item["ProductID"], "Stock"
                    ].iloc[0]
                )

                if row["Remove"] or qty <= 0:
                    changed = True
                    continue

                if qty > stock:
                    st.session_state.flash = (
                        "error",
                        f"Only {stock:g} left in stock for {item['ProductName']}.",
                    )
                    qty = stock

                if qty != item["Quantity"]:
                    item["Quantity"] = qty
                    changed = True

                new_cart.append(item)

            if changed:
                st.session_state.cart = new_cart
                st.rerun()

with side_col:
    with st.container(border=True):
        card_title("👤 Customer")
        phone_col, name_col = st.columns([1, 1.3], gap="small")

        phone = phone_col.text_input(
            "Phone number", key="customer_phone", placeholder="10-digit mobile"
        ).strip()

        match = (
            customers[customers["Mobile"].astype(str).str.strip() == phone]
            if phone and not customers.empty
            else pd.DataFrame()
        )

        is_new_customer = False

        if not match.empty:
            customer_name = str(match.iloc[0]["CustomerName"])
            name_col.text_input("Customer", value=customer_name, disabled=True)
            st.caption(f"✅ Existing customer — {customer_name}")
        else:
            placeholder_name = "Walk-in Customer" if not phone else "New customer name"
            typed_name = name_col.text_input(
                "Customer name", key="customer_name_input", placeholder=placeholder_name
            ).strip()
            customer_name = typed_name or "Walk-in Customer"
            if phone:
                is_new_customer = True
                st.caption("🆕 New number — will be saved as a customer with this bill.")

    with st.container(border=True):
        card_title("💳 Payment")
        paid_col, mode_col = st.columns(2, gap="small")

        amount_paid = paid_col.number_input(
            "Amount received", min_value=0.0, value=float(grand_total), step=1.0
        )
        payment_mode = mode_col.selectbox("Payment mode", ["Cash", "UPI", "Card"])

        balance = amount_paid - grand_total

        if balance >= 0:
            change_html = (
                f'<div class="label">Change</div>'
                f'<div class="change">{money(balance)}</div>'
            )
        else:
            change_html = (
                f'<div class="label">Still due</div>'
                f'<div class="change due">{money(abs(balance))}</div>'
            )

        st.markdown(
            f'<div class="pos-pay">'
            f'<div><div class="label">Total amount</div>'
            f'<div class="big">{money(grand_total)}</div></div>'
            f"<div>{change_html}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Action row: complete sale + footer actions (single compact row)
# ---------------------------------------------------------------------------
held_count = len(st.session_state.held_bills)

a_complete, f1, f2, f3, f4 = st.columns([1.6, 1, 1, 1.2, 1.2], gap="small")

complete_sale = a_complete.button(
    "✅  Complete sale",
    type="primary",
    use_container_width=True,
    disabled=not st.session_state.cart,
)

if f1.button(
    "🗑️  Clear cart", use_container_width=True, disabled=not st.session_state.cart
):
    st.session_state.cart = []
    st.rerun()

if f2.button(
    "⏸️  Hold bill", use_container_width=True, disabled=not st.session_state.cart
):
    st.session_state.held_bills.append(
        {
            "customer": customer_name,
            "at": datetime.now().strftime("%H:%M"),
            "items": list(st.session_state.cart),
        }
    )
    st.session_state.cart = []
    st.session_state.flash = ("info", "Bill held. Retrieve it any time from this till.")
    st.rerun()

if f3.button(
    f"▶️  Retrieve held ({held_count})",
    use_container_width=True,
    disabled=held_count == 0,
):
    held = st.session_state.held_bills.pop()
    st.session_state.cart = held["items"]
    st.rerun()

with f4:
    if "last_invoice" in st.session_state:
        bill_no = st.session_state.last_invoice["sale_id"]
        if st.button(f"🖨️  Print bill #{bill_no}", use_container_width=True):
            invoice_dialog()
    else:
        st.button("🖨️  Print last bill", use_container_width=True, disabled=True)


# ---------------------------------------------------------------------------
# Save the sale (FEFO batch allocation)
# ---------------------------------------------------------------------------
def save_sale() -> None:
    bill_rows = [
        {
            "Product": x["ProductName"],
            "Qty": x["Quantity"],
            "Price": x["Price"],
            "GST %": x["GSTPercent"],
            "Amount": x["Quantity"] * x["Price"],
        }
        for x in st.session_state.cart
    ]

    with engine.begin() as connection:
        if is_new_customer:
            existing_id = connection.execute(
                text(
                    """SELECT "CustomerID" FROM "Customers" WHERE "Mobile" = :phone"""
                ),
                {"phone": phone},
            ).scalar()

            if not existing_id:
                connection.execute(
                    text("""
                        INSERT INTO "Customers" ("CustomerName", "Mobile")
                        VALUES (:name, :phone)
                        """),
                    {"name": customer_name, "phone": phone},
                )

        if payment_mode == "Cash":
            open_check = connection.execute(
                text("""
                    SELECT "CashDrawerID" FROM "CashDrawers"
                    WHERE "CashDrawerID" = :drawer_id
                      AND "UserID" = :user_id AND "Status" = 'Open'
                    """),
                {"drawer_id": drawer_id, "user_id": user["UserID"]},
            ).scalar()

            if not open_check:
                raise ValueError("The cash drawer is closed. Reopen it and try again.")

        sale_id = connection.execute(
            text("""
                INSERT INTO "Sales"
                ("CustomerName", "SubTotal", "GSTAmount", "GrandTotal",
                 "PaymentMode", "AmountPaid", "BalanceAmount", "UserID")
                VALUES
                (:customer, :subtotal, :gst, :grandtotal,
                 :payment_mode, :amount_paid, :balance, :user_id)
                RETURNING "SaleID"
                """),
            {
                "customer": customer_name,
                "subtotal": subtotal,
                "gst": gst_total,
                "grandtotal": grand_total,
                "payment_mode": payment_mode,
                "amount_paid": amount_paid,
                "balance": balance,
                "user_id": user["UserID"],
            },
        ).scalar()

        for item in st.session_state.cart:
            product_id = int(item["ProductID"])
            requested_qty = float(item["Quantity"])

            # FEFO: first expiry, first out. Expired batches are never sold.
            batches = (
                connection.execute(
                    text("""
                        SELECT
                            "BatchID", "BatchNo", "ExpiryDate", "PurchasePrice",
                            "SellingPrice", "GSTPercent", "Quantity"
                        FROM "ProductBatches"
                        WHERE "ProductID" = :product_id
                          AND "IsActive" = TRUE
                          AND "Quantity" > 0
                          AND "ExpiryDate" >= CURRENT_DATE
                        ORDER BY "ExpiryDate" ASC, "BatchID" ASC
                        FOR UPDATE
                        """),
                    {"product_id": product_id},
                )
                .mappings()
                .all()
            )

            remaining = requested_qty
            allocations = []

            for batch in batches:
                if remaining <= 0:
                    break

                allocated = min(remaining, float(batch["Quantity"]))

                if allocated > 0:
                    allocations.append(
                        {
                            "BatchID": int(batch["BatchID"]),
                            "BatchNo": str(batch["BatchNo"]),
                            "Quantity": allocated,
                            "PurchasePrice": float(batch["PurchasePrice"]),
                        }
                    )
                    remaining -= allocated

            if remaining > 0.000001:
                raise ValueError(
                    f"Not enough unexpired stock for {item['ProductName']}. "
                    f"Needed {requested_qty:g}, available {requested_qty - remaining:g}."
                )

            for allocation in allocations:
                batch_qty = allocation["Quantity"]
                purchase_price = allocation["PurchasePrice"]

                updated_batch = connection.execute(
                    text("""
                        UPDATE "ProductBatches"
                        SET "Quantity" = "Quantity" - :quantity
                        WHERE "BatchID" = :batch_id
                          AND "Quantity" >= :quantity
                          AND "IsActive" = TRUE
                          AND "ExpiryDate" >= CURRENT_DATE
                        """),
                    {"quantity": batch_qty, "batch_id": allocation["BatchID"]},
                )

                if updated_batch.rowcount == 0:
                    raise ValueError(
                        f"Batch {allocation['BatchNo']} was taken by another till. Retry the bill."
                    )

                connection.execute(
                    text("""
                        INSERT INTO "SaleItems"
                        ("SaleID", "ProductID", "BatchID", "Quantity", "Price",
                         "GSTPercent", "Amount", "PurchasePrice", "ProfitAmount")
                        VALUES
                        (:sale_id, :product_id, :batch_id, :quantity,
                         :price, :gst, :amount, :purchase_price, :profit_amount)
                        """),
                    {
                        "sale_id": sale_id,
                        "product_id": product_id,
                        "batch_id": allocation["BatchID"],
                        "quantity": batch_qty,
                        "price": item["Price"],
                        "gst": item["GSTPercent"],
                        "amount": batch_qty * float(item["Price"]),
                        "purchase_price": purchase_price,
                        "profit_amount": (float(item["Price"]) - purchase_price)
                        * batch_qty,
                    },
                )

            updated_product = connection.execute(
                text("""
                    UPDATE "Products"
                    SET "Stock" = "Stock" - :quantity
                    WHERE "ProductID" = :product_id AND "Stock" >= :quantity
                    """),
                {"quantity": requested_qty, "product_id": product_id},
            )

            if updated_product.rowcount == 0:
                raise ValueError(f"Stock summary is short for {item['ProductName']}.")

    st.session_state.last_invoice = {
        "sale_id": sale_id,
        "customer": customer_name,
        "phone": phone,
        "payment_mode": payment_mode,
        "subtotal": subtotal,
        "gst": gst_total,
        "grand_total": grand_total,
        "amount_paid": amount_paid,
        "change": balance,
        "salesperson": user["FullName"],
        "items": bill_rows,
        "when": datetime.now().strftime("%d-%b-%Y %H:%M"),
    }

    st.session_state.cart = []
    load_products.clear()

    if is_new_customer:
        load_customers.clear()
        # Widget keys can't be changed after the widgets are drawn in this run,
        # so ask the next run to clear them before they are created.
        st.session_state.clear_customer_fields = True

    st.session_state.open_invoice_dialog = True
    st.session_state.flash = ("success", f"Sale completed. Bill no. {sale_id}")


if complete_sale:
    if amount_paid < grand_total:
        st.session_state.flash = (
            "error",
            "Amount received is less than the bill total.",
        )
        st.rerun()

    try:
        save_sale()
        st.rerun()
    except Exception as exc:
        st.error(f"Sale not saved: {exc}")

if st.session_state.get("open_invoice_dialog") and "last_invoice" in st.session_state:
    st.session_state.open_invoice_dialog = False
    invoice_dialog()

# ---------------------------------------------------------------------------
# WhatsApp bill
# Free WhatsApp click-to-chat. Existing billing functionality is unchanged.
# ---------------------------------------------------------------------------
if "last_invoice" in st.session_state:
    with st.container(border=True):
        wa_col1, wa_col2 = st.columns([1.3, 1], gap="small")

        with wa_col1:
            whatsapp_mobile = st.text_input(
                "📱 Customer WhatsApp number",
                value=st.session_state.last_invoice.get("phone", ""),
                placeholder="📱 Customer WhatsApp number (10-digit)",
                key="whatsapp_bill_mobile",
                label_visibility="collapsed",
            ).strip()

        with wa_col2:
            if whatsapp_mobile:
                st.link_button(
                    "📱 Send Bill on WhatsApp",
                    build_whatsapp_bill_url(
                        st.session_state.last_invoice,
                        whatsapp_mobile,
                    ),
                    use_container_width=True,
                )
            else:
                st.button(
                    "📱 Send Bill on WhatsApp",
                    use_container_width=True,
                    disabled=True,
                )