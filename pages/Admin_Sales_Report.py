import streamlit as st
from logging_config import log_exception
import pandas as pd
from sqlalchemy import text
from database.database import engine
from auth import require_role

user = require_role("Admin")

#st.title("👑 Admin Sales Report")
st.caption("Complete sales, employee and profit report")

# ---------------------------------------------------------
# FILTERS
# ---------------------------------------------------------
today = pd.Timestamp.today().normalize()

c1, c2 = st.columns(2)
from_date = pd.Timestamp(c1.date_input("From Date", today))
to_date = pd.Timestamp(c2.date_input("To Date", today))

if from_date > to_date:
    st.error("From Date cannot be after To Date.")
    st.stop()

start_dt = from_date.strftime("%Y-%m-%d")
end_dt = (to_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

try:
    with engine.connect() as connection:
        employees = pd.read_sql(
            text("""
                SELECT UserID, FullName
                FROM Users
                WHERE IsActive = 1
                ORDER BY FullName
            """),
            connection
        )
except Exception as e:
    st.error("Unable to load employees.")
    log_exception(e)
    st.exception(e)
    st.stop()

employee_options = ["All Employees"] + employees["FullName"].tolist()
selected_employee = st.selectbox("Salesperson", employee_options)

employee_filter = ""
params = {
    "start_date": start_dt,
    "end_date": end_dt
}

if selected_employee != "All Employees":
    selected_user_id = int(
        employees.loc[
            employees["FullName"] == selected_employee,
            "UserID"
        ].iloc[0]
    )
    employee_filter = " AND s.UserID = :user_id"
    params["user_id"] = selected_user_id

# ---------------------------------------------------------
# COMPLETE SALES REPORT
# SaleItems uses Price, PurchasePrice and ProfitAmount.
# ---------------------------------------------------------
query = text(f"""
    SELECT
        s.SaleID,
        s.SaleDate,
        s.CustomerName,
        COALESCE(u.FullName, 'Unknown') AS Salesperson,
        s.PaymentMode,
        SUM(si.Quantity) AS TotalQty,
        SUM(si.Amount) AS SalesValue,
        SUM(si.Quantity * si.PurchasePrice) AS PurchaseCost,
        SUM(si.ProfitAmount) AS GrossProfit
    FROM Sales s
    INNER JOIN SaleItems si
        ON si.SaleID = s.SaleID
    LEFT JOIN Users u
        ON u.UserID = s.UserID
    WHERE s.SaleDate >= :start_date
      AND s.SaleDate < :end_date
      {employee_filter}
    GROUP BY
        s.SaleID,
        s.SaleDate,
        s.CustomerName,
        u.FullName,
        s.PaymentMode
    ORDER BY s.SaleDate DESC, s.SaleID DESC
""")

try:
    with engine.connect() as connection:
        sales = pd.read_sql(query, connection, params=params)
except Exception as e:
    st.error("Unable to load admin sales report.")
    log_exception(e)
    st.exception(e)
    st.stop()

if sales.empty:
    st.info("No sales found for the selected period.")
    st.stop()

# ---------------------------------------------------------
# KPIs
# ---------------------------------------------------------
total_sales = float(sales["SalesValue"].sum())
purchase_cost = float(sales["PurchaseCost"].sum())
gross_profit = float(sales["GrossProfit"].sum())
total_bills = int(sales["SaleID"].nunique())
total_qty = float(sales["TotalQty"].sum())
margin = (gross_profit / total_sales * 100) if total_sales else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Sales", f"₹{total_sales:,.2f}")
c2.metric("Purchase Cost", f"₹{purchase_cost:,.2f}")
c3.metric("Gross Profit", f"₹{gross_profit:,.2f}")
c4.metric("Bills", total_bills)
c5.metric("Profit Margin", f"{margin:.2f}%")

st.metric("Total Quantity Sold", f"{total_qty:,.2f}")

# ---------------------------------------------------------
# BILL-WISE REPORT
# ---------------------------------------------------------
st.subheader("🧾 Bill-wise Sales & Profit")

display = sales.copy()
display["SaleDate"] = pd.to_datetime(display["SaleDate"]).dt.strftime(
    "%d-%m-%Y %H:%M"
)
display["SalesValue"] = display["SalesValue"].round(2)
display["PurchaseCost"] = display["PurchaseCost"].round(2)
display["GrossProfit"] = display["GrossProfit"].round(2)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True
)

# ---------------------------------------------------------
# EMPLOYEE SUMMARY
# ---------------------------------------------------------
st.subheader("👥 Employee-wise Sales")

employee_summary = (
    sales.groupby("Salesperson", dropna=False)
    .agg(
        Bills=("SaleID", "nunique"),
        Quantity=("TotalQty", "sum"),
        Sales=("SalesValue", "sum"),
        PurchaseCost=("PurchaseCost", "sum"),
        GrossProfit=("GrossProfit", "sum")
    )
    .reset_index()
)

employee_summary["Profit Margin %"] = employee_summary.apply(
    lambda row: (
        row["GrossProfit"] / row["Sales"] * 100
        if row["Sales"] else 0
    ),
    axis=1
).round(2)

st.dataframe(
    employee_summary.round(2),
    use_container_width=True,
    hide_index=True
)

# ---------------------------------------------------------
# PAYMENT SUMMARY
# ---------------------------------------------------------
st.subheader("💳 Payment Mode Summary")

payment_summary = (
    sales.groupby("PaymentMode")
    .agg(
        Bills=("SaleID", "nunique"),
        Sales=("SalesValue", "sum")
    )
    .reset_index()
)

st.dataframe(
    payment_summary.round(2),
    use_container_width=True,
    hide_index=True
)

# ---------------------------------------------------------
# DAILY SALES / PROFIT
# ---------------------------------------------------------
st.subheader("📈 Daily Sales & Profit")

daily = (
    sales.assign(
        Date=pd.to_datetime(sales["SaleDate"]).dt.date
    )
    .groupby("Date")
    .agg(
        Sales=("SalesValue", "sum"),
        PurchaseCost=("PurchaseCost", "sum"),
        GrossProfit=("GrossProfit", "sum")
    )
    .reset_index()
)

st.line_chart(
    daily.set_index("Date")[["Sales", "GrossProfit"]]
)

# ---------------------------------------------------------
# EXPORT
# ---------------------------------------------------------
st.download_button(
    "⬇️ Export Admin Sales Report CSV",
    display.to_csv(index=False).encode("utf-8"),
    "admin_sales_report.csv",
    "text/csv"
)
