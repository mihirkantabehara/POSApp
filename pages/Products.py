import streamlit as st

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

st.title("")

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

.block-container{
  max-width:1600px;
  padding-top:1.25rem;
  padding-bottom:1.5rem;
}

div[data-testid="stVerticalBlock"]{
  gap:.65rem;
}

.stTabs [data-baseweb="tab-list"]{
  gap:6px;
  border-bottom:1px solid var(--pos-line);
}

.stTabs [data-baseweb="tab"]{
  height:42px;
  padding:0 14px;
  font-weight:600;
}

div[data-testid="stMetric"]{
  border:1px solid var(--pos-line);
  border-radius:10px;
  padding:10px 12px;
  background:var(--pos-surface);
}

div[data-testid="stMetricLabel"]{
  color:var(--pos-muted);
  font-size:.78rem;
}

div[data-testid="stMetricValue"]{
  color:var(--pos-ink);
  font-size:1.2rem;
}

/* metrics strip */
.stats-card{
  background:var(--pos-surface);border:1px solid var(--pos-line);
  border-radius:12px;padding:10px 12px 4px 12px;margin-bottom:4px;
}



/* product table */

.product-table{

  border:1px solid var(--pos-line);border-radius:12px;

  overflow:hidden;background:var(--pos-surface);margin-top:6px;

}

