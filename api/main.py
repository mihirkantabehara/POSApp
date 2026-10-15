from datetime import datetime, timedelta

from decimal import Decimal, ROUND_HALF_UP

from typing import Literal



import hashlib



import hmac



import jwt



import time



from fastapi import FastAPI, HTTPException, Depends, Request

from fastapi.responses import FileResponse



from fastapi.middleware.cors import CORSMiddleware



from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer



from sqlalchemy import text





from database.database import engine



from logging_config import get_logger

from product_images import (

    get_product_image_path,

    product_image_media_type,

)

from customer_orders import (
    complete_customer_order,
    ensure_customer_order_tables,
    reject_customer_order,
)



import os



import re







from pwdlib import PasswordHash



from pydantic import BaseModel, Field







JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")



JWT_ALGORITHM = "HS256"



TOKEN_HOURS = 12







app = FastAPI(title="POS Mobile API", version="1.0.0")

logger = get_logger(__name__)





@app.middleware("http")

async def log_api_request(request: Request, call_next):

    started_at = time.perf_counter()

    try:

        response = await call_next(request)

    except Exception:

        logger.exception(

            "request_failed method=%s path=%s",

            request.method,

            request.url.path,

        )

        raise



    log = logger.warning if response.status_code >= 400 else logger.info

    log(

        "request_completed method=%s path=%s status_code=%s duration_ms=%.2f",

        request.method,

        request.url.path,

        response.status_code,

        (time.perf_counter() - started_at) * 1000,

    )

    return response







app.add_middleware(



    CORSMiddleware,



    allow_origins=["*"],



    allow_credentials=True,



    allow_methods=["*"],



    allow_headers=["*"],



)







security = HTTPBearer()

customer_security = HTTPBearer(auto_error=False)

customer_password_hasher = PasswordHash.recommended()







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

        logger.warning("staff_auth_rejected")

        raise HTTPException(status_code=401, detail="Invalid or expired token.")







def roles(*allowed):



    def check(user=Depends(current_user)):

        if user["Role"] not in allowed:

            logger.warning(

                "access_denied user_id=%s role=%s allowed_roles=%s",

                user["UserID"],

                user["Role"],

                ",".join(allowed),

            )

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





class CustomerCheckoutItemRequest(BaseModel):

    product_id: int = Field(gt=0)

    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)





class CustomerCheckoutRequest(BaseModel):

    items: list[CustomerCheckoutItemRequest] = Field(min_length=1, max_length=100)

    payment_mode: Literal["Cash", "UPI", "Card"] = "Cash"

    delivery_address: str | None = Field(default=None, max_length=1000)

    notes: str | None = Field(default=None, max_length=1000)


class CustomerOrderCompletionRequest(BaseModel):

    payment_mode: Literal["Cash", "UPI", "Card"]

    amount_received: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    product_overrides: dict[int, int] = Field(default_factory=dict)





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

        logger.exception("health_check_failed")

        raise HTTPException(status_code=503, detail="Database connection failed.")







@app.post("/login")



def login(request: LoginRequest):



    try:



        with engine.connect() as c:



            row = c.execute(



                text("""



                    SELECT "UserID", "Username", "PasswordHash",

                           "FullName", "Role", "IsActive"

                    FROM "Users"

                    WHERE "Username" = :username



                """),



                {"username": request.username.strip()}



            ).mappings().first()







        if not row or not bool(row["IsActive"]):

            logger.warning("staff_login_rejected")

            raise HTTPException(status_code=401, detail="Invalid username or password.")







        if not hmac.compare_digest(

            hash_password(request.password), str(row["PasswordHash"])

        ):

            logger.warning("staff_login_rejected")

            raise HTTPException(status_code=401, detail="Invalid username or password.")







        user = {



            "UserID": int(row["UserID"]),



            "Username": str(row["Username"]),



            "FullName": str(row["FullName"]),



            "Role": str(row["Role"]),

        }

        logger.info(

            "staff_login_succeeded user_id=%s role=%s",

            user["UserID"],

            user["Role"],

        )

        return {"token": create_token(user), "user": user}



    except HTTPException:



        raise



    except Exception:

        logger.exception("staff_login_failed")

        raise HTTPException(status_code=500, detail="Unable to access user database.")









