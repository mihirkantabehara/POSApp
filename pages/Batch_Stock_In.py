import streamlit as st
from logging_config import log_exception
import pandas as pd
from datetime import date
from sqlalchemy import text

from database.database import engine
from auth import require_role


# =========================================================
# ACCESS
# =========================================================

user = require_role("Manager", "Admin")


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Batch Stock In",
    page_icon="📦",
    layout="wide"
)

#st.title("📦 Batch Stock In")
st.caption(
    f"Logged in as: {user['FullName']} • {user['Role']}"
)


# =========================================================
# LOAD PRODUCTS
# =========================================================

@st.cache_data(ttl=30)
def load_products(search=""):

    query = """
        SELECT
            ProductID,
            ProductName,
            Barcode,
            PurchasePrice,
            SellingPrice,
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

    query += """
        ORDER BY ProductName
    """

    with engine.connect() as connection:

        result = connection.execute(
            text(query),
            params
        )

        return pd.DataFrame(
            result.fetchall(),
            columns=result.keys()
        )


# =========================================================
# LOAD BATCHES
# =========================================================

@st.cache_data(ttl=10)
def load_batches(product_id=None):

    query = """
        SELECT
            b.BatchID,
            b.ProductID,
            p.ProductName,
            p.Barcode,
            b.BatchNo,
            b.ManufacturingDate,
            b.ExpiryDate,
            b.PurchasePrice,
            b.SellingPrice,
            b.GSTPercent,
            b.Quantity,
            b.CreatedDate,

            CASE
                WHEN b.ExpiryDate < CAST(GETDATE() AS DATE)
                    THEN 'Expired'

                WHEN b.ExpiryDate <= DATEADD(day, 7, CAST(GETDATE() AS DATE))
                    THEN 'Expires in 7 days'

                WHEN b.ExpiryDate <= DATEADD(day, 30, CAST(GETDATE() AS DATE))
                    THEN 'Expires in 30 days'

                ELSE 'Good'
            END AS ExpiryStatus

        FROM ProductBatches b

        INNER JOIN Products p
            ON p.ProductID = b.ProductID

        WHERE b.IsActive = 1
    """

    params = {}

    if product_id is not None:

        query += """
            AND b.ProductID = :product_id
        """

        params["product_id"] = int(product_id)

    query += """
        ORDER BY
            b.ExpiryDate ASC,
            p.ProductName ASC
    """

    with engine.connect() as connection:

        result = connection.execute(
            text(query),
            params
        )

        return pd.DataFrame(
            result.fetchall(),
            columns=result.keys()
        )


# =========================================================
# SUMMARY
# =========================================================

try:

    all_batches = load_batches()

    if all_batches.empty:

        total_batches = 0
        total_batch_stock = 0
        expired_batches = 0
        expiring_batches = 0

    else:

        total_batches = len(all_batches)

        total_batch_stock = float(
            all_batches["Quantity"]
            .fillna(0)
            .sum()
        )

        expired_batches = int(
            (
                all_batches["ExpiryStatus"]
                == "Expired"
            ).sum()
        )

        expiring_batches = int(
            all_batches["ExpiryStatus"]
            .isin(
                [
                    "Expires in 7 days",
                    "Expires in 30 days"
                ]
            ).sum()
        )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "📦 Total Batches",
        total_batches
    )

    c2.metric(
        "📊 Batch Stock",
        f"{total_batch_stock:,.2f}"
    )

    c3.metric(
        "🔴 Expired",
        expired_batches
    )

    c4.metric(
        "🟠 Expiring Soon",
        expiring_batches
    )

except Exception as e:

    st.error("Unable to load batch information.")
    log_exception(e)
    st.exception(e)


st.divider()


# =========================================================
# ADD BATCH
# =========================================================

st.subheader("➕ Add New Batch")


search_product = st.text_input(
    "🔍 Search Product",
    placeholder="Product name or barcode..."
)


products = load_products(search_product)


if products.empty:

    st.warning("No products found.")

else:

    product_options = {}

    for _, row in products.iterrows():

        barcode = (
            ""
            if pd.isna(row["Barcode"])
            else str(row["Barcode"])
        )

        label = (
            f"{row['ProductName']} "
            f"| Stock: {float(row['Stock'] or 0):g}"
        )

        if barcode:
            label += f" | {barcode}"

        product_options[label] = int(
            row["ProductID"]
        )

    selected_label = st.selectbox(
        "Select Product",
        list(product_options.keys())
    )

    selected_product_id = product_options[
        selected_label
    ]

    selected_product = products[
        products["ProductID"]
        == selected_product_id
    ].iloc[0]


    # -----------------------------------------------------
    # Existing product information
    # -----------------------------------------------------

    info1, info2, info3, info4 = st.columns(4)

    info1.metric(
        "Current Stock",
        f"{float(selected_product['Stock'] or 0):,.2f}"
    )

    info2.metric(
        "Purchase Price",
        f"₹{float(selected_product['PurchasePrice'] or 0):,.2f}"
    )

    info3.metric(
        "Selling Price",
        f"₹{float(selected_product['SellingPrice'] or 0):,.2f}"
    )

    info4.metric(
        "GST",
        f"{float(selected_product['GSTPercent'] or 0):g}%"
    )


    st.write("")


    # -----------------------------------------------------
    # Batch form
    # -----------------------------------------------------

    with st.form("batch_form"):

        c1, c2 = st.columns(2)

        with c1:

            batch_no = st.text_input(
                "Batch Number *",
                placeholder="Example: BATCH-001"
            )

            manufacturing_date = st.date_input(
                "Manufacturing Date",
                value=date.today()
            )

            purchase_price = st.number_input(
                "Purchase Price *",
                min_value=0.0,
                value=float(
                    selected_product["PurchasePrice"] or 0
                ),
                step=0.01
            )

        with c2:

            expiry_date = st.date_input(
                "Expiry Date *",
                value=date(
                    date.today().year + 1,
                    date.today().month,
                    date.today().day
                )
            )

            selling_price = st.number_input(
                "Selling Price *",
                min_value=0.0,
                value=float(
                    selected_product["SellingPrice"] or 0
                ),
                step=0.01
            )

            gst_percent = st.number_input(
                "GST %",
                min_value=0.0,
                max_value=100.0,
                value=float(
                    selected_product["GSTPercent"] or 0
                ),
                step=0.5
            )

        quantity = st.number_input(
            "Quantity *",
            min_value=0.01,
            value=1.0,
            step=1.0
        )


        submitted = st.form_submit_button(
            "💾 SAVE BATCH",
            type="primary",
            use_container_width=True
        )


    # -----------------------------------------------------
    # Save batch
    # -----------------------------------------------------

    if submitted:

        if not batch_no.strip():

            st.error(
                "Batch number is required."
            )

        elif expiry_date < manufacturing_date:

            st.error(
                "Expiry date cannot be before manufacturing date."
            )

        elif expiry_date < date.today():

            st.error(
                "Cannot add an already expired batch."
            )

        elif quantity <= 0:

            st.error(
                "Quantity must be greater than zero."
            )

        elif selling_price <= 0:

            st.error(
                "Selling price must be greater than zero."
            )

        else:

            try:

                with engine.begin() as connection:

                    # -------------------------------------
                    # Check duplicate batch
                    # -------------------------------------

                    existing = connection.execute(
                        text("""
                            SELECT BatchID
                            FROM ProductBatches
                            WHERE ProductID = :product_id
                              AND BatchNo = :batch_no
                        """),
                        {
                            "product_id": selected_product_id,
                            "batch_no": batch_no.strip()
                        }
                    ).scalar()

                    if existing:

                        raise ValueError(
                            "This batch number already exists "
                            "for this product."
                        )


                    # -------------------------------------
                    # Insert batch
                    # -------------------------------------

                    connection.execute(
                        text("""
                            INSERT INTO ProductBatches
                            (
                                ProductID,
                                BatchNo,
                                ManufacturingDate,
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
                                :manufacturing_date,
                                :expiry_date,
                                :purchase_price,
                                :selling_price,
                                :gst_percent,
                                :quantity,
                                1
                            )
                        """),
                        {
                            "product_id": selected_product_id,
                            "batch_no": batch_no.strip(),
                            "manufacturing_date": manufacturing_date,
                            "expiry_date": expiry_date,
                            "purchase_price": purchase_price,
                            "selling_price": selling_price,
                            "gst_percent": gst_percent,
                            "quantity": quantity
                        }
                    )


                    # -------------------------------------
                    # Update total product stock
                    # -------------------------------------

                    connection.execute(
                        text("""
                            UPDATE Products
                            SET
                                Stock = COALESCE(Stock, 0)
                                         + :quantity,

                                PurchasePrice = :purchase_price,

                                SellingPrice = :selling_price,

                                GSTPercent = :gst_percent

                            WHERE ProductID = :product_id
                        """),
                        {
                            "quantity": quantity,
                            "purchase_price": purchase_price,
                            "selling_price": selling_price,
                            "gst_percent": gst_percent,
                            "product_id": selected_product_id
                        }
                    )


                # Clear cache

                load_products.clear()
                load_batches.clear()


                st.success(
                    f"✅ Batch {batch_no.strip()} "
                    f"added successfully."
                )

                st.rerun()


            except Exception as e:

                st.error(
                    "Unable to save batch."
                )

                log_exception(e)
                st.exception(e)


st.divider()


# =========================================================
# BATCH LIST
# =========================================================

st.subheader("📋 Batch Inventory")


filter_option = st.selectbox(
    "Show",
    [
        "All Batches",
        "Active Stock Only",
        "Expired",
        "Expires in 7 Days",
        "Expires in 30 Days"
    ]
)


try:

    batches = load_batches(
        selected_product_id
        if products is not None and not products.empty
        else None
    )


    # -----------------------------------------------------
    # Filters
    # -----------------------------------------------------

    if filter_option == "Active Stock Only":

        batches = batches[
            batches["Quantity"] > 0
        ]

    elif filter_option == "Expired":

        batches = batches[
            batches["ExpiryStatus"]
            == "Expired"
        ]

    elif filter_option == "Expires in 7 Days":

        batches = batches[
            batches["ExpiryStatus"]
            == "Expires in 7 days"
        ]

    elif filter_option == "Expires in 30 Days":

        batches = batches[
            batches["ExpiryStatus"]
            == "Expires in 30 days"
        ]


    if batches.empty:

        st.info(
            "No batches found."
        )

    else:

        display = batches[
            [
                "ProductName",
                "BatchNo",
                "ManufacturingDate",
                "ExpiryDate",
                "PurchasePrice",
                "SellingPrice",
                "GSTPercent",
                "Quantity",
                "ExpiryStatus"
            ]
        ].copy()


        display.columns = [
            "Product",
            "Batch",
            "Manufactured",
            "Expiry",
            "Purchase Price",
            "Selling Price",
            "GST %",
            "Quantity",
            "Status"
        ]


        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True
        )


except Exception as e:

    st.error(
        "Unable to load batch inventory."
    )

    log_exception(e)
    log_exception(e)
    st.exception(e)