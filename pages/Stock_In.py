import streamlit as st
import pandas as pd
from database.database import engine
from sqlalchemy import text

from auth import require_role
require_role("Manager", "Admin")
#st.title("📥 Stock In / Purchase")


# =====================================
# SUPPLIER
# =====================================

st.subheader("Purchase Details")

supplier_name = st.text_input(
    "Supplier Name",
    placeholder="Enter supplier name"
)


# =====================================
# LOAD PRODUCTS
# =====================================

try:

    products = pd.read_sql(
        """
        SELECT
            ProductID,
            ProductName,
            Barcode,
            Stock,
            SellingPrice
        FROM Products
        ORDER BY ProductName
        """,
        engine
    )

except Exception as e:

    st.error("Could not load products.")
    st.exception(e)
    st.stop()


if products.empty:

    st.warning(
        "No products found. Add products first."
    )

    st.stop()


# =====================================
# SELECT PRODUCT
# =====================================

st.subheader("Add Purchase Item")

selected_product = st.selectbox(
    "Product",
    products["ProductName"].tolist()
)


selected = products[
    products["ProductName"] == selected_product
].iloc[0]


col1, col2 = st.columns(2)

with col1:

    st.write("Current Stock")
    st.write(f"{selected['Stock']}")


with col2:

    st.write("Selling Price")
    st.write(
        f"₹{selected['SellingPrice']:.2f}"
    )


quantity = st.number_input(
    "Purchase Quantity",
    min_value=0.01,
    value=1.0,
    step=1.0
)


purchase_price = st.number_input(
    "Purchase Price",
    min_value=0.0,
    value=0.0,
    step=0.01
)


# =====================================
# PURCHASE CART
# =====================================

if "purchase_cart" not in st.session_state:

    st.session_state.purchase_cart = []


if st.button("➕ Add to Purchase"):

    item = {
        "ProductID": int(selected["ProductID"]),
        "ProductName": selected["ProductName"],
        "Quantity": quantity,
        "PurchasePrice": purchase_price
    }

    st.session_state.purchase_cart.append(item)

    st.success("Item added to purchase.")


# =====================================
# PURCHASE LIST
# =====================================

st.divider()

st.subheader("📋 Current Purchase")


if len(st.session_state.purchase_cart) == 0:

    st.info("No items added.")


else:

    total_amount = 0

    purchase_data = []


    for item in st.session_state.purchase_cart:

        amount = (
            item["Quantity"] *
            item["PurchasePrice"]
        )

        total_amount += amount


        purchase_data.append(
            {
                "Product": item["ProductName"],
                "Quantity": item["Quantity"],
                "Purchase Price": item["PurchasePrice"],
                "Amount": amount
            }
        )


    purchase_df = pd.DataFrame(
        purchase_data
    )


    st.dataframe(
        purchase_df,
        use_container_width=True,
        hide_index=True
    )


    st.subheader(
        f"Total Purchase: ₹{total_amount:,.2f}"
    )


    # =================================
    # SAVE PURCHASE
    # =================================

    if st.button("💾 Save Purchase"):

        try:

            with engine.begin() as connection:

                # Save purchase header

                result = connection.execute(
                    text(
                        """
                        INSERT INTO Purchases
                        (
                            SupplierName,
                            TotalAmount
                        )
                        OUTPUT INSERTED.PurchaseID
                        VALUES
                        (
                            :supplier,
                            :total
                        )
                        """
                    ),
                    {
                        "supplier": supplier_name,
                        "total": total_amount
                    }
                )


                purchase_id = result.fetchone()[0]


                # Save purchase items
                # and increase stock

                for item in st.session_state.purchase_cart:

                    amount = (
                        item["Quantity"] *
                        item["PurchasePrice"]
                    )


                    connection.execute(
                        text(
                            """
                            INSERT INTO PurchaseItems
                            (
                                PurchaseID,
                                ProductID,
                                Quantity,
                                PurchasePrice,
                                Amount
                            )
                            VALUES
                            (
                                :purchase_id,
                                :product_id,
                                :quantity,
                                :price,
                                :amount
                            )
                            """
                        ),
                        {
                            "purchase_id": purchase_id,
                            "product_id": item["ProductID"],
                            "quantity": item["Quantity"],
                            "price": item["PurchasePrice"],
                            "amount": amount
                        }
                    )


                    # Increase stock

                    connection.execute(
                        text(
                            """
                            UPDATE Products
                            SET Stock = Stock + :quantity
                            WHERE ProductID = :product_id
                            """
                        ),
                        {
                            "quantity": item["Quantity"],
                            "product_id": item["ProductID"]
                        }
                    )


            st.success(
                f"Purchase saved successfully! "
                f"Purchase No: {purchase_id}"
            )


            st.session_state.purchase_cart = []

            st.rerun()


        except Exception as e:

            st.error("Error saving purchase.")
            st.exception(e)


    # =================================
    # CLEAR PURCHASE
    # =================================

    if st.button("🗑️ Clear Purchase"):

        st.session_state.purchase_cart = []

        st.rerun()