class CustomerRegisterRequest(BaseModel):

    customer_name: str = Field(min_length=2, max_length=150)

    mobile: str = Field(min_length=10, max_length=20)

    password: str = Field(min_length=8, max_length=128)





class CustomerLoginRequest(BaseModel):

    mobile: str = Field(min_length=10, max_length=20)

    password: str = Field(min_length=1, max_length=128)





def normalize_customer_mobile(value: str) -> str:

    """Normalize Indian mobile numbers to 10 digits."""

    digits = re.sub(r"\D", "", value or "")

    if len(digits) == 12 and digits.startswith("91"):

        digits = digits[2:]

    elif len(digits) == 11 and digits.startswith("0"):

        digits = digits[1:]



    if len(digits) != 10 or digits[0] not in "6789":

        raise HTTPException(

            status_code=400,

            detail="Enter a valid 10-digit Indian mobile number.",

        )

    return digits





def create_customer_token(customer_id: int, mobile: str) -> str:

    """Customer tokens deliberately do not contain staff UserID/Role claims."""

    payload = {

        "customer_id": customer_id,

        "mobile": mobile,

        "token_type": "customer",

        "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS),

    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)





@app.post("/customer/register")

def customer_register(request: CustomerRegisterRequest):

    mobile = normalize_customer_mobile(request.mobile)

    name = request.customer_name.strip()

    if len(name) < 2:

        raise HTTPException(status_code=400, detail="Enter the customer's name.")



    try:

        with engine.begin() as connection:

            # Never allow self-claiming a pre-existing shop customer's account.

            existing_customer = connection.execute(

                text("""

                    SELECT "CustomerID"

                    FROM "Customers"

                    WHERE regexp_replace(COALESCE("Mobile"::text, ''),

                                         '[^0-9]', '', 'g')

                          IN (:mobile, :mobile_with_country, :mobile_with_zero)

                    LIMIT 1

                """),

                {

                    "mobile": mobile,

                    "mobile_with_country": "91" + mobile,

                    "mobile_with_zero": "0" + mobile,

                },

            ).scalar()



            if existing_customer is not None:

                raise HTTPException(

                    status_code=409,

                    detail=(

                        "This mobile number already exists in the shop's customer "

                        "records. Please contact the shop to activate online access."

                    ),

                )



            # The customer row and credentials are created atomically.

            customer_id = connection.execute(

                text("""

                    INSERT INTO "Customers" ("CustomerName", "Mobile")

                    VALUES (:name, :mobile)

                    RETURNING "CustomerID"

                """),

                {"name": name, "mobile": mobile},

            ).scalar_one()



            connection.execute(

                text("""

                    INSERT INTO "CustomerCredentials"

                        ("CustomerID", "MobileLogin", "PasswordHash")

                    VALUES (:customer_id, :mobile, :password_hash)

                """),

                {

                    "customer_id": customer_id,

                    "mobile": mobile,

                    "password_hash": customer_password_hasher.hash(request.password),

                },

            )



        logger.info("customer_registration_succeeded customer_id=%s", customer_id)

        return {

            "success": True,

            "message": "Customer account created. You can now log in.",

            "customer_id": int(customer_id),

        }

    except HTTPException:

        raise

    except Exception:

        logger.exception("customer_registration_failed")

        # Keep database details out of the public response.

        raise HTTPException(

            status_code=500,

            detail="Unable to create customer account. Please try again.",

        )





@app.post("/customer/login")

