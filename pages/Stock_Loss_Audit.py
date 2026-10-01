import streamlit as st
from logging_config import log_exception
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_role

st.set_page_config(
    page_title="Stock Adjustment Audit",
    page_icon="🧮",
    layout="wide"
)

user = require_role("Manager", "Admin")

#st.title("🧮 Stock Adjustment Audit")
st.caption("Every manual stock change is recorded with user, old stock, new stock, reason and value.")

@st.cache_data(ttl=30)
def load_products():
    query = text("""
        SELECT ProductID, ProductName, Barcode, SellingPrice, Stock
        FROM Products
        ORDER BY ProductName
    """)
    with engine.connect() as connection:
        return pd.read_sql(query, connection)

products = load_products()

if products.empty:
    st.info("No products found.")
    st.stop()

tab1, tab2 = st.tabs(["➕ New Adjustment", "📜 Adjustment History"])

with tab1:
    product_options = {
        f"{row['ProductName']} | {row['Barcode'] if pd.notna(row['Barcode']) else ''}":
        int(row["ProductID"])
        for _, row in products.iterrows()
    }

    selected = st.selectbox(
        "Select Product",
        list(product_options.keys())
    )
    product_id = product_options[selected]

    row = products[products["ProductID"] == product_id].iloc[0]
    old_stock = float(row["Stock"] or 0)
    unit_price = float(row["SellingPrice"] or 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Stock", f"{old_stock:g}")
    c2.metric("Unit Price", f"₹{unit_price:,.2f}")

    with c3:
        new_stock = st.number_input(
            "New Stock",
            min_value=0.0,
            value=old_stock,
            step=1.0
        )

    difference = new_stock - old_stock
    difference_value = difference * unit_price

    if difference < 0:
        st.warning(
            f"Stock reduction: {abs(difference):g} units "
            f"(₹{abs(difference_value):,.2f})"
        )
        adjustment_type = "Reduction"
    elif difference > 0:
        st.success(
            f"Stock increase: {difference:g} units "
            f"(₹{difference_value:,.2f})"
        )
        adjustment_type = "Increase"
    else:
        st.info("No stock change.")
        adjustment_type = "No Change"

    reason = st.text_area(
        "Reason *",
        placeholder="Example: Damaged goods, missing stock, purchase correction, counting error..."
    )

    if st.button(
        "💾 Save Stock Adjustment",
        type="primary",
        use_container_width=True
    ):
        if difference == 0:
            st.warning("There is no stock change to save.")
        elif not reason.strip():
            st.warning("Please enter a reason for the adjustment.")
        else:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            INSERT INTO StockAdjustments
                            (
                                ProductID,
                                UserID,
                                OldStock,
                                NewStock,
                                DifferenceQty,
                                UnitPrice,
                                DifferenceValue,
                                AdjustmentType,
                                Reason
                            )
                            VALUES
                            (
                                :product_id,
                                :user_id,
                                :old_stock,
                                :new_stock,
                                :difference_qty,
                                :unit_price,
                                :difference_value,
                                :adjustment_type,
                                :reason
                            )
                        """),
                        {
                            "product_id": product_id,
                            "user_id": int(user["UserID"]),
                            "old_stock": old_stock,
                            "new_stock": new_stock,
                            "difference_qty": difference,
                            "unit_price": unit_price,
                            "difference_value": difference_value,
                            "adjustment_type": adjustment_type,
                            "reason": reason.strip()
                        }
                    )

                    connection.execute(
                        text("""
                            UPDATE Products
                            SET Stock = :new_stock
                            WHERE ProductID = :product_id
                        """),
                        {
                            "new_stock": new_stock,
                            "product_id": product_id
                        }
                    )

                load_products.clear()
                st.success("Stock adjustment saved successfully.")
                st.rerun()

            except Exception as e:
                st.error("Unable to save stock adjustment.")
                log_exception(e)
                st.exception(e)

with tab2:
    st.subheader("Stock Adjustment History")

    c1, c2, c3 = st.columns(3)

    with c1:
        from_date = st.date_input(
            "From",
            value=pd.Timestamp.today().date()
        )

    with c2:
        to_date = st.date_input(
            "To",
            value=pd.Timestamp.today().date()
        )

    with c3:
        adjustment_filter = st.selectbox(
            "Type",
            ["All", "Increase", "Reduction"]
        )

    query = text("""
        SELECT
            a.StockAdjustmentID,
            a.AdjustmentDateTime,
            p.ProductName,
            p.Barcode,
            u.FullName AS AdjustedBy,
            a.AdjustmentType,
            a.OldStock,
            a.NewStock,
            a.DifferenceQty,
            a.UnitPrice,
            a.DifferenceValue,
            a.Reason
        FROM StockAdjustments a
        INNER JOIN Products p ON p.ProductID = a.ProductID
        INNER JOIN Users u ON u.UserID = a.UserID
        WHERE a.AdjustmentDateTime >= :from_date
          AND a.AdjustmentDateTime < DATEADD(day, 1, :to_date)
        ORDER BY a.AdjustmentDateTime DESC
    """)

    try:
        with engine.connect() as connection:
            history = pd.read_sql(
                query,
                connection,
                params={
                    "from_date": str(from_date),
                    "to_date": str(to_date)
                }
            )

        if adjustment_filter != "All":
            history = history[
                history["AdjustmentType"] == adjustment_filter
            ]

        if history.empty:
            st.info("No stock adjustments found.")
        else:
            reductions = history[
                history["AdjustmentType"] == "Reduction"
            ]
            increases = history[
                history["AdjustmentType"] == "Increase"
            ]

            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Adjustments",
                len(history)
            )
            m2.metric(
                "Reduction Value",
                f"₹{abs(reductions['DifferenceValue'].sum()):,.2f}"
            )
            m3.metric(
                "Increase Value",
                f"₹{increases['DifferenceValue'].sum():,.2f}"
            )

            st.dataframe(
                history,
                use_container_width=True,
                hide_index=True
            )

            csv = history.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Export Adjustment Audit CSV",
                csv,
                "stock_adjustment_audit.csv",
                "text/csv"
            )

    except Exception as e:
        st.error("Unable to load adjustment history.")
        log_exception(e)
        st.exception(e)
