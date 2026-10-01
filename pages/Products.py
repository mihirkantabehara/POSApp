import streamlit as st
from logging_config import log_exception
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text
from database.database import engine
from auth import require_role

# Camera barcode scanner
try:
    from pyzbar.pyzbar import decode as decode_barcodes
    from PIL import Image
    BARCODE_SCANNER_AVAILABLE = True
except ImportError:
    BARCODE_SCANNER_AVAILABLE = False


# =========================================================
# ACCESS
# =========================================================
user = require_role("Manager", "Admin")

st.set_page_config(
    page_title="Products",
    page_icon="📦",
    layout="wide",
)

#st.title("📦 Products")
st.caption(f"Logged in as: {user['FullName']} • {user['Role']}")

st.markdown(
    """
<style>
:root{
  --pos-ink:#0f172a;
  --pos-muted:#64748b;
  --pos-line:#e2e8f0;
  --pos-surface:#ffffff;
  --pos-blue:#2563eb;
  --pos-blue-soft:#eff6ff;
}

/* metrics strip */
.stats-card{
  background:var(--pos-surface);border:1px solid var(--pos-line);
  border-radius:12px;padding:14px 18px 4px 18px;margin-bottom:4px;
}

/* product table */
.product-table{
  border:1px solid var(--pos-line);border-radius:12px;
  overflow:hidden;background:var(--pos-surface);margin-top:6px;
}
.product-table div[data-testid="stHorizontalBlock"]{
  padding:9px 16px;border-bottom:1px solid var(--pos-line);
  align-items:center;
}
.product-table div[data-testid="stHorizontalBlock"]:first-of-type{
  background:#f8fafc;border-bottom:2px solid var(--pos-ink);
  padding-top:10px;padding-bottom:10px;
}
.product-table div[data-testid="stHorizontalBlock"]:not(:first-of-type):hover{
  background:#f8fafc;
}
.product-table div[data-testid="stHorizontalBlock"]:last-of-type{
  border-bottom:none;
}
.th-label{font-size:.74rem;font-weight:600;color:var(--pos-muted);}
.cell-name{font-size:.9rem;color:var(--pos-ink);font-weight:500;}
.cell-barcode{
  font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace;
  font-size:.8rem;color:var(--pos-muted);
}
.cell-num{
  font-variant-numeric:tabular-nums;font-size:.88rem;
  color:var(--pos-ink);text-align:right;
}
.stock-badge{
  display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;
  font-size:.68rem;font-weight:600;vertical-align:1px;
}
.stock-badge.low{background:#fef2f2;color:#b91c1c;}

/* icon-only edit button */
.product-table .stButton>button{
  background:transparent;border:1px solid transparent;
  padding:2px 9px;font-size:.95rem;border-radius:7px;min-height:0;
}
.product-table .stButton>button:hover{
  background:var(--pos-blue-soft);border-color:#dbeafe;
}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# SESSION STATE
# =========================================================
defaults = {
    "product_search": "",
    "new_barcode": "",
    "edit_barcode_value": "",
    "scanner_message": "",
    "product_page": 1,
    "product_page_size": 10,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# HELPERS
# =========================================================
def load_products(search=""):
    query = """
        SELECT
            ProductID,
            ProductName,
            Barcode,
            SellingPrice,
            PurchasePrice,
            Stock,
            GSTPercent
        FROM Products
    """

    params = {}

    if search.strip():
        query += """
            WHERE ProductName LIKE :search
               OR Barcode LIKE :search
        """
        params["search"] = f"%{search.strip()}%"

    query += " ORDER BY ProductName"

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        return pd.DataFrame(result.fetchall(), columns=result.keys())


def add_product(name, barcode, price, purchase_price, stock, gst, expiry_date):
    """
    Create a new product and, when an opening quantity is given, create
    its first stock batch too so FEFO billing has something to sell
    against immediately.
    """
    with engine.begin() as connection:
        # Prevent duplicate barcode.
        if barcode.strip():
            existing = connection.execute(
                text("""
                    SELECT ProductID
                    FROM Products
                    WHERE Barcode = :barcode
                """),
                {"barcode": barcode.strip()},
            ).first()

            if existing:
                raise ValueError(
                    f"Barcode {barcode.strip()} already exists "
                    f"for Product ID {existing[0]}."
                )

        product_id = connection.execute(
            text("""
                INSERT INTO Products
                (
                    ProductName,
                    Barcode,
                    SellingPrice,
                    PurchasePrice,
                    Stock,
                    GSTPercent
                )
                OUTPUT INSERTED.ProductID
                VALUES
                (
                    :name,
                    :barcode,
                    :price,
                    :purchase_price,
                    :stock,
                    :gst
                )
            """),
            {
                "name": name.strip(),
                "barcode": barcode.strip(),
                "price": float(price),
                "purchase_price": float(purchase_price),
                "stock": float(stock),
                "gst": float(gst),
            },
        ).scalar()

        # The opening stock becomes Batch 1 for this product.
        if float(stock) > 0:
            batch_no = f"P{product_id}-B1"

            connection.execute(
                text("""
                    INSERT INTO ProductBatches
                    (
                        ProductID,
                        BatchNo,
                        ExpiryDate,
                        PurchasePrice,
                        SellingPrice,
                        GSTPercent,
                        Quantity,
                        IsActive
                    )
                    VALUES
                    (
                        :product_id,
                        :batch_no,
                        :expiry_date,
                        :purchase_price,
                        :selling_price,
                        :gst,
                        :quantity,
                        1
                    )
                """),
                {
                    "product_id": product_id,
                    "batch_no": batch_no,
                    "expiry_date": expiry_date,
                    "purchase_price": float(purchase_price),
                    "selling_price": float(price),
                    "gst": float(gst),
                    "quantity": float(stock),
                },
            )

        return product_id


def update_product(product_id, name, barcode, price, gst):
    with engine.begin() as connection:
        if barcode.strip():
            existing = connection.execute(
                text("""
                    SELECT ProductID
                    FROM Products
                    WHERE Barcode = :barcode
                      AND ProductID <> :product_id
                """),
                {
                    "barcode": barcode.strip(),
                    "product_id": int(product_id),
                },
            ).first()

            if existing:
                raise ValueError(
                    f"Barcode {barcode.strip()} is already assigned "
                    f"to Product ID {existing[0]}."
                )

        connection.execute(
            text("""
                UPDATE Products
                SET
                    ProductName = :name,
                    Barcode = :barcode,
                    SellingPrice = :price,
                    GSTPercent = :gst
                WHERE ProductID = :product_id
            """),
            {
                "product_id": int(product_id),
                "name": name.strip(),
                "barcode": barcode.strip(),
                "price": float(price),
                "gst": float(gst),
            },
        )


def load_product_batches(product_id):
    query = text("""
        SELECT
            BatchID,
            BatchNo,
            ManufacturingDate,
            ExpiryDate,
            PurchasePrice,
            SellingPrice,
            GSTPercent,
            Quantity,
            IsActive
        FROM ProductBatches
        WHERE ProductID = :product_id
          AND IsActive = 1
        ORDER BY ExpiryDate ASC, BatchID ASC
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"product_id": int(product_id)},
        )
        return pd.DataFrame(
            result.fetchall(),
            columns=result.keys(),
        )