def customer_login(request: CustomerLoginRequest):

    mobile = normalize_customer_mobile(request.mobile)

    try:

        with engine.connect() as connection:

            row = connection.execute(

                text("""

                    SELECT cc."CustomerID",

                           cc."MobileLogin",

                           cc."PasswordHash",

                           cc."IsActive",

                           c."CustomerName"

                    FROM "CustomerCredentials" AS cc

                    JOIN "Customers" AS c

                      ON c."CustomerID" = cc."CustomerID"

                    WHERE cc."MobileLogin" = :mobile

                    LIMIT 1

                """),

                {"mobile": mobile},

            ).mappings().first()



        if (

            not row

            or not bool(row["IsActive"])

            or not customer_password_hasher.verify(

                request.password, str(row["PasswordHash"])

            )

        ):

            logger.warning("customer_login_rejected")

            raise HTTPException(

                status_code=401,

                detail="Invalid mobile number or password.",

            )



        token = create_customer_token(

            int(row["CustomerID"]), str(row["MobileLogin"])

        )

        logger.info(

            "customer_login_succeeded customer_id=%s",

            row["CustomerID"],

        )

        return {

            "access_token": token,

            "token_type": "bearer",

            "customer": {

                "customer_id": int(row["CustomerID"]),

                "customer_name": str(row["CustomerName"]),

                "mobile": str(row["MobileLogin"]),

            },

        }

    except HTTPException:

        raise

    except Exception:

        logger.exception("customer_login_failed")

        raise HTTPException(

            status_code=500,

            detail="Unable to log in. Please try again.",

        )





@app.get("/customer/me")

def customer_me(

    credentials: HTTPAuthorizationCredentials | None = Depends(customer_security),

):

    """Return the signed-in customer; staff tokens are not accepted here."""

    if credentials is None:

        logger.warning("customer_auth_rejected reason=missing_bearer_token")

        raise HTTPException(status_code=401, detail="Customer login required.")



    try:

        payload = jwt.decode(

            credentials.credentials,

            JWT_SECRET,

            algorithms=[JWT_ALGORITHM],

        )

    except jwt.ExpiredSignatureError:

        logger.warning("customer_auth_rejected reason=expired_token")

        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    except jwt.InvalidTokenError:

        logger.warning("customer_auth_rejected reason=invalid_token")

        raise HTTPException(status_code=401, detail="Invalid or expired token.")



    if payload.get("token_type") != "customer" or "customer_id" not in payload:

        logger.warning("customer_auth_rejected reason=wrong_token_type")

        raise HTTPException(status_code=401, detail="Customer login required.")



    customer_id = int(payload["customer_id"])

    try:

        with engine.connect() as connection:

            row = connection.execute(

                text("""

                    SELECT c."CustomerID", c."CustomerName", c."Mobile",

                           cc."IsActive"

                    FROM "CustomerCredentials" AS cc

                    JOIN "Customers" AS c

                      ON c."CustomerID" = cc."CustomerID"

                    WHERE cc."CustomerID" = :customer_id

                    LIMIT 1

                """),

                {"customer_id": customer_id},

            ).mappings().first()

    except Exception:

        logger.exception("customer_profile_load_failed customer_id=%s", customer_id)

        raise HTTPException(

            status_code=500,

            detail="Unable to load customer profile.",

        )



    if not row or not bool(row["IsActive"]):

        logger.warning(

            "customer_auth_rejected customer_id=%s reason=inactive",

            customer_id,

        )

        raise HTTPException(status_code=401, detail="Customer account is inactive.")



    return {

        "customer_id": int(row["CustomerID"]),

        "customer_name": str(row["CustomerName"]),

        "mobile": str(row["Mobile"] or ""),

    }



@app.get("/customer/products")

