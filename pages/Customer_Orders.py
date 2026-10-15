import pandas as pd
import streamlit as st
from sqlalchemy import text

from auth import require_role
from customer_orders import (
    complete_customer_order,
    ensure_customer_order_tables,
    reject_customer_order,
)
from database.database import engine
from logging_config import get_logger


logger = get_logger(__name__)
user = require_role("Sales Boy")

st.set_page_config(
    page_title="Customer Orders",
    page_icon="🛍️",
    layout="wide",
)

st.caption(
    "Review mobile checkout orders. Completing an order creates a POS sale and "
    "deducts stock from the earliest-expiring unexpired batches."
)


def load_orders():
    with engine.begin() as connection:
        ensure_customer_order_tables(connection)
        rows = connection.execute(
            text("""
                SELECT o."OrderID", o."OrderDate", o."Status",
                       c."CustomerName", COALESCE(c."Mobile", '') AS "Mobile",
                       o."PaymentMode", o."SubTotal", o."GSTAmount",
                       o."GrandTotal", o."DeliveryAddress", o."Notes",
                       o."SaleID"
                FROM "CustomerOrders" AS o
                JOIN "Customers" AS c ON c."CustomerID" = o."CustomerID"
                ORDER BY
                    CASE WHEN o."Status" = 'Pending' THEN 0 ELSE 1 END,
                    o."OrderDate" DESC,
                    o."OrderID" DESC
            """)
        ).mappings().all()
    return pd.DataFrame([dict(row) for row in rows])


def load_order_items(order_id):
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT "ProductName", "Quantity", "Price", "GSTPercent",
                       "Amount", "GSTAmount"
                FROM "CustomerOrderItems"
                WHERE "OrderID" = :order_id
                ORDER BY "OrderItemID"
            """),
            {"order_id": int(order_id)},
        ).mappings().all()
    return pd.DataFrame([dict(row) for row in rows])


try:
    orders = load_orders()
except Exception:
    logger.exception("customer_orders_load_failed")
    st.error("Unable to load customer orders. Check the database connection.")
    st.stop()

if orders.empty:
    st.info("No customer orders have been submitted yet.")
    st.stop()

pending_count = int((orders["Status"] == "Pending").sum())
completed_count = int((orders["Status"] == "Completed").sum())
rejected_count = int((orders["Status"] == "Rejected").sum())
metric_cols = st.columns(3)
metric_cols[0].metric("Pending", pending_count)
metric_cols[1].metric("Completed", completed_count)
metric_cols[2].metric("Rejected", rejected_count)

status_filter = st.selectbox(
    "Show orders",
    ["Pending", "All", "Completed", "Rejected"],
    key="customer_orders_status_filter",
)
if status_filter != "All":
    visible_orders = orders[orders["Status"] == status_filter]
else:
    visible_orders = orders

if visible_orders.empty:
    st.info(f"No {status_filter.lower()} orders.")
    st.stop()

for order in visible_orders.to_dict("records"):
    order_id = int(order["OrderID"])
    status = str(order["Status"])
    total = float(order["GrandTotal"])
    title = (
        f"Order #{order_id} · {order['CustomerName']} · "
        f"₹{total:,.2f} · {status}"
    )

    with st.expander(title, expanded=status == "Pending"):
        st.write(f"**Submitted:** {order['OrderDate']}")
        st.write(f"**Customer:** {order['CustomerName']} · {order['Mobile']}")
        st.write(f"**Checkout payment selection:** {order['PaymentMode']}")
        if order["DeliveryAddress"]:
            st.write(f"**Delivery address:** {order['DeliveryAddress']}")
        if order["Notes"]:
            st.write(f"**Customer notes:** {order['Notes']}")

        try:
            items = load_order_items(order_id)
        except Exception:
            logger.exception(
                "customer_order_items_load_failed order_id=%s",
                order_id,
            )
            st.error("Unable to load this order's items.")
            continue

        if not items.empty:
            display_items = items.rename(
                columns={
                    "ProductName": "Product",
                    "Quantity": "Quantity",
                    "Price": "Unit Price",
                    "GSTPercent": "GST %",
                    "Amount": "Amount",
                    "GSTAmount": "GST",
                }
            )
            st.dataframe(
                display_items,
                hide_index=True,
                use_container_width=True,
            )

        st.write(
            f"Subtotal ₹{float(order['SubTotal']):,.2f} · "
            f"GST ₹{float(order['GSTAmount']):,.2f} · "
            f"**Total ₹{total:,.2f}**"
        )

        if status == "Completed":
            st.success(f"Completed as POS sale #{int(order['SaleID'])}.")
        elif status == "Pending":
            st.warning(
                "No payment gateway is connected. Confirm the payment was "
                "actually received before completing."
            )
            payment_col, amount_col = st.columns(2)
            payment_modes = ["Cash", "UPI", "Card"]
            selected_payment = payment_col.selectbox(
                "Payment received by",
                payment_modes,
                index=(
                    payment_modes.index(order["PaymentMode"])
                    if order["PaymentMode"] in payment_modes
                    else 0
                ),
                key=f"order_payment_mode_{order_id}",
            )
            amount_received = amount_col.number_input(
                "Amount actually received (₹)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                key=f"order_amount_received_{order_id}",
            )
            complete_col, reject_col = st.columns(2)
            if complete_col.button(
                "Complete order and record sale",
                type="primary",
                key=f"complete_order_{order_id}",
                use_container_width=True,
            ):
                try:
                    sale_id = complete_customer_order(
                        order_id,
                        int(user["UserID"]),
                        selected_payment,
                        amount_received,
                    )
                    st.success(
                        f"Order completed and saved as POS sale #{sale_id}."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    logger.exception(
                        "customer_order_completion_failed order_id=%s user_id=%s",
                        order_id,
                        user.get("UserID"),
                    )
                    st.error(
                        "Could not complete the order. No sale or stock change "
                        "was committed."
                    )

            if reject_col.button(
                "Reject order",
                key=f"reject_order_{order_id}",
                use_container_width=True,
            ):
                try:
                    reject_customer_order(order_id)
                    st.success(f"Order #{order_id} rejected.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    logger.exception(
                        "customer_order_rejection_failed order_id=%s user_id=%s",
                        order_id,
                        user.get("UserID"),
                    )
                    st.error("Could not reject this order.")
