from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import text

from database.database import engine


CENT = Decimal("0.01")


def ensure_customer_order_tables(connection):
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS "CustomerOrders" (
            "OrderID" BIGSERIAL PRIMARY KEY,
            "CustomerID" INTEGER NOT NULL REFERENCES "Customers" ("CustomerID"),
            "OrderDate" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "Status" TEXT NOT NULL DEFAULT 'Pending'
                CHECK ("Status" IN ('Pending', 'Accepted', 'Rejected', 'Completed')),
            "PaymentMode" TEXT NOT NULL
                CHECK ("PaymentMode" IN ('Cash', 'UPI', 'Card')),
            "SubTotal" NUMERIC(18, 2) NOT NULL,
            "GSTAmount" NUMERIC(18, 2) NOT NULL,
            "GrandTotal" NUMERIC(18, 2) NOT NULL,
            "DeliveryAddress" TEXT,
            "Notes" TEXT
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS "CustomerOrderItems" (
            "OrderItemID" BIGSERIAL PRIMARY KEY,
            "OrderID" BIGINT NOT NULL
                REFERENCES "CustomerOrders" ("OrderID") ON DELETE CASCADE,
            "ProductID" INTEGER NOT NULL,
            "ProductName" TEXT NOT NULL,
            "Quantity" NUMERIC(18, 3) NOT NULL CHECK ("Quantity" > 0),
            "Price" NUMERIC(18, 2) NOT NULL,
            "GSTPercent" NUMERIC(7, 3) NOT NULL,
            "Amount" NUMERIC(18, 2) NOT NULL,
            "GSTAmount" NUMERIC(18, 2) NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE INDEX IF NOT EXISTS "IX_CustomerOrders_CustomerID_OrderDate"
        ON "CustomerOrders" ("CustomerID", "OrderDate" DESC)
    """))
    connection.execute(text("""
        ALTER TABLE "CustomerOrders"
        ADD COLUMN IF NOT EXISTS "SaleID" INTEGER
    """))
    connection.execute(text("""
        ALTER TABLE "CustomerOrders"
        ADD COLUMN IF NOT EXISTS "CompletedAt" TIMESTAMPTZ
    """))
    connection.execute(text("""
        ALTER TABLE "CustomerOrders"
        ADD COLUMN IF NOT EXISTS "CompletedByUserID" INTEGER
    """))


def complete_customer_order(
    order_id: int,
    user_id: int,
    payment_mode: str,
    amount_received: Decimal,
    product_overrides: dict[int, int] | None = None,
) -> int:
    """Convert one pending mobile order into a normal sale, atomically."""
    amount_received = Decimal(str(amount_received)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    if payment_mode not in ("Cash", "UPI", "Card"):
        raise ValueError("Select a valid payment mode.")

    with engine.begin() as connection:
        ensure_customer_order_tables(connection)

        order = connection.execute(
            text("""
                SELECT o."OrderID", o."CustomerID", o."Status",
                       o."SubTotal", o."GSTAmount", o."GrandTotal",
                       c."CustomerName"
                FROM "CustomerOrders" AS o
                JOIN "Customers" AS c ON c."CustomerID" = o."CustomerID"
                WHERE o."OrderID" = :order_id
                FOR UPDATE OF o
            """),
            {"order_id": int(order_id)},
        ).mappings().first()
        if not order:
            raise ValueError("Order not found.")
        if order["Status"] != "Pending":
            raise ValueError(f"Order is already {str(order['Status']).lower()}.")

        grand_total = Decimal(str(order["GrandTotal"])).quantize(CENT)
        if amount_received < grand_total:
            raise ValueError(
                f"Confirm at least ₹{grand_total:,.2f} received before completing."
            )

        if payment_mode == "Cash":
            cash_drawer = connection.execute(
                text("""
                    SELECT "CashDrawerID"
                    FROM "CashDrawers"
                    WHERE "UserID" = :user_id AND "Status" = 'Open'
                    ORDER BY "CashDrawerID" DESC
                    LIMIT 1
                    FOR UPDATE
                """),
                {"user_id": int(user_id)},
            ).scalar()
            if not cash_drawer:
                raise ValueError(
                    "Open your cash drawer before completing a cash order."
                )

        items = connection.execute(
            text("""
                SELECT "OrderItemID", "ProductID", "ProductName", "Quantity",
                       "Price", "GSTPercent", "Amount", "GSTAmount"
                FROM "CustomerOrderItems"
                WHERE "OrderID" = :order_id
                ORDER BY "ProductID", "OrderItemID"
            """),
            {"order_id": int(order_id)},
        ).mappings().all()
        if not items:
            raise ValueError("Order has no items.")

        product_overrides = {
            int(original_id): int(replacement_id)
            for original_id, replacement_id in (product_overrides or {}).items()
        }
        order_product_ids = {int(item["ProductID"]) for item in items}
        if not set(product_overrides).issubset(order_product_ids):
            raise ValueError("Replacement mapping contains an item not in this order.")
        resolved_product_ids = {
            product_id: product_overrides.get(product_id, product_id)
            for product_id in order_product_ids
        }

        quantities_by_product = {}
        for item in items:
            original_product_id = int(item["ProductID"])
            product_id = resolved_product_ids[original_product_id]
            quantities_by_product[product_id] = (
                quantities_by_product.get(product_id, Decimal("0"))
                + Decimal(str(item["Quantity"]))
            )

        for product_id, required_quantity in sorted(quantities_by_product.items()):
            product = connection.execute(
                text("""
                    SELECT "ProductID", "Stock"
                    FROM "Products"
                    WHERE "ProductID" = :product_id
                    FOR UPDATE
                """),
                {"product_id": product_id},
            ).mappings().first()
            if not product:
                raise ValueError(f"Product {product_id} no longer exists.")
            if Decimal(str(product["Stock"] or 0)) < required_quantity:
                product_name = next(
                    str(item["ProductName"])
                    for item in items
                    if resolved_product_ids[int(item["ProductID"])] == product_id
                )
                raise ValueError(f"Insufficient stock for {product_name}.")

        sale_id = connection.execute(
            text("""
                INSERT INTO "Sales"
                    ("CustomerName", "SubTotal", "GSTAmount", "GrandTotal",
                     "PaymentMode", "AmountPaid", "BalanceAmount", "UserID")
                VALUES
                    (:customer_name, :subtotal, :gst_amount, :grand_total,
                     :payment_mode, :amount_paid, :balance, :user_id)
                RETURNING "SaleID"
            """),
            {
                "customer_name": str(order["CustomerName"]),
                "subtotal": order["SubTotal"],
                "gst_amount": order["GSTAmount"],
                "grand_total": grand_total,
                "payment_mode": payment_mode,
                "amount_paid": amount_received,
                "balance": amount_received - grand_total,
                "user_id": int(user_id),
            },
        ).scalar_one()

        for item in items:
            product_id = resolved_product_ids[int(item["ProductID"])]
            remaining = Decimal(str(item["Quantity"]))
            price = Decimal(str(item["Price"]))
            gst_percent = Decimal(str(item["GSTPercent"]))

            batches = connection.execute(
                text("""
                    SELECT "BatchID", "BatchNo", "ExpiryDate", "PurchasePrice",
                           "Quantity"
                    FROM "ProductBatches"
                    WHERE "ProductID" = :product_id
                      AND "IsActive" = TRUE
                      AND "Quantity" > 0
                      AND "ExpiryDate" >= CURRENT_DATE
                    ORDER BY "ExpiryDate" ASC, "BatchID" ASC
                    FOR UPDATE
                """),
                {"product_id": product_id},
            ).mappings().all()

            for batch in batches:
                if remaining <= 0:
                    break

                available = Decimal(str(batch["Quantity"]))
                allocated = min(remaining, available)
                if allocated <= 0:
                    continue

                updated_batch = connection.execute(
                    text("""
                        UPDATE "ProductBatches"
                        SET "Quantity" = "Quantity" - :quantity
                        WHERE "BatchID" = :batch_id
                          AND "Quantity" >= :quantity
                          AND "IsActive" = TRUE
                          AND "ExpiryDate" >= CURRENT_DATE
                    """),
                    {
                        "quantity": allocated,
                        "batch_id": int(batch["BatchID"]),
                    },
                )
                if updated_batch.rowcount != 1:
                    raise ValueError(
                        f"Batch {batch['BatchNo']} changed during order completion."
                    )

                purchase_price = Decimal(str(batch["PurchasePrice"] or 0))
                amount = (allocated * price).quantize(CENT, rounding=ROUND_HALF_UP)
                profit = (
                    allocated * (price - purchase_price)
                ).quantize(CENT, rounding=ROUND_HALF_UP)
                connection.execute(
                    text("""
                        INSERT INTO "SaleItems"
                            ("SaleID", "ProductID", "BatchID", "Quantity", "Price",
                             "GSTPercent", "Amount", "PurchasePrice", "ProfitAmount")
                        VALUES
                            (:sale_id, :product_id, :batch_id, :quantity, :price,
                             :gst_percent, :amount, :purchase_price, :profit_amount)
                    """),
                    {
                        "sale_id": int(sale_id),
                        "product_id": product_id,
                        "batch_id": int(batch["BatchID"]),
                        "quantity": allocated,
                        "price": price,
                        "gst_percent": gst_percent,
                        "amount": amount,
                        "purchase_price": purchase_price,
                        "profit_amount": profit,
                    },
                )
                remaining -= allocated

            if remaining > Decimal("0.000001"):
                raise ValueError(
                    f"Not enough unexpired batch stock for {item['ProductName']}."
                )

        for product_id, quantity in quantities_by_product.items():
            updated_product = connection.execute(
                text("""
                    UPDATE "Products"
                    SET "Stock" = "Stock" - :quantity
                    WHERE "ProductID" = :product_id AND "Stock" >= :quantity
                """),
                {"quantity": quantity, "product_id": product_id},
            )
            if updated_product.rowcount != 1:
                raise ValueError("Product stock summary changed during completion.")

        updated_order = connection.execute(
            text("""
                UPDATE "CustomerOrders"
                SET "Status" = 'Completed',
                    "PaymentMode" = :payment_mode,
                    "SaleID" = :sale_id,
                    "CompletedAt" = CURRENT_TIMESTAMP,
                    "CompletedByUserID" = :user_id
                WHERE "OrderID" = :order_id AND "Status" = 'Pending'
            """),
            {
                "payment_mode": payment_mode,
                "sale_id": int(sale_id),
                "user_id": int(user_id),
                "order_id": int(order_id),
            },
        )
        if updated_order.rowcount != 1:
            raise ValueError("Order status changed before completion.")

        return int(sale_id)


def reject_customer_order(order_id: int) -> None:
    with engine.begin() as connection:
        ensure_customer_order_tables(connection)
        result = connection.execute(
            text("""
                UPDATE "CustomerOrders"
                SET "Status" = 'Rejected'
                WHERE "OrderID" = :order_id AND "Status" = 'Pending'
            """),
            {"order_id": int(order_id)},
        )
        if result.rowcount != 1:
            raise ValueError("Pending order not found or already processed.")