def customer_products(

    credentials: HTTPAuthorizationCredentials | None = Depends(customer_security),

):

    """Return the storefront catalog for customer-facing browsing.



    The route is intentionally public, but a valid customer token is accepted for

    authenticated customers as well.

    """

    if credentials is not None:

        try:

            payload = jwt.decode(

                credentials.credentials,

                JWT_SECRET,

                algorithms=[JWT_ALGORITHM],

            )

        except jwt.ExpiredSignatureError:

            logger.warning("customer_catalog_auth_rejected reason=expired_token")

            raise HTTPException(status_code=401, detail="Invalid or expired token.")

        except jwt.InvalidTokenError:

            logger.warning("customer_catalog_auth_rejected reason=invalid_token")

            raise HTTPException(status_code=401, detail="Invalid or expired token.")



        if payload.get("token_type") != "customer" or "customer_id" not in payload:

            logger.warning("customer_catalog_auth_rejected reason=wrong_token_type")

            raise HTTPException(status_code=401, detail="Customer login required.")



    try:

        with engine.connect() as c:

            rows = c.execute(text("""



                SELECT p."ProductID",
                       p."ProductName",
                       p."Barcode",
                       p."CategoryID",
                       c."CategoryName" AS "CategoryName",
                       p."SubcategoryID",
                       sc."SubcategoryName" AS "SubcategoryName",
                       COALESCE(batch."SellingPrice", p."SellingPrice") AS "SellingPrice",
                       batch."MRP" AS "MRP",
                       p."Stock",
                       p."GSTPercent"
                FROM "Products" AS p
                LEFT JOIN "ProductCategories" AS c
                  ON c."CategoryID" = p."CategoryID"
                LEFT JOIN "ProductSubcategories" AS sc
                  ON sc."SubcategoryID" = p."SubcategoryID"
                LEFT JOIN LATERAL (
                    SELECT
                        pb."MRP",
                        pb."SellingPrice"
                    FROM "ProductBatches" AS pb
                    WHERE pb."ProductID" = p."ProductID"
                      AND pb."IsActive" IS TRUE
                      AND pb."Quantity" > 0
                    ORDER BY pb."ExpiryDate" ASC NULLS LAST,
                             pb."BatchID" ASC
                    LIMIT 1
                ) AS batch ON TRUE
                ORDER BY p."ProductName"



            """)).mappings().all()



        products = []

        for row in rows:

            product = dict(row)

            image_path = get_product_image_path(int(product["ProductID"]))

            product["ImageURL"] = (

                f"/customer/products/{product['ProductID']}/image"

                if image_path is not None

                else None

            )

            products.append(product)

        return products



    except Exception:

        logger.exception("customer_products_load_failed")

        raise HTTPException(

            status_code=500,

            detail="Unable to load customer catalog.",

        )





@app.get("/customer/products/{product_id}/image")

def customer_product_image(product_id: int):

    image_path = get_product_image_path(product_id)

    if image_path is None:

        raise HTTPException(status_code=404, detail="Product image not found.")



    try:

        media_type = product_image_media_type(image_path)

        return FileResponse(image_path, media_type=media_type)

    except (OSError, ValueError):

        logger.exception("customer_product_image_load_failed product_id=%s", product_id)

        raise HTTPException(

            status_code=500,

            detail="Unable to load product image.",

        )





@app.post("/customer/checkout", status_code=201)

