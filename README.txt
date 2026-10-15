POS Mobile API - Stage 1

1. Copy main.py to C:\POSApp\api\main.py
2. Create C:\POSApp\api\__init__.py
3. Copy mobile_api_requirements.txt to C:\POSApp\mobile_api_requirements.txt
4. In PowerShell:
   cd C:\POSApp
   python -m pip install -r mobile_api_requirements.txt
5. Change JWT_SECRET in api\main.py.
6. Start:
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
7. Test on the PC:
   http://127.0.0.1:8000/docs

The API uses the existing POSDB through database.database.engine.
PurchasePrice is never sent to Sales Boy clients.
Sales save Price, PurchasePrice and ProfitAmount in SaleItems.

Customer mobile checkout:
POST /customer/checkout requires the customer bearer token returned by
POST /customer/login. Send JSON with "items" (each item has "product_id" and
"quantity"), and optionally "payment_mode" ("Cash", "UPI", or "Card"),
"delivery_address", and "notes". Product prices and GST are read from the
database; client-supplied prices are not accepted. The endpoint creates a
Pending order and its line items in CustomerOrders and CustomerOrderItems.
It checks current stock but does not reserve stock, deduct stock, or collect
payment. The order tables are created automatically on the first checkout.

Managers and admins can review these orders in Streamlit under Customer Orders.
Completing a pending order requires staff to confirm that the full amount was
received. It creates a regular sale attributed to the signed-in staff member and
deducts stock using the earliest-expiring unexpired batches in one transaction.
Cash orders require that staff member to have an open cash drawer. Rejected and
completed orders remain available in the order history.

Product images are stored in the app server's persistent product-images directory.
Set PRODUCT_IMAGE_DIR to a persistent shared directory when Streamlit and the API
run as separate processes or containers. The product editor supports JPEG, PNG,
and WebP images up to 5 MB; the customer catalog returns ImageURL and serves each
image from /customer/products/{product_id}/image. Back up this directory with the
database.
