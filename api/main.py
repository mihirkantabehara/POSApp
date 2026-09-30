from datetime import datetime, timedelta
import hashlib
import hmac
import jwt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text
from database.database import engine

JWT_SECRET = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12

app = FastAPI(title="POS Mobile API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def create_token(user):
    payload = {
        "UserID": user["UserID"],
        "Username": user["Username"],
        "FullName": user["FullName"],
        "Role": user["Role"],
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        return {
            "UserID": int(payload["UserID"]),
            "Username": str(payload["Username"]),
            "FullName": str(payload["FullName"]),
            "Role": str(payload["Role"]),
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

def roles(*allowed):
    def check(user=Depends(current_user)):
        if user["Role"] not in allowed:
            raise HTTPException(status_code=403, detail="Permission denied.")
        return user
    return check

class LoginRequest(BaseModel):
    username: str
    password: str

class SaleItemRequest(BaseModel):
    ProductID: int
    Quantity: float = Field(gt=0)

class SaleRequest(BaseModel):
    CustomerName: str = "Walk-in Customer"
    PaymentMode: str
    AmountPaid: float = Field(ge=0)
    Items: list[SaleItemRequest]

@app.get("/")
def root():
    return {"status": "ok", "service": "POS Mobile API"}

@app.get("/health")
def health():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database connection failed.")

@app.post("/login")
def login(request: LoginRequest):
    try:
        with engine.connect() as c:
            row = c.execute(
                text("""
                    SELECT UserID, Username, PasswordHash, FullName, Role, IsActive
                    FROM Users WHERE Username = :username
                """),
                {"username": request.username.strip()}
            ).mappings().first()

        if not row or not bool(row["IsActive"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")

        if not hmac.compare_digest(
            hash_password(request.password), str(row["PasswordHash"])
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password.")

        user = {
            "UserID": int(row["UserID"]),
            "Username": str(row["Username"]),
            "FullName": str(row["FullName"]),
            "Role": str(row["Role"]),
        }
        return {"token": create_token(user), "user": user}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to access user database.")

@app.get("/me")
def me(user=Depends(current_user)):
    return user

@app.get("/products")
def products(user=Depends(roles("Sales Boy", "Manager", "Admin"))):
    try:
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT ProductID, ProductName, Barcode, SellingPrice, Stock, GSTPercent
                FROM Products ORDER BY ProductName
            """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load products.")

@app.get("/customers")
def customers(user=Depends(roles("Sales Boy", "Manager", "Admin"))):
    try:
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT CustomerID, CustomerName, Mobile
                FROM Customers ORDER BY CustomerName
            """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load customers.")

@app.get("/cash-drawer")
def cash_drawer(user=Depends(roles("Sales Boy", "Manager", "Admin"))):
    try:
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT TOP 1 CashDrawerID, OpeningCash, OpenDateTime, Status
                FROM CashDrawers
                WHERE UserID = :user_id AND Status = 'Open'
                ORDER BY CashDrawerID DESC
            """), {"user_id": user["UserID"]}).mappings().first()
        return dict(row) if row else {"Status": "Closed"}
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to check cash drawer.")

@app.post("/sales")
def create_sale(
    request: SaleRequest,
    user=Depends(roles("Sales Boy", "Manager", "Admin"))
):
    if request.PaymentMode not in ("Cash", "UPI", "Card"):
        raise HTTPException(status_code=400, detail="Invalid payment mode.")
    if not request.Items:
        raise HTTPException(status_code=400, detail="At least one item is required.")

    try:
        with engine.begin() as c:
            if request.PaymentMode == "Cash":
                drawer = c.execute(text("""
                    SELECT CashDrawerID FROM CashDrawers
                    WHERE UserID = :user_id AND Status = 'Open'
                """), {"user_id": user["UserID"]}).scalar()
                if not drawer:
                    raise HTTPException(status_code=400, detail="Open the cash drawer first.")

            items = []
            for requested in request.Items:
                p = c.execute(text("""
                    SELECT ProductID, ProductName, SellingPrice, PurchasePrice,
                           GSTPercent, Stock
                    FROM Products WITH (UPDLOCK, ROWLOCK)
                    WHERE ProductID = :product_id
                """), {"product_id": requested.ProductID}).mappings().first()

                if not p:
                    raise HTTPException(status_code=404, detail="Product not found.")

                qty = float(requested.Quantity)
                stock = float(p["Stock"] or 0)
                if stock < qty:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for {p['ProductName']}."
                    )

                price = float(p["SellingPrice"] or 0)
                purchase = float(p["PurchasePrice"] or 0)
                gst = float(p["GSTPercent"] or 0)
                amount = qty * price
                profit = qty * (price - purchase)

                items.append({
                    "ProductID": int(p["ProductID"]),
                    "ProductName": str(p["ProductName"]),
                    "Quantity": qty,
                    "Price": price,
                    "PurchasePrice": purchase,
                    "GSTPercent": gst,
                    "Amount": amount,
                    "ProfitAmount": profit,
                })

            subtotal = sum(x["Amount"] for x in items)
            gst_total = sum(x["Amount"] * x["GSTPercent"] / 100 for x in items)
            total = subtotal + gst_total

            if request.AmountPaid < total:
                raise HTTPException(status_code=400, detail="Amount paid is less than total.")

            balance = request.AmountPaid - total

            result = c.execute(text("""
                INSERT INTO Sales
                (CustomerName, SubTotal, GSTAmount, GrandTotal, PaymentMode,
                 AmountPaid, BalanceAmount, UserID)
                OUTPUT INSERTED.SaleID
                VALUES
                (:customer, :subtotal, :gst, :total, :mode,
                 :paid, :balance, :user_id)
            """), {
                "customer": request.CustomerName.strip() or "Walk-in Customer",
                "subtotal": subtotal, "gst": gst_total, "total": total,
                "mode": request.PaymentMode, "paid": request.AmountPaid,
                "balance": balance, "user_id": user["UserID"]
            })
            sale_id = int(result.scalar_one())

            for x in items:
                updated = c.execute(text("""
                    UPDATE Products
                    SET Stock = Stock - :qty
                    WHERE ProductID = :product_id AND Stock >= :qty
                """), {"qty": x["Quantity"], "product_id": x["ProductID"]})

                if updated.rowcount == 0:
                    raise HTTPException(status_code=400, detail="Insufficient stock.")

                c.execute(text("""
                    INSERT INTO SaleItems
                    (SaleID, ProductID, Quantity, Price, GSTPercent, Amount,
                     PurchasePrice, ProfitAmount)
                    VALUES
                    (:sale_id, :product_id, :qty, :price, :gst, :amount,
                     :purchase, :profit)
                """), {
                    "sale_id": sale_id, "product_id": x["ProductID"],
                    "qty": x["Quantity"], "price": x["Price"],
                    "gst": x["GSTPercent"], "amount": x["Amount"],
                    "purchase": x["PurchasePrice"], "profit": x["ProfitAmount"]
                })

        return {
            "success": True,
            "SaleID": sale_id,
            "Subtotal": round(subtotal, 2),
            "GSTAmount": round(gst_total, 2),
            "GrandTotal": round(total, 2),
            "AmountPaid": round(request.AmountPaid, 2),
            "BalanceAmount": round(balance, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/my")
def my_sales(user=Depends(roles("Sales Boy", "Manager", "Admin"))):
    try:
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT SaleID, SaleDate, CustomerName, PaymentMode, GrandTotal
                FROM Sales
                WHERE UserID = :user_id
                ORDER BY SaleDate DESC
            """), {"user_id": user["UserID"]}).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load sales.")

@app.get("/reports/profit")
def profit_report(user=Depends(roles("Manager", "Admin"))):
    try:
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT s.SaleID, s.SaleDate, s.CustomerName,
                       COALESCE(u.FullName, 'Unknown') AS Salesperson,
                       s.PaymentMode,
                       SUM(si.Quantity * si.Price) AS SalesValue,
                       SUM(si.Quantity * si.PurchasePrice) AS PurchaseCost,
                       SUM(si.ProfitAmount) AS GrossProfit
                FROM Sales s
                INNER JOIN SaleItems si ON si.SaleID = s.SaleID
                LEFT JOIN Users u ON u.UserID = s.UserID
                GROUP BY s.SaleID, s.SaleDate, s.CustomerName,
                         u.FullName, s.PaymentMode
                ORDER BY s.SaleDate DESC
            """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load profit report.")