def customer_checkout(

    request: CustomerCheckoutRequest,

    credentials: HTTPAuthorizationCredentials | None = Depends(customer_security),

):

    """Save a pending customer order without charging payment or changing stock."""

    if credentials is None:

        logger.warning("customer_checkout_rejected reason=missing_bearer_token")

        raise HTTPException(status_code=401, detail="Customer login required.")



    try:

        payload = jwt.decode(

            credentials.credentials,

            JWT_SECRET,

            algorithms=[JWT_ALGORITHM],

        )

    except jwt.InvalidTokenError:

        logger.warning("customer_checkout_rejected reason=invalid_token")

        raise HTTPException(status_code=401, detail="Invalid or expired token.")



    try:

        customer_id = int(payload["customer_id"])

    except (KeyError, TypeError, ValueError):

        customer_id = 0



    if payload.get("token_type") != "customer" or customer_id <= 0:

        logger.warning("customer_checkout_rejected reason=wrong_token_type")

        raise HTTPException(status_code=401, detail="Customer login required.")



    cent = Decimal("0.01")

    quantities: dict[int, Decimal] = {}

    for item in request.items:

        quantities[item.product_id] = (

            quantities.get(item.product_id, Decimal("0")) + item.quantity

        )



    try:

        with engine.begin() as connection:

            ensure_customer_order_tables(connection)



            customer = connection.execute(

                text("""

                    SELECT cc."IsActive"

                    FROM "CustomerCredentials" AS cc

                    WHERE cc."CustomerID" = :customer_id

                    FOR UPDATE

                """),

                {"customer_id": customer_id},

            ).mappings().first()



            if not customer or not bool(customer["IsActive"]):

                logger.warning(

                    "customer_checkout_rejected customer_id=%s reason=inactive",

                    customer_id,

                )

                raise HTTPException(

                    status_code=401,

                    detail="Customer account is inactive.",

                )



            order_items = []

            for product_id, quantity in quantities.items():

                product = connection.execute(

                    text("""

                        SELECT "ProductID", "ProductName", "SellingPrice",

                               "Stock", "GSTPercent"

                        FROM "Products"

                        WHERE "ProductID" = :product_id

                        FOR UPDATE

                    """),

                    {"product_id": product_id},

                ).mappings().first()



                if not product:

                    raise HTTPException(

                        status_code=404,

                        detail=f"Product {product_id} was not found.",

                    )



                stock = Decimal(str(product["Stock"] or 0))

                if quantity > stock:

                    raise HTTPException(

                        status_code=400,

                        detail=f"Insufficient stock for {product['ProductName']}.",

                    )



                price = Decimal(str(product["SellingPrice"] or 0))

                gst_percent = Decimal(str(product["GSTPercent"] or 0))

                amount = (quantity * price).quantize(cent, rounding=ROUND_HALF_UP)

                gst_amount = (

                    amount * gst_percent / Decimal("100")

                ).quantize(cent, rounding=ROUND_HALF_UP)

                order_items.append({

                    "product_id": int(product["ProductID"]),

                    "product_name": str(product["ProductName"]),

                    "quantity": quantity,

                    "price": price,

                    "gst_percent": gst_percent,

                    "amount": amount,

                    "gst_amount": gst_amount,

                })



            subtotal = sum(

                (item["amount"] for item in order_items), Decimal("0")

            ).quantize(cent)

            gst_total = sum(

                (item["gst_amount"] for item in order_items), Decimal("0")

            ).quantize(cent)

            grand_total = subtotal + gst_total



            order_id = connection.execute(

                text("""

                    INSERT INTO "CustomerOrders"

                        ("CustomerID", "PaymentMode", "SubTotal", "GSTAmount",

                         "GrandTotal", "DeliveryAddress", "Notes")

                    VALUES

                        (:customer_id, :payment_mode, :subtotal, :gst_amount,

                         :grand_total, :delivery_address, :notes)

                    RETURNING "OrderID"

                """),

                {

                    "customer_id": customer_id,

                    "payment_mode": request.payment_mode,

                    "subtotal": subtotal,

                    "gst_amount": gst_total,

                    "grand_total": grand_total,

                    "delivery_address": (

                        request.delivery_address.strip()

                        if request.delivery_address and request.delivery_address.strip()

                        else None

                    ),

                    "notes": (

                        request.notes.strip()

                        if request.notes and request.notes.strip()

                        else None

                    ),

                },

            ).scalar_one()



            for item in order_items:

                connection.execute(

                    text("""

                        INSERT INTO "CustomerOrderItems"

                            ("OrderID", "ProductID", "ProductName", "Quantity",

                             "Price", "GSTPercent", "Amount", "GSTAmount")

                        VALUES

                            (:order_id, :product_id, :product_name, :quantity,

                             :price, :gst_percent, :amount, :gst_amount)

                    """),

                    {"order_id": order_id, **item},

                )



        logger.info(

            "customer_checkout_succeeded customer_id=%s order_id=%s",

            customer_id,

            order_id,

        )

        return {

            "success": True,

            "order_id": int(order_id),

            "status": "Pending",

            "payment_mode": request.payment_mode,

            "subtotal": float(subtotal),

            "gst_amount": float(gst_total),

            "grand_total": float(grand_total),

            "message": (

                "Order submitted for shop confirmation. Payment has not been collected."

            ),

        }

    except HTTPException:

        raise

    except Exception:

        logger.exception(

            "customer_checkout_failed customer_id=%s",

            customer_id,

        )

        raise HTTPException(

            status_code=500,

            detail="Unable to submit checkout. Please try again.",

        )





@app.get("/me")



def me(user=Depends(current_user)):



    return user







@app.get("/products")



def products(user=Depends(roles("Sales Boy", "Manager", "Admin"))):



    try:



        with engine.connect() as c:



            rows = c.execute(text("""



                SELECT "ProductID", "ProductName", "Barcode",

                       "SellingPrice", "Stock", "GSTPercent"

                FROM "Products"

                ORDER BY "ProductName"



            """)).mappings().all()



        return [dict(r) for r in rows]



    except Exception:

        logger.exception("products_load_failed")

        raise HTTPException(status_code=500, detail="Unable to load products.")