.product-table div[data-testid="stHorizontalBlock"]{
  padding:6px 12px;border-bottom:1px solid var(--pos-line);
  align-items:center;
}
.product-table div[data-testid="stHorizontalBlock"]:first-of-type{
  background:#f8fafc;border-bottom:2px solid var(--pos-ink);
  padding-top:8px;padding-bottom:8px;

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
  padding:2px 8px;font-size:.9rem;border-radius:7px;min-height:0;
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


def load_lookup_data():
    """Load active product lookup values used by the Product master."""

    with engine.connect() as connection:

        categories = pd.read_sql(
            text("""

                SELECT "CategoryID", "CategoryName"

                FROM "ProductCategories"

                WHERE "IsActive" = TRUE

                ORDER BY "CategoryName"

            """),
            connection,
        )

        brands = pd.read_sql(
            text("""

                SELECT "BrandID", "BrandName"

                FROM "ProductBrands"

                WHERE "IsActive" = TRUE

                ORDER BY "BrandName"

            """),
            connection,
        )

        units = pd.read_sql(
            text("""

                SELECT "UnitID", "UnitName"

                FROM "ProductUnits"

                WHERE "IsActive" = TRUE

                ORDER BY "UnitName"

            """),
            connection,
        )

    return categories, brands, units


def load_subcategories(category_id=None):

    sql = """

        SELECT "SubcategoryID", "SubcategoryName", "CategoryID"

        FROM "ProductSubcategories"

        WHERE "IsActive" = TRUE

    """

    params = {}

    if category_id is not None:

        sql += ' AND "CategoryID" = :category_id'

        params["category_id"] = int(category_id)

    sql += ' ORDER BY "SubcategoryName"'

    with engine.connect() as connection:

        return pd.read_sql(text(sql), connection, params=params)


def load_products(search=""):

    query = """

        SELECT

            p."ProductID",

            p."ProductName",

            p."Barcode",

            p."CategoryID",

            c."CategoryName",

            p."SubcategoryID",

            sc."SubcategoryName",

            p."BrandID",

            b."BrandName",

            p."UnitID",

            u."UnitName",

            p."PackSize",

            p."MRP",

            p."Stock",

            p."GSTPercent",

            p."Description"

        FROM "Products" p

        LEFT JOIN "ProductCategories" c

            ON c."CategoryID" = p."CategoryID"

        LEFT JOIN "ProductSubcategories" sc

            ON sc."SubcategoryID" = p."SubcategoryID"

        LEFT JOIN "ProductBrands" b

            ON b."BrandID" = p."BrandID"

        LEFT JOIN "ProductUnits" u

            ON u."UnitID" = p."UnitID"

    """

    params = {}

    if search.strip():

        query += """

            WHERE p."ProductName" ILIKE :search

               OR p."Barcode" ILIKE :search

               OR c."CategoryName" ILIKE :search

               OR sc."SubcategoryName" ILIKE :search

               OR b."BrandName" ILIKE :search

               OR u."UnitName" ILIKE :search

        """

        params["search"] = f"%{search.strip()}%"

    query += ' ORDER BY p."ProductName"'

    with engine.connect() as connection:

        result = connection.execute(text(query), params)

        return pd.DataFrame(result.fetchall(), columns=result.keys())


def add_product(
    name,
    barcode,
    category_id,
    subcategory_id,
    brand_id,
    unit_id,
    pack_size,
    mrp,
    gst,
    description,
):
    """Create only the Product master. "Stock"/prices stay at batch level."""

    with engine.begin() as connection:

        if barcode.strip():

            existing = connection.execute(
                text("""

                    SELECT "ProductID"

                    FROM "Products"

                    WHERE "Barcode" = :barcode

                """),
                {"barcode": barcode.strip()},
            ).first()

            if existing:

                raise ValueError(
                    f"Barcode {barcode.strip()} already exists "
                    f"for Product ID {existing[0]}."
                )

        lookup = (
            connection.execute(
                text("""

                SELECT

                    c."CategoryName",

                    sc."SubcategoryName",

                    b."BrandName",

                    u."UnitName"

                FROM (SELECT 1 AS Dummy) x

                LEFT JOIN "ProductCategories" c

                    ON c."CategoryID" = :category_id

                LEFT JOIN "ProductSubcategories" sc

                    ON sc."SubcategoryID" = :subcategory_id

                LEFT JOIN "ProductBrands" b

                    ON b."BrandID" = :brand_id

                LEFT JOIN "ProductUnits" u

                    ON u."UnitID" = :unit_id

            """),
                {
                    "category_id": category_id,
                    "subcategory_id": subcategory_id,
                    "brand_id": brand_id,
                    "unit_id": unit_id,
                },
            )
            .mappings()
            .first()
        )

        product_id = connection.execute(
            text("""

                INSERT INTO "Products"

                (

                    "ProductName",

                    "Barcode",

                    "CategoryID",

                    "SubcategoryID",

                    "BrandID",

                    "UnitID",

                    "Category",

                    "Subcategory",

                    "Brand",

                    "Unit",

                    "PackSize",

                    "MRP",

                    "GSTPercent",

                    "Description",

                    "SellingPrice",

                    "PurchasePrice",

                    "Stock"

                )

                RETURNING "ProductID"

                VALUES

                (

                    :name,

                    :barcode,

                    :category_id,

                    :subcategory_id,

                    :brand_id,

                    :unit_id,

                    :category,

                    :subcategory,

                    :brand,

                    :unit,

                    :pack_size,

                    :mrp,

                    :gst,

                    :description,

                    0,

                    0,

                    0

                )

            """),
            {
                "name": name.strip(),
                "barcode": barcode.strip() or None,
                "category_id": category_id,
                "subcategory_id": subcategory_id,
                "brand_id": brand_id,
                "unit_id": unit_id,
                "category": lookup["CategoryName"] if lookup else None,
                "subcategory": lookup["SubcategoryName"] if lookup else None,
                "brand": lookup["BrandName"] if lookup else None,
                "unit": lookup["UnitName"] if lookup else None,
                "pack_size": pack_size.strip() or None,
                "mrp": float(mrp),
                "gst": float(gst),
                "description": description.strip() or None,
            },
        ).scalar()

        return product_id


def update_product(
    product_id,
    name,
    barcode,
    category_id,
    subcategory_id,
    brand_id,
    unit_id,
    pack_size,
    mrp,
    gst,
    description,
):

    with engine.begin() as connection:

        if barcode.strip():

            existing = connection.execute(
                text("""

                    SELECT "ProductID"

                    FROM "Products"

                    WHERE "Barcode" = :barcode

                      AND "ProductID" <> :product_id

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

        lookup = (
            connection.execute(
                text("""

                SELECT

                    c."CategoryName",

                    sc."SubcategoryName",

                    b."BrandName",

                    u."UnitName"

                FROM (SELECT 1 AS Dummy) x

                LEFT JOIN "ProductCategories" c

                    ON c."CategoryID" = :category_id

                LEFT JOIN "ProductSubcategories" sc

                    ON sc."SubcategoryID" = :subcategory_id

                LEFT JOIN "ProductBrands" b

                    ON b."BrandID" = :brand_id

                LEFT JOIN "ProductUnits" u

                    ON u."UnitID" = :unit_id

            """),
                {
                    "category_id": category_id,
                    "subcategory_id": subcategory_id,
                    "brand_id": brand_id,
                    "unit_id": unit_id,
                },
            )
            .mappings()
            .first()
        )

        connection.execute(
            text("""

                UPDATE "Products"

                SET

                    "ProductName" = :name,

                    "Barcode" = :barcode,

                    "CategoryID" = :category_id,

                    "SubcategoryID" = :subcategory_id,

                    "BrandID" = :brand_id,

                    "UnitID" = :unit_id,

                    "Category" = :category,

                    "Subcategory" = :subcategory,

                    "Brand" = :brand,

                    "Unit" = :unit,

                    "PackSize" = :pack_size,

                    "MRP" = :mrp,

                    "GSTPercent" = :gst,

                    "Description" = :description

                WHERE "ProductID" = :product_id

            """),
            {
                "product_id": int(product_id),
                "name": name.strip(),
                "barcode": barcode.strip() or None,
                "category_id": category_id,
                "subcategory_id": subcategory_id,
                "brand_id": brand_id,
                "unit_id": unit_id,
                "category": lookup["CategoryName"] if lookup else None,
                "subcategory": lookup["SubcategoryName"] if lookup else None,
                "brand": lookup["BrandName"] if lookup else None,
                "unit": lookup["UnitName"] if lookup else None,
                "pack_size": pack_size.strip() or None,
                "mrp": float(mrp),
                "gst": float(gst),
                "description": description.strip() or None,
            },
        )


def add_lookup_value(table_name, name, category_id=None):
    """Add a value to one of the controlled lookup tables."""

    allowed = {
        "category": "ProductCategories",
        "subcategory": "ProductSubcategories",
        "brand": "ProductBrands",
        "unit": "ProductUnits",
    }

    table = allowed.get(table_name)

    if not table:

        raise ValueError("Invalid lookup type.")

    clean_name = name.strip()

    if not clean_name:

        raise ValueError("Name cannot be empty.")

    with engine.begin() as connection:

        if table_name == "category":

            connection.execute(
                text("""

                    INSERT INTO "ProductCategories" ("CategoryName")

                    VALUES (:name)

                """),
                {"name": clean_name},
            )

        elif table_name == "subcategory":

            if category_id is None:

                raise ValueError("Select a category for the subcategory.")

            connection.execute(
                text("""

                    INSERT INTO "ProductSubcategories"

                    ("CategoryID", "SubcategoryName")

                    VALUES (:category_id, :name)

                """),
                {"category_id": int(category_id), "name": clean_name},
            )

        elif table_name == "brand":

            connection.execute(
                text("""

                    INSERT INTO "ProductBrands" ("BrandName")

                    VALUES (:name)

                """),
                {"name": clean_name},
            )

        else:

            connection.execute(
                text("""

                    INSERT INTO "ProductUnits" ("UnitName")

                    VALUES (:name)

                """),
                {"name": clean_name},
            )


def load_product_batches(product_id):

    query = text("""

        SELECT

            "BatchID",

            "BatchNo",

            "ManufacturingDate",

            "ExpiryDate",

            "PurchasePrice",

            "SellingPrice",

            "GSTPercent",

            "Quantity",

            "IsActive"

        FROM "ProductBatches"

        WHERE "ProductID" = :product_id

          AND "IsActive" = TRUE

        ORDER BY "ExpiryDate" ASC, "BatchID" ASC

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

        batch = (
            connection.execute(
                text("""

                SELECT

                    "BatchID",

                    "ProductID",

                    "BatchNo",

                    "Quantity"

                FROM "ProductBatches"

                WHERE "BatchID" = :batch_id

                  AND "IsActive" = TRUE

                FOR UPDATE

            """),
                {"batch_id": int(batch_id)},
            )
            .mappings()
            .first()
        )

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

                UPDATE "ProductBatches"

                SET "Quantity" = "Quantity" + :change

                WHERE "BatchID" = :batch_id

                  AND "IsActive" = TRUE

                  AND "Quantity" + :change >= 0

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

                UPDATE "Products"

                SET "Stock" = "Stock" + :change

                WHERE "ProductID" = :product_id

                  AND "Stock" + :change >= 0

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

        barcode_value = (
            results[0]
            .data.decode(
                "utf-8",
                errors="ignore",
            )
            .strip()
        )

        if not barcode_value:

            st.warning("Barcode was detected but contains no readable value.")

            return None

        return barcode_value

    except Exception as exc:

        st.error(f"Could not read the barcode image: {exc}")

        return None


@st.dialog("✏️ Edit Product", width="large")
def edit_product_dialog(row):

    product_id = int(row.ProductID)

    categories, brands, units = load_lookup_data()

    current_category_id = None if pd.isna(row.CategoryID) else int(row.CategoryID)

    subcategories = load_subcategories(current_category_id)

    current_subcategory_id = (
        None if pd.isna(row.SubcategoryID) else int(row.SubcategoryID)
    )

    current_brand_id = None if pd.isna(row.BrandID) else int(row.BrandID)

    current_unit_id = None if pd.isna(row.UnitID) else int(row.UnitID)

    current_barcode = "" if pd.isna(row.Barcode) else str(row.Barcode)

    edit_name = st.text_input(
        "Product Name *",
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

    category_names = ["-- Select Category --"] + categories["CategoryName"].tolist()

    category_index = 0

    if current_category_id is not None:

        matches = categories.index[
            categories["CategoryID"] == current_category_id
        ].tolist()

        if matches:

            category_index = matches[0] + 1

    with c1:

        selected_category = st.selectbox(
            "Category",
            category_names,
            index=category_index,
            key=f"edit_category_{product_id}",
        )

    selected_category_id = None

    if selected_category != "-- Select Category --":

        selected_category_id = int(
            categories.loc[
                categories["CategoryName"] == selected_category,
                "CategoryID",
            ].iloc[0]
        )

    # Reload subcategories for the category selected in this dialog.

    if selected_category_id != current_category_id:

        subcategories = load_subcategories(selected_category_id)

        current_subcategory_id = None

    subcategory_names = ["-- Select Subcategory --"] + subcategories[
        "SubcategoryName"
    ].tolist()

    subcategory_index = 0

    if current_subcategory_id is not None:

        matches = subcategories.index[
            subcategories["SubcategoryID"] == current_subcategory_id
        ].tolist()

        if matches:

            subcategory_index = matches[0] + 1

    with c2:

        selected_subcategory = st.selectbox(
            "Subcategory",
            subcategory_names,
            index=subcategory_index,
            key=f"edit_subcategory_{product_id}",
        )

    selected_subcategory_id = None

    if selected_subcategory != "-- Select Subcategory --":

        selected_subcategory_id = int(
            subcategories.loc[
                subcategories["SubcategoryName"] == selected_subcategory,
                "SubcategoryID",
            ].iloc[0]
        )

    c1, c2 = st.columns(2)

    brand_names = ["-- Select Brand --"] + brands["BrandName"].tolist()

    brand_index = 0

    if current_brand_id is not None:

        matches = brands.index[brands["BrandID"] == current_brand_id].tolist()

        if matches:

            brand_index = matches[0] + 1

    with c1:

        selected_brand = st.selectbox(
            "Brand",
            brand_names,
            index=brand_index,
            key=f"edit_brand_{product_id}",
        )

    selected_brand_id = None

    if selected_brand != "-- Select Brand --":

        selected_brand_id = int(
            brands.loc[
                brands["BrandName"] == selected_brand,
                "BrandID",
            ].iloc[0]
        )

    unit_names = ["-- Select Unit --"] + units["UnitName"].tolist()

    unit_index = 0

    if current_unit_id is not None:

        matches = units.index[units["UnitID"] == current_unit_id].tolist()

        if matches:

            unit_index = matches[0] + 1

    with c2:

        selected_unit = st.selectbox(
            "Unit",
            unit_names,
            index=unit_index,
            key=f"edit_unit_{product_id}",
        )

    selected_unit_id = None

    if selected_unit != "-- Select Unit --":

        selected_unit_id = int(
            units.loc[
                units["UnitName"] == selected_unit,
                "UnitID",
            ].iloc[0]
        )

    c1, c2 = st.columns(2)

    with c1:

        edit_pack_size = st.text_input(
            "Pack Size",
            value="" if pd.isna(row.PackSize) else str(row.PackSize),
            key=f"edit_pack_size_{product_id}",
            placeholder="1 Kg / 500 ml",
        )

    with c2:

        edit_mrp = st.number_input(
            "MRP",
            min_value=0.0,
            value=0.0 if pd.isna(row.MRP) else float(row.MRP),
            step=0.01,
            key=f"edit_mrp_{product_id}",
        )

    edit_gst = st.number_input(
        "GST %",
        min_value=0.0,
        max_value=100.0,
        value=0.0 if pd.isna(row.GSTPercent) else float(row.GSTPercent),
        step=0.5,
        key=f"edit_gst_{product_id}",
    )

    edit_description = st.text_area(
        "Description",
        value="" if pd.isna(row.Description) else str(row.Description),
        key=f"edit_description_{product_id}",
    )

    st.caption(
        "Purchase price, selling price, quantity and expiry are maintained "
        "at batch level through Purchase Stock and Admin Approval."
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
                    selected_category_id,
                    selected_subcategory_id,
                    selected_brand_id,
                    selected_unit_id,
                    edit_pack_size,
                    edit_mrp,
                    edit_gst,
                    edit_description,
                )

                st.success("Product updated successfully.")

                st.rerun()

            except Exception as e:

                st.error("Could not update product.")

                st.exception(e)


# =========================================================

# TABS

# =========================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📋 Product List",
        "➕ Add Product",
        "📦 Stock Adjustment",
        "⚙️ Master Data",
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

            # Total current inventory value based on active batch

            # selling prices. This does not change any existing

            # product, search, edit, batch, or stock functionality.

            inventory_value_query = text("""

                SELECT

                    COALESCE(

                        SUM(

                            CAST("Quantity" AS DECIMAL(18,3))

                            * CAST("SellingPrice" AS DECIMAL(18,2))

                        ),

                        0

                    ) AS "TotalInventoryValue"

                FROM "ProductBatches"

                WHERE "IsActive" = TRUE

                  AND "Quantity" > 0

            """)

            try:

                with engine.connect() as connection:

                    total_inventory_value = (
                        connection.execute(inventory_value_query).scalar() or 0
                    )

            except Exception as e:

                log_exception(e)

                total_inventory_value = 0

            total_inventory_value = float(total_inventory_value)

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Total Products",
                len(products),
                border=True,
            )

            c2.metric(
                "Total Stock",
                f"{products['Stock'].sum():,.2f}",
                border=True,
            )

            low_stock = int((products["Stock"] <= 10).sum())

            c3.metric(
                "Low Stock",
                low_stock,
                border=True,
            )

            c4.metric(
                "Total Inventory Value",
                f"₹{total_inventory_value:,.2f}",
                border=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)

            st.divider()

            st.subheader("📋 Product List")

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
                    index=[10, 20, 30, 50].index(st.session_state.product_page_size),
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
                        text-align: right;
                        padding-top: 28px;
                        color: #64748b;
                        font-size: 14px;
                    ">
                        Showing <b>{first_record}-{last_record}</b>
                        of <b>{total_products}</b> products
                        &nbsp;&nbsp;•&nbsp;&nbsp;
                        Page <b>{current_page}</b> of <b>{total_pages}</b>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div class="product-table">',
                unsafe_allow_html=True,
            )

            header = st.columns([2.5, 1.35, 1.2, 1.2, 0.9, 0.95, 0.8, 0.65, 0.55])

            for col, label in zip(
                header,
                [
                    "Product",
                    "Barcode",
                    "Category",
                    "Brand",
                    "Unit",
                    "MRP",
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

                r1, r2, r3, r4, r5, r6, r7, r8, r9 = st.columns(
                    [2.5, 1.35, 1.2, 1.2, 0.9, 0.95, 0.8, 0.65, 0.55]
                )

                r1.markdown(
                    f'<span class="cell-name">{row.ProductName}</span>',
                    unsafe_allow_html=True,
                )

                barcode_text = (
                    "—"
                    if pd.isna(row.Barcode) or not str(row.Barcode).strip()
                    else str(row.Barcode)
                )

                r2.markdown(
                    f'<span class="cell-barcode">{barcode_text}</span>',
                    unsafe_allow_html=True,
                )

                category_text = (
                    "—" if pd.isna(row.CategoryName) else str(row.CategoryName)
                )

                r3.markdown(
                    f'<span class="cell-name">{category_text}</span>',
                    unsafe_allow_html=True,
                )

                brand_text = "—" if pd.isna(row.BrandName) else str(row.BrandName)

                r4.markdown(
                    f'<span class="cell-name">{brand_text}</span>',
                    unsafe_allow_html=True,
                )

                unit_text = "—" if pd.isna(row.UnitName) else str(row.UnitName)

                r5.markdown(
                    f'<span class="cell-name">{unit_text}</span>',
                    unsafe_allow_html=True,
                )

                mrp_value = 0 if pd.isna(row.MRP) else float(row.MRP)

                r6.markdown(
                    f'<span class="cell-num">₹{mrp_value:,.2f}</span>',
                    unsafe_allow_html=True,
                )

                stock_value = 0 if pd.isna(row.Stock) else float(row.Stock)

                badge = (
                    '<span class="stock-badge low">Low</span>'
                    if stock_value <= 10
                    else ""
                )

                r7.markdown(
                    f'<span class="cell-num">{stock_value:g}{badge}</span>',
                    unsafe_allow_html=True,
                )

                gst_value = 0 if pd.isna(row.GSTPercent) else float(row.GSTPercent)

                r8.markdown(
                    f'<span class="cell-num">{gst_value:g}%</span>',
                    unsafe_allow_html=True,
                )

                if r9.button(
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

            nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 3, 1, 1])

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

        st.exception(e)

# =========================================================

# ADD PRODUCT

# =========================================================

with tab2:

    st.subheader("➕ Add New Product")

    st.caption(
        "Create the product master only. Category, subcategory, brand and unit "
        "are controlled lookup values. Stock, purchase price, selling price "
        "and expiry are added later through Purchase Stock and approved by Admin."
    )

    try:

        categories, brands, units = load_lookup_data()

    except Exception as e:

        st.error(
            "Unable to load product lookup values. Run the lookup migration SQL first."
        )

        st.exception(e)

        st.stop()

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

        scanned_barcode = scan_barcode_from_camera("new_product_barcode_camera")

        if scanned_barcode:

            st.session_state.new_barcode = scanned_barcode

            st.success(f"✅ Barcode detected: {scanned_barcode}")

    barcode = st.text_input(
        "Barcode",
        value=st.session_state.new_barcode,
        key="new_barcode_input",
        placeholder="Scan with camera or enter barcode manually",
    )

    st.session_state.new_barcode = barcode

    st.divider()

    name = st.text_input(
        "Product Name *",
        placeholder="Example: Rice 25kg",
    )

    # -----------------------------------------------------

    # LOOKUP FIELDS

    # -----------------------------------------------------

    c1, c2 = st.columns(2)

    category_names = ["-- Select Category --"] + categories["CategoryName"].tolist()

    with c1:

        selected_category = st.selectbox(
            "Category",
            category_names,
            key="new_product_category",
        )

    selected_category_id = None

    if selected_category != "-- Select Category --":

        selected_category_id = int(
            categories.loc[
                categories["CategoryName"] == selected_category,
                "CategoryID",
            ].iloc[0]
        )

    subcategories = load_subcategories(selected_category_id)

    subcategory_names = ["-- Select Subcategory --"] + subcategories[
        "SubcategoryName"
    ].tolist()

    with c2:

        selected_subcategory = st.selectbox(
            "Subcategory",
            subcategory_names,
            key="new_product_subcategory",
            disabled=selected_category_id is None,
        )

    selected_subcategory_id = None

    if selected_subcategory != "-- Select Subcategory --":

        selected_subcategory_id = int(
            subcategories.loc[
                subcategories["SubcategoryName"] == selected_subcategory,
                "SubcategoryID",
            ].iloc[0]
        )

    c1, c2 = st.columns(2)

    brand_names = ["-- Select Brand --"] + brands["BrandName"].tolist()

    unit_names = ["-- Select Unit --"] + units["UnitName"].tolist()

    with c1:

        selected_brand = st.selectbox(
            "Brand",
            brand_names,
            key="new_product_brand",
        )

    with c2:

        selected_unit = st.selectbox(
            "Unit",
            unit_names,
            key="new_product_unit",
        )

    selected_brand_id = None

    if selected_brand != "-- Select Brand --":

        selected_brand_id = int(
            brands.loc[
                brands["BrandName"] == selected_brand,
                "BrandID",
            ].iloc[0]
        )

    selected_unit_id = None

    if selected_unit != "-- Select Unit --":

        selected_unit_id = int(
            units.loc[
                units["UnitName"] == selected_unit,
                "UnitID",
            ].iloc[0]
        )

    c1, c2, c3 = st.columns(3)

    with c1:

        pack_size = st.text_input(
            "Pack Size",
            placeholder="1 Kg / 500 ml",
        )

    with c2:

        mrp = st.number_input(
            "MRP",
            min_value=0.0,
            value=0.0,
            step=0.01,
        )

    with c3:

        gst = st.number_input(
            "GST %",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.5,
        )

    description = st.text_area(
        "Description",
        placeholder="Optional product description",
    )

    st.info(
        "📦 Purchase price, selling price, quantity and expiry are batch-level "
        "data and will be entered from Manager → Purchase Stock."
    )

    if st.button(
        "➕ SAVE PRODUCT",
        type="primary",
        use_container_width=True,
    ):

        if not name.strip():

            st.error("Product name is required.")

        else:

            try:

                new_id = add_product(
                    name,
                    barcode,
                    selected_category_id,
                    selected_subcategory_id,
                    selected_brand_id,
                    selected_unit_id,
                    pack_size,
                    mrp,
                    gst,
                    description,
                )

                st.success(f"Product '{name}' added successfully (ID {new_id}).")

                st.session_state.new_barcode = ""

            except Exception as e:

                st.error("Could not add product.")

                st.exception(e)

# =========================================================

# STOCK ADJUSTMENT

# =========================================================

with tab3:

    st.subheader("📦 Stock Adjustment")

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
                f"{row.ProductName} | Current stock: {float(row.Stock):g}": int(
                    row.ProductID
                )
                for row in stock_products.itertuples()
            }

            selected_label = st.selectbox(
                "1. Select Product",
                list(product_options.keys()),
                key="stock_product",
            )

            selected_id = product_options[selected_label]

            selected = stock_products[stock_products["ProductID"] == selected_id].iloc[
                0
            ]

            st.metric(
                "Current Total Product Stock",
                f"{float(selected['Stock']):,.2f}",
                border=True,
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

                selected_batch = batches[batches["BatchID"] == selected_batch_id].iloc[
                    0
                ]

                b1, b2, b3, b4 = st.columns(4)

                b1.metric(
                    "Batch No.",
                    str(selected_batch["BatchNo"]),
                    border=True,
                )
                b2.metric(
                    "Batch Quantity",
                    f"{float(selected_batch['Quantity']):,.2f}",
                    border=True,
                )

                expiry_text = (
                    pd.to_datetime(selected_batch["ExpiryDate"]).strftime("%d-%m-%Y")
                    if pd.notna(selected_batch["ExpiryDate"])
                    else "No expiry"
                )

                b3.metric("Expiry", expiry_text, border=True)
                b4.metric(
                    "Purchase Price",
                    f"₹{float(selected_batch['PurchasePrice'] or 0):,.2f}",
                    border=True,
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

                p1.metric("Batch Before", f"{current_qty:,.2f}", border=True)
                p2.metric("Batch After", f"{after_qty:,.2f}", border=True)

                if adjustment_type == "Reduce Stock" and quantity > current_qty:

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

                            st.exception(e)

    except Exception as e:

        st.error("Unable to load stock adjustment data.")

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

# =========================================================

# MASTER DATA / LOOKUPS

# =========================================================

with tab4:

    st.subheader("⚙️ Product Master Data")

    st.caption(
        "Manage the lookup values used by Category, Subcategory, Brand and Unit."
    )

    try:

        categories, brands, units = load_lookup_data()

    except Exception as e:

        st.error("Unable to load lookup tables. Run the lookup migration SQL first.")

        st.exception(e)

        st.stop()

    m1, m2 = st.columns(2)

    with m1:

        st.markdown("### 📂 Categories")

        new_category = st.text_input(
            "New Category",
            key="master_new_category",
            placeholder="Example: Grocery",
        )

        if st.button(
            "➕ Add Category",
            key="add_category_button",
            use_container_width=True,
        ):

            try:

                add_lookup_value("category", new_category)

                st.success("Category added.")

                st.rerun()

            except Exception as e:

                st.error("Could not add category. It may already exist.")

                st.exception(e)

        st.dataframe(
            categories[["CategoryID", "CategoryName"]],
            use_container_width=True,
            hide_index=True,
        )

    with m2:

        st.markdown("### 🏷️ Brands")

        new_brand = st.text_input(
            "New Brand",
            key="master_new_brand",
            placeholder="Example: Fortune",
        )

        if st.button(
            "➕ Add Brand",
            key="add_brand_button",
            use_container_width=True,
        ):

            try:

                add_lookup_value("brand", new_brand)

                st.success("Brand added.")

                st.rerun()

            except Exception as e:

                st.error("Could not add brand. It may already exist.")

                st.exception(e)

        st.dataframe(
            brands[["BrandID", "BrandName"]],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    m1, m2 = st.columns(2)

    with m1:

        st.markdown("### 📁 Subcategories")

        category_names = ["-- Select Category --"] + categories["CategoryName"].tolist()

        master_category = st.selectbox(
            "Parent Category",
            category_names,
            key="master_subcategory_category",
        )

        master_category_id = None

        if master_category != "-- Select Category --":

            master_category_id = int(
                categories.loc[
                    categories["CategoryName"] == master_category,
                    "CategoryID",
                ].iloc[0]
            )

        new_subcategory = st.text_input(
            "New Subcategory",
            key="master_new_subcategory",
            placeholder="Example: Rice",
        )

        if st.button(
            "➕ Add Subcategory",
            key="add_subcategory_button",
            use_container_width=True,
        ):

            try:

                add_lookup_value(
                    "subcategory",
                    new_subcategory,
                    master_category_id,
                )

                st.success("Subcategory added.")

                st.rerun()

            except Exception as e:

                st.error("Could not add subcategory. It may already exist.")

                st.exception(e)

        subcategory_view = load_subcategories(master_category_id)

        st.dataframe(
            subcategory_view,
            use_container_width=True,
            hide_index=True,
        )

    with m2:

        st.markdown("### 📏 Units")

        new_unit = st.text_input(
            "New Unit",
            key="master_new_unit",
            placeholder="Kg / Litre / Piece",
        )

        if st.button(
            "➕ Add Unit",
            key="add_unit_button",
            use_container_width=True,
        ):

            try:

                add_lookup_value("unit", new_unit)

                st.success("Unit added.")

                st.rerun()

            except Exception as e:

                st.error("Could not add unit. It may already exist.")

                st.exception(e)

        st.dataframe(
            units[["UnitID", "UnitName"]],
            use_container_width=True,
            hide_index=True,
        )
