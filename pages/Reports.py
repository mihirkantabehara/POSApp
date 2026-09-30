import streamlit as st
import pandas as pd
from sqlalchemy import text

from database.database import engine
from auth import require_role

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")

user = require_role("Manager", "Admin")

#st.title("📊 Sales & Profit Reports")

period = st.selectbox(
    "Period",
    ["Today", "Yesterday", "This Week", "This Month", "Custom"]
)

today = pd.Timestamp.today().normalize()

if period == "Today":
    start_date = today
    end_date = today
elif period == "Yesterday":
    start_date = today - pd.Timedelta(days=1)
    end_date = start_date
elif period == "This Week":
    start_date = today - pd.Timedelta(days=int(today.dayofweek))
    end_date = today
elif period == "This Month":
    start_date = today.replace(day=1)
    end_date = today
else:
    c1, c2 = st.columns(2)
    start_date = pd.Timestamp(c1.date_input("From", today))
    end_date = pd.Timestamp(c2.date_input("To", today))

start_dt = start_date.strftime("%Y-%m-%d")
end_dt = (end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

# IMPORTANT:
# Your SaleItems table uses Price, not UnitPrice.
# PurchasePrice and ProfitAmount are already present.
query = text("""
    SELECT
        s.SaleID,
        s.SaleDate,
        s.CustomerName,
        s.PaymentMode,
        u.FullName AS Salesperson,
        SUM(si.Quantity * si.Price) AS SalesValue,
        SUM(si.Quantity * si.PurchasePrice) AS PurchaseCost,
        SUM(si.ProfitAmount) AS Profit
    FROM Sales s
    INNER JOIN SaleItems si
        ON si.SaleID = s.SaleID
    LEFT JOIN Users u
        ON u.UserID = s.UserID
    WHERE s.SaleDate >= :start_date
      AND s.SaleDate < :end_date
    GROUP BY
        s.SaleID,
        s.SaleDate,
        s.CustomerName,
        s.PaymentMode,
        u.FullName
    ORDER BY s.SaleDate DESC
""")

try:
    with engine.connect() as connection:
        sales = pd.read_sql(
            query,
            connection,
            params={
                "start_date": start_dt,
                "end_date": end_dt
            }
        )
except Exception as e:
    st.error("Unable to load profit data.")
    st.exception(e)
    st.stop()

if sales.empty:
    st.info("No sales found for this period.")
    st.stop()

total_sales = sales["SalesValue"].sum()
total_cost = sales["PurchaseCost"].sum()
total_profit = sales["Profit"].sum()
margin = (total_profit / total_sales * 100) if total_sales else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sales", f"₹{total_sales:,.2f}")
c2.metric("Purchase Cost", f"₹{total_cost:,.2f}")
c3.metric("Gross Profit", f"₹{total_profit:,.2f}")
c4.metric("Profit Margin", f"{margin:.2f}%")

st.subheader("Bill-wise Profit")

display_sales = sales.copy()
display_sales["SalesValue"] = display_sales["SalesValue"].round(2)
display_sales["PurchaseCost"] = display_sales["PurchaseCost"].round(2)
display_sales["Profit"] = display_sales["Profit"].round(2)

st.dataframe(
    display_sales,
    use_container_width=True,
    hide_index=True
)

st.subheader("Profit by Salesperson")

employee = (
    sales.groupby("Salesperson", dropna=False)
    .agg(
        Sales=("SalesValue", "sum"),
        PurchaseCost=("PurchaseCost", "sum"),
        Profit=("Profit", "sum")
    )
    .reset_index()
)

employee["Margin %"] = employee.apply(
    lambda r: (r["Profit"] / r["Sales"] * 100)
    if r["Sales"] else 0,
    axis=1
)

st.dataframe(
    employee,
    use_container_width=True,
    hide_index=True
)

st.subheader("Profit by Day")

daily = (
    sales.assign(Date=pd.to_datetime(sales["SaleDate"]).dt.date)
    .groupby("Date")
    .agg(
        Sales=("SalesValue", "sum"),
        PurchaseCost=("PurchaseCost", "sum"),
        Profit=("Profit", "sum")
    )
    .reset_index()
)

st.line_chart(
    daily.set_index("Date")[["Sales", "Profit"]]
)

st.download_button(
    "⬇️ Export Profit Report CSV",
    sales.to_csv(index=False).encode("utf-8"),
    "profit_report.csv",
    "text/csv"
)