@app.get("/customer/orders")
def staff_customer_orders(
    status: str = "All",
    user=Depends(roles("Sales Boy", "Manager", "Admin")),
):
    """List customer checkout orders for staff POS clients."""
    allowed_statuses = {"All", "Pending", "Accepted", "Completed", "Rejected"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid order status filter.")

    try:
        with engine.begin() as connection:
            ensure_customer_order_tables(connection)
            status_clause = '' if status == "All" else 'WHERE o."Status" = :status'
            rows = connection.execute(
                text(f"""
                    SELECT o."OrderID", o."OrderDate", o."Status",
                           c."CustomerName", COALESCE(c."Mobile", '') AS "Mobile",
                           o."PaymentMode", o."SubTotal", o."GSTAmount",
                           o."GrandTotal", o."DeliveryAddress", o."Notes",
                           o."SaleID"
                    FROM "CustomerOrders" AS o
                    JOIN "Customers" AS c ON c."CustomerID" = o."CustomerID"
                    {status_clause}
                    ORDER BY CASE WHEN o."Status" = 'Pending' THEN 0 ELSE 1 END,
                             o."OrderDate" DESC, o."OrderID" DESC
                """), {"status": status} if status != "All" else {},
            ).mappings().all()
            orders = [dict(row) for row in rows]
            for order in orders:
                items = connection.execute(
                    text("""
                        SELECT "ProductID", "ProductName", "Quantity", "Price",
                               "GSTPercent", "Amount", "GSTAmount"
                        FROM "CustomerOrderItems"
                        WHERE "OrderID" = :order_id
                        ORDER BY "OrderItemID"
                    """),
                    {"order_id": int(order["OrderID"])},
                ).mappings().all()
                order["Items"] = [dict(item) for item in items]
        return orders
    except HTTPException:
        raise
    except Exception:
        logger.exception("customer_orders_api_load_failed user_id=%s", user["UserID"])
        raise HTTPException(status_code=500, detail="Unable to load customer orders.")


@app.post("/customer/orders/{order_id}/complete")
def staff_complete_customer_order(
    order_id: int,
    request: CustomerOrderCompletionRequest,
    user=Depends(roles("Sales Boy", "Manager", "Admin")),
):
    try:
        sale_id = complete_customer_order(
            order_id,
            int(user["UserID"]),
            request.payment_mode,
            request.amount_received,
            request.product_overrides,
        )
        return {"success": True, "SaleID": sale_id, "OrderID": order_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "customer_order_api_completion_failed order_id=%s user_id=%s",
            order_id,
            user["UserID"],
        )
        raise HTTPException(status_code=500, detail="Unable to complete customer order.")


@app.post("/customer/orders/{order_id}/reject")
def staff_reject_customer_order(
    order_id: int,
    user=Depends(roles("Sales Boy", "Manager", "Admin")),
):
    try:
        reject_customer_order(order_id)
        return {"success": True, "OrderID": order_id, "Status": "Rejected"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "customer_order_api_rejection_failed order_id=%s user_id=%s",
            order_id,
            user["UserID"],
        )
        raise HTTPException(status_code=500, detail="Unable to reject customer order.")


@app.get("/customers")



def customers(user=Depends(roles("Sales Boy", "Manager", "Admin"))):



    try:



        with engine.connect() as c:



            rows = c.execute(text("""



                SELECT "CustomerID", "CustomerName", "Mobile"

                FROM "Customers"

                ORDER BY "CustomerName"



            """)).mappings().all()



        return [dict(r) for r in rows]



    except Exception:

        logger.exception("customers_load_failed")

        raise HTTPException(status_code=500, detail="Unable to load customers.")







@app.get("/cash-drawer")



def cash_drawer(user=Depends(roles("Sales Boy", "Manager", "Admin"))):



    try:



        with engine.connect() as c:



            row = c.execute(text("""



                SELECT "CashDrawerID", "OpeningCash", "OpenDateTime", "Status"

                FROM "CashDrawers"

                WHERE "UserID" = :user_id AND "Status" = 'Open'

                ORDER BY "CashDrawerID" DESC

                LIMIT 1



            """), {"user_id": user["UserID"]}).mappings().first()



        return dict(row) if row else {"Status": "Closed"}



    except Exception:

        logger.exception("cash_drawer_check_failed user_id=%s", user["UserID"])

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



                    SELECT "CashDrawerID"

                    FROM "CashDrawers"

                    WHERE "UserID" = :user_id AND "Status" = 'Open'

                    LIMIT 1



                """), {"user_id": user["UserID"]}).scalar()



                if not drawer:



                    raise HTTPException(status_code=400, detail="Open the cash drawer first.")







            items = []



            for requested in request.Items:



                p = c.execute(text("""



                    SELECT "ProductID", "ProductName", "SellingPrice",

                           "PurchasePrice", "GSTPercent", "Stock"

                    FROM "Products"

                    WHERE "ProductID" = :product_id

                    FOR UPDATE



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



                INSERT INTO "Sales"

                ("CustomerName", "SubTotal", "GSTAmount", "GrandTotal",

                 "PaymentMode", "AmountPaid", "BalanceAmount", "UserID")

                VALUES

                (:customer, :subtotal, :gst, :total, :mode,

                 :paid, :balance, :user_id)

                RETURNING "SaleID"



            """), {



                "customer": request.CustomerName.strip() or "Walk-in Customer",



                "subtotal": subtotal, "gst": gst_total, "total": total,



                "mode": request.PaymentMode, "paid": request.AmountPaid,



                "balance": balance, "user_id": user["UserID"]



            })



            sale_id = int(result.scalar_one())







            for x in items:



                updated = c.execute(text("""



                    UPDATE "Products"

                    SET "Stock" = "Stock" - :qty

                    WHERE "ProductID" = :product_id AND "Stock" >= :qty



                """), {"qty": x["Quantity"], "product_id": x["ProductID"]})







                if updated.rowcount == 0:



                    raise HTTPException(status_code=400, detail="Insufficient stock.")







                c.execute(text("""



                    INSERT INTO "SaleItems"

                    ("SaleID", "ProductID", "Quantity", "Price", "GSTPercent",

                     "Amount", "PurchasePrice", "ProfitAmount")



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

        logger.exception("sale_creation_failed user_id=%s", user["UserID"])

        raise HTTPException(status_code=500, detail=str(e))







@app.get("/sales/my")



def my_sales(user=Depends(roles("Sales Boy", "Manager", "Admin"))):



    try:



        with engine.connect() as c:



            rows = c.execute(text("""



                SELECT "SaleID", "SaleDate", "CustomerName",

                       "PaymentMode", "GrandTotal"

                FROM "Sales"

                WHERE "UserID" = :user_id

                ORDER BY "SaleDate" DESC



            """), {"user_id": user["UserID"]}).mappings().all()



        return [dict(r) for r in rows]



    except Exception:

        logger.exception("sales_load_failed user_id=%s", user["UserID"])

        raise HTTPException(status_code=500, detail="Unable to load sales.")







@app.get("/reports/profit")



def profit_report(user=Depends(roles("Manager", "Admin"))):



    try:



        with engine.connect() as c:



            rows = c.execute(text("""



                SELECT s."SaleID", s."SaleDate", s."CustomerName",

                       COALESCE(u."FullName", 'Unknown') AS "Salesperson",

                       s."PaymentMode",

                       SUM(si."Quantity" * si."Price") AS "SalesValue",

                       SUM(si."Quantity" * si."PurchasePrice") AS "PurchaseCost",

                       SUM(si."ProfitAmount") AS "GrossProfit"

                FROM "Sales" AS s

                INNER JOIN "SaleItems" AS si ON si."SaleID" = s."SaleID"

                LEFT JOIN "Users" AS u ON u."UserID" = s."UserID"

                GROUP BY s."SaleID", s."SaleDate", s."CustomerName",

                         u."FullName", s."PaymentMode"

                ORDER BY s."SaleDate" DESC



            """)).mappings().all()



        return [dict(r) for r in rows]



    except Exception:

        logger.exception("profit_report_load_failed user_id=%s", user["UserID"])

        raise HTTPException(status_code=500, detail="Unable to load profit report.")