def adjust_batch_stock(batch_id, quantity_change):
    """Update one exact batch and the product total atomically."""
    with engine.begin() as connection:
        batch = connection.execute(
            text("""
                SELECT
                    BatchID,
                    ProductID,
                    BatchNo,
                    Quantity
                FROM ProductBatches WITH (UPDLOCK, ROWLOCK)
                WHERE BatchID = :batch_id
                  AND IsActive = 1
            """),
            {"batch_id": int(batch_id)},
        ).mappings().first()

        if not batch:
            raise ValueError("Selected batch was not found or is inactive.")

        current_qty = float(batch["Quantity"] or 0)
        change = float(quantity_change)

        if change == 0:
            raise ValueError("Quantity must be greater than zero.")

        if current_qty + change < 0:
            raise ValueError(
                f"Batch {batch['BatchNo']} has only {current_qty:g} units."
            )

        result = connection.execute(
            text("""
                UPDATE ProductBatches
                SET Quantity = Quantity + :change
                WHERE BatchID = :batch_id
                  AND IsActive = 1
                  AND Quantity + :change >= 0
            """),
            {
                "batch_id": int(batch_id),
                "change": change,
            },
        )

        if result.rowcount != 1:
            raise ValueError("Batch quantity could not be updated.")

        result = connection.execute(
            text("""
                UPDATE Products
                SET Stock = Stock + :change
                WHERE ProductID = :product_id
                  AND Stock + :change >= 0
            """),
            {
                "product_id": int(batch["ProductID"]),
                "change": change,
            },
        )

        if result.rowcount != 1:
            raise ValueError("Product total stock could not be updated.")

        return {
            "ProductID": int(batch["ProductID"]),
            "BatchNo": str(batch["BatchNo"]),
            "OldQuantity": current_qty,
            "NewQuantity": current_qty + change,
        }


