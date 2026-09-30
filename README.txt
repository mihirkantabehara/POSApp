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