def scan_barcode_from_camera(camera_key):
    """
    Capture one image from the browser camera and decode common
    1D/2D barcodes using pyzbar.
    """
    if not BARCODE_SCANNER_AVAILABLE:
        st.error(
            "Camera barcode scanning is not installed. "
            "Run: pip install pyzbar pillow"
        )
        return None

    picture = st.camera_input(
        "📷 Point the camera at the barcode and capture",
        key=camera_key,
        resolution="720p",
    )

    if picture is None:
        return None

    try:
        image = Image.open(picture)
        results = decode_barcodes(image)

        if not results:
            st.warning(
                "No barcode detected. Hold the barcode straight, "
                "fill the camera view, and capture again."
            )
            return None

        # Prefer the first detected barcode.
        barcode_value = results[0].data.decode(
            "utf-8",
            errors="ignore",
        ).strip()

        if not barcode_value:
            st.warning("Barcode was detected but contains no readable value.")
            return None

        return barcode_value

    except Exception as exc:
        st.error(f"Could not read the barcode image: {exc}")
        return None


@st.dialog("✏️ Edit Product", width="small")
def edit_product_dialog(row):
    """
    Compact popup to edit one product. Opened from the ✏️ icon on
    that product's row in the product list table.
    """
    product_id = int(row.ProductID)

    current_barcode = (
        "" if pd.isna(row.Barcode) else str(row.Barcode)
    )

    edit_name = st.text_input(
        "Product Name",
        value=str(row.ProductName),
        key=f"edit_name_{product_id}",
    )

    edit_barcode = st.text_input(
        "Barcode",
        value=current_barcode,
        key=f"edit_barcode_{product_id}",
    )

    scan_edit = st.checkbox(
        "📷 Scan Barcode",
        key=f"scan_edit_{product_id}",
    )

    if scan_edit:
        scanned_edit = scan_barcode_from_camera(f"edit_camera_{product_id}")

        if scanned_edit:
            st.session_state[f"edit_barcode_{product_id}"] = scanned_edit
            st.success(f"Barcode detected: {scanned_edit}")
            st.rerun()

    c1, c2 = st.columns(2)

    with c1:
        edit_price = st.number_input(
            "Selling Price",
            min_value=0.0,
            value=float(row.SellingPrice or 0),
            step=0.01,
            key=f"edit_price_{product_id}",
        )

    with c2:
        edit_gst = st.number_input(
            "GST %",
            min_value=0.0,
            max_value=100.0,
            value=float(row.GSTPercent or 0),
            step=0.5,
            key=f"edit_gst_{product_id}",
        )

    st.caption(
        "Purchase price and expiry date are set per batch — "
        "add new stock from **📦 Stock Adjustment** to record a "
        "fresh batch with its own cost and expiry."
    )

    if st.button(
        "💾 Update Product",
        type="primary",
        use_container_width=True,
        key=f"update_btn_{product_id}",
    ):
        if not edit_name.strip():
            st.error("Product name is required.")
        else:
            try:
                update_product(
                    product_id,
                    edit_name,
                    edit_barcode,
                    edit_price,
                    edit_gst,
                )

                st.success("Product updated successfully.")
                st.rerun()

            except Exception as e:
                st.error("Could not update product.")
                log_exception(e)
                st.exception(e)


# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3 = st.tabs(
    [
        "📋 Product List",
        "➕ Add Product",
        "📦 Stock Adjustment",
    ]
)


# =========================================================
# PRODUCT LIST / EDIT
# =========================================================
with tab1:

    search = st.text_input(
        "🔍 Search Product / Barcode",
        placeholder="Type product name or barcode...",
        key="product_search_input",
    )

    # Start from page 1 when the search text changes.
    if st.session_state.get("_last_product_search") != search:
        st.session_state._last_product_search = search
        st.session_state.product_page = 1

    try:
        products = load_products(search)

        if products.empty:
            st.info("No products found.")

        else:
            st.markdown('<div class="stats-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Total Products",
                len(products),
            )

            c2.metric(
                "Total Stock",
                f"{products['Stock'].sum():,.2f}",
            )

            low_stock = int(
                (products["Stock"] <= 10).sum()
            )

            c3.metric(
                "Low Stock",
                low_stock,
            )
            st.markdown("</div>", unsafe_allow_html=True)

            # -------------------------------------------------
            # TOTAL PRODUCT VALUE
            # -------------------------------------------------
            purchase_value = (
                products["Stock"].fillna(0).astype(float)
                * products["PurchasePrice"].fillna(0).astype(float)
            ).sum()

            selling_value = (
                products["Stock"].fillna(0).astype(float)
                * products["SellingPrice"].fillna(0).astype(float)
            ).sum()

            potential_margin = selling_value - purchase_value

            st.markdown("### 💰 Total Product Value")

            value_col1, value_col2, value_col3 = st.columns(3)

            value_col1.metric(
                "Purchase Value",
                f"₹{purchase_value:,.2f}",
                help="Current stock quantity × purchase price.",
            )

            value_col2.metric(
                "Selling Value",
                f"₹{selling_value:,.2f}",
                help="Current stock quantity × selling price.",
            )

            value_col3.metric(
                "Potential Margin",
                f"₹{potential_margin:,.2f}",
                help="Selling value minus purchase value.",
            )

            st.divider()

            st.caption("📋 Product List")
            st.caption("Click ✏️ on a row to edit that product.")

            # ---------------------------------------------
            # PRODUCT LIST PAGINATION
            # ---------------------------------------------
            total_products = len(products)

            page_size_col, page_info_col = st.columns([1, 3])

            with page_size_col:
                page_size = st.selectbox(
                    "Products per page",
                    [10, 20, 30, 50],
                    index=[10, 20, 30, 50].index(
                        st.session_state.product_page_size
                    ),
                    key="product_page_size_select",
                )

                if page_size != st.session_state.product_page_size:
                    st.session_state.product_page_size = page_size
                    st.session_state.product_page = 1
                    st.rerun()

            page_size = st.session_state.product_page_size
            total_pages = max(
                1,
                (total_products + page_size - 1) // page_size,
            )

            if st.session_state.product_page > total_pages:
                st.session_state.product_page = total_pages

            current_page = st.session_state.product_page

            first_index = (current_page - 1) * page_size
            last_index = first_index + page_size
            page_products = products.iloc[first_index:last_index]

            with page_info_col:
                first_record = first_index + 1
                last_record = min(last_index, total_products)

                st.markdown(
                    f"""
                    <div style="
                        text-align:right;
                        padding-top:28px;
                        color:#64748b;
                        font-size:14px;
                    ">
                        Showing <b>{first_record}-{last_record}</b>
                        of <b>{total_products}</b> products
                        &nbsp; • &nbsp;
                        Page <b>{current_page}</b> of <b>{total_pages}</b>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div class="product-table">',
                unsafe_allow_html=True,
            )

            header = st.columns(
                [3, 1.6, 1.1, 1.1, 0.9, 0.8, 0.6]
            )

            for col, label in zip(
                header,
                [
                    "Product",
                    "Barcode",
                    "Price",
                    "Purchase",
                    "Stock",
                    "GST",
                    "",
                ],
            ):
                col.markdown(
                    f'<span class="th-label">{label}</span>',
                    unsafe_allow_html=True,
                )

            for row in page_products.itertuples():
                r1, r2, r3, r4, r5, r6, r7 = st.columns(
                    [3, 1.6, 1.1, 1.1, 0.9, 0.8, 0.6]
                )

                r1.markdown(
                    f'<span class="cell-name">{row.ProductName}</span>',
                    unsafe_allow_html=True,
                )

                barcode_text = (
                    "—"
                    if pd.isna(row.Barcode)
                    or not str(row.Barcode).strip()
                    else str(row.Barcode)
                )

                r2.markdown(
                    f'<span class="cell-barcode">{barcode_text}</span>',
                    unsafe_allow_html=True,
                )

                r3.markdown(
                    f'<span class="cell-num">₹{float(row.SellingPrice or 0):,.2f}</span>',
                    unsafe_allow_html=True,
                )

                r4.markdown(
                    f'<span class="cell-num">₹{float(row.PurchasePrice or 0):,.2f}</span>',
                    unsafe_allow_html=True,
                )

                stock_value = float(row.Stock)

                badge = (
                    '<span class="stock-badge low">Low</span>'
                    if stock_value <= 10
                    else ""
                )

                r5.markdown(
                    f'<span class="cell-num">{stock_value:g}{badge}</span>',
                    unsafe_allow_html=True,
                )

                r6.markdown(
                    f'<span class="cell-num">{float(row.GSTPercent or 0):g}%</span>',
                    unsafe_allow_html=True,
                )

                if r7.button(
                    "✏️",
                    key=f"edit_icon_{row.ProductID}",
                    help="Edit product",
                ):
                    edit_product_dialog(row)

            st.markdown("</div>", unsafe_allow_html=True)

            # ---------------------------------------------
            # PAGINATION CONTROLS
            # ---------------------------------------------
            st.write("")

            nav1, nav2, nav3, nav4, nav5 = st.columns(
                [1, 1, 3, 1, 1]
            )

            with nav1:
                if st.button(
                    "⏮ First",
                    disabled=current_page <= 1,
                    use_container_width=True,
                    key="product_first",
                ):
                    st.session_state.product_page = 1
                    st.rerun()

            with nav2:
                if st.button(
                    "◀ Previous",
                    disabled=current_page <= 1,
                    use_container_width=True,
                    key="product_previous",
                ):
                    st.session_state.product_page = current_page - 1
                    st.rerun()

            with nav3:
                selected_page = st.selectbox(
                    "Page",
                    range(1, total_pages + 1),
                    index=current_page - 1,
                    label_visibility="collapsed",
                    key="product_page_select",
                )

                if selected_page != current_page:
                    st.session_state.product_page = selected_page
                    st.rerun()

            with nav4:
                if st.button(
                    "Next ▶",
                    disabled=current_page >= total_pages,
                    use_container_width=True,
                    key="product_next",
                ):
                    st.session_state.product_page = current_page + 1
                    st.rerun()

            with nav5:
                if st.button(
                    "Last ⏭",
                    disabled=current_page >= total_pages,
                    use_container_width=True,
                    key="product_last",
                ):
                    st.session_state.product_page = total_pages
                    st.rerun()

    except Exception as e:
        st.error("Unable to load products.")
        log_exception(e)
        st.exception(e)


# =========================================================
# ADD PRODUCT
# =========================================================
with tab2:

    st.caption("➕ Add New Product")

    # ---------------------------------------------
    # Barcode scanner
    # ---------------------------------------------
    st.markdown("### 📷 Barcode")

    scan_col1, scan_col2 = st.columns([1, 3])

    with scan_col1:
        scan_new = st.checkbox(
            "Open Camera Scanner",
            key="scan_new_barcode",
        )

    with scan_col2:
        st.caption(
            "Use the laptop webcam or the camera of the phone/tablet "
            "that is opening this Streamlit page."
        )

    if scan_new:
        scanned_barcode = scan_barcode_from_camera(
            "new_product_barcode_camera"
        )

        if scanned_barcode:
            st.session_state.new_barcode = scanned_barcode
            st.success(
                f"✅ Barcode detected: {scanned_barcode}"
            )

    barcode = st.text_input(
        "Barcode",
        value=st.session_state.new_barcode,
        key="new_barcode_input",
        placeholder="Scan with camera or enter barcode manually",
    )

    # Keep session state synchronized with manual entry.
    st.session_state.new_barcode = barcode

    if barcode.strip():
        st.info(f"Barcode ready: **{barcode.strip()}**")

    st.divider()

    name = st.text_input(
        "Product Name *",
        placeholder="Example: Rice 25kg",
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        price = st.number_input(
            "Selling Price *",
            min_value=0.0,
            value=0.0,
            step=0.01,
        )

    with c2:
        purchase_price = st.number_input(
            "Purchase Price *",
            min_value=0.0,
            value=0.0,
            step=0.01,
            help="Cost price for this opening batch.",
        )

    with c3:
        stock = st.number_input(
            "Opening Stock",
            min_value=0.0,
            value=0.0,
            step=1.0,
        )

    with c4:
        gst = st.number_input(
            "GST %",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.5,
        )

    st.markdown("### 📅 Expiry Date (Batch 1)")

    exp_col1, exp_col2 = st.columns([1, 2])

    with exp_col1:
        no_expiry = st.checkbox(
            "No expiry / long shelf life",
            key="new_product_no_expiry",
        )

    with exp_col2:
        if no_expiry:
            expiry_date = date(2099, 12, 31)
            st.caption("This batch will be treated as non-expiring.")
        else:
            expiry_date = st.date_input(
                "Expiry Date",
                min_value=date.today(),
                value=date.today() + timedelta(days=365),
                key="new_product_expiry",
            )

    st.caption(
        "This opening quantity is saved as **Batch 1** for the product, "
        "so billing can sell against it (First Expiry, First Out) right away."
    )

    if st.button(
        "➕ SAVE PRODUCT",
        type="primary",
        use_container_width=True,
    ):
        if not name.strip():
            st.error("Product name is required.")

        elif price <= 0:
            st.error("Selling price must be greater than zero.")

        elif purchase_price <= 0:
            st.error("Purchase price must be greater than zero.")

        elif stock > 0 and not no_expiry and expiry_date < date.today():
            st.error("Expiry date cannot be in the past.")

        else:
            try:
                new_id = add_product(
                    name,
                    barcode,
                    price,
                    purchase_price,
                    stock,
                    gst,
                    expiry_date,
                )

                st.success(
                    f"Product '{name}' added successfully (ID {new_id})."
                )

                # Clear the form after a successful save.
                st.session_state.new_barcode = ""

            except Exception as e:
                st.error("Could not add product.")
                log_exception(e)
                st.exception(e)


# =========================================================
# STOCK ADJUSTMENT
# =========================================================
with tab3:

    st.caption("📦 Stock Adjustment")
    st.caption(
        "Select the product and exact batch before changing stock. "
        "Both batch quantity and total product stock are updated."
    )

    try:
        stock_products = load_products("")

        if stock_products.empty:
            st.info("No products available.")
        else:
            product_options = {
                f"{row.ProductName} | Current stock: {float(row.Stock):g}":
                int(row.ProductID)
                for row in stock_products.itertuples()
            }

            selected_label = st.selectbox(
                "1. Select Product",
                list(product_options.keys()),
                key="stock_product",
            )

            selected_id = product_options[selected_label]

            selected = stock_products[
                stock_products["ProductID"] == selected_id
            ].iloc[0]

            st.metric(
                "Current Total Product Stock",
                f"{float(selected['Stock']):,.2f}",
            )

            batches = load_product_batches(selected_id)

            if batches.empty:
                st.warning(
                    "No active batch exists for this product. "
                    "Please add stock through Batch Stock In first."
                )
            else:
                st.markdown("### 2. Select Batch")

                batch_options = {}
                for batch in batches.itertuples():
                    expiry = (
                        pd.to_datetime(batch.ExpiryDate).strftime("%d-%m-%Y")
                        if pd.notna(batch.ExpiryDate)
                        else "No expiry"
                    )

                    label = (
                        f"Batch: {batch.BatchNo} | "
                        f"Qty: {float(batch.Quantity):g} | "
                        f"Expiry: {expiry}"
                    )
                    batch_options[label] = int(batch.BatchID)

                selected_batch_label = st.selectbox(
                    "Batch",
                    list(batch_options.keys()),
                    key="stock_batch",
                )

                selected_batch_id = batch_options[selected_batch_label]

                selected_batch = batches[
                    batches["BatchID"] == selected_batch_id
                ].iloc[0]

                b1, b2, b3, b4 = st.columns(4)

                b1.metric(
                    "Batch No.",
                    str(selected_batch["BatchNo"]),
                )
                b2.metric(
                    "Batch Quantity",
                    f"{float(selected_batch['Quantity']):,.2f}",
                )

                expiry_text = (
                    pd.to_datetime(
                        selected_batch["ExpiryDate"]
                    ).strftime("%d-%m-%Y")
                    if pd.notna(selected_batch["ExpiryDate"])
                    else "No expiry"
                )
                b3.metric("Expiry", expiry_text)
                b4.metric(
                    "Purchase Price",
                    f"₹{float(selected_batch['PurchasePrice'] or 0):,.2f}",
                )

                st.divider()
                st.markdown("### 3. Stock Movement")

                adjustment_type = st.radio(
                    "Adjustment",
                    ["Add Stock", "Reduce Stock"],
                    horizontal=True,
                    key="batch_adjustment_type",
                )

                quantity = st.number_input(
                    "Quantity",
                    min_value=0.01,
                    value=1.0,
                    step=1.0,
                    key="batch_stock_quantity",
                )

                reason = st.text_input(
                    "Reason",
                    placeholder=(
                        "Example: New purchase / damaged stock / "
                        "physical count correction"
                    ),
                    key="batch_stock_reason",
                )

                current_qty = float(selected_batch["Quantity"] or 0)

                if adjustment_type == "Add Stock":
                    after_qty = current_qty + float(quantity)
                else:
                    after_qty = current_qty - float(quantity)

                p1, p2 = st.columns(2)
                p1.metric("Batch Before", f"{current_qty:,.2f}")
                p2.metric("Batch After", f"{after_qty:,.2f}")

                if (
                    adjustment_type == "Reduce Stock"
                    and quantity > current_qty
                ):
                    st.error(
                        f"Cannot reduce {quantity:g}. "
                        f"Selected batch has only {current_qty:g}."
                    )

                if st.button(
                    "💾 UPDATE SELECTED BATCH",
                    type="primary",
                    use_container_width=True,
                    key="update_batch_stock",
                ):
                    if adjustment_type == "Reduce Stock" and quantity > current_qty:
                        st.error(
                            "Reduce quantity cannot be greater than "
                            "the selected batch quantity."
                        )
                    else:
                        change = (
                            float(quantity)
                            if adjustment_type == "Add Stock"
                            else -float(quantity)
                        )

                        try:
                            result = adjust_batch_stock(
                                selected_batch_id,
                                change,
                            )

                            st.success(
                                f"Batch {result['BatchNo']} updated: "
                                f"{result['OldQuantity']:g} → "
                                f"{result['NewQuantity']:g}"
                            )

                            if reason.strip():
                                st.caption(f"Reason: {reason}")

                            st.rerun()

                        except Exception as e:
                            st.error("Could not update batch stock.")
                            log_exception(e)
                            st.exception(e)

    except Exception as e:
        st.error("Unable to load stock adjustment data.")
        log_exception(e)
        st.exception(e)


# =========================================================
# INSTALLATION NOTE
# =========================================================
if not BARCODE_SCANNER_AVAILABLE:
    st.sidebar.warning(
        "📷 Camera barcode scanner is not installed.\n\n"
        "Run:\n"
        "pip install pyzbar pillow"
    )