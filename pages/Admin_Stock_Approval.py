import streamlit as st

from sqlalchemy import text

from database.database import engine





st.set_page_config(

    page_title="Admin - Stock Approval",

    page_icon="✅",

    layout="wide"

)





# =========================================================

# LOGIN CHECK

# =========================================================



if not st.session_state.get("logged_in"):



    st.error("Please login first.")



    st.stop()





user = st.session_state.get("user")



if not user:



    st.error("User information not found.")



    st.stop()





admin_user_id = user["UserID"]





# =========================================================

# PAGE HEADER

# =========================================================



st.title("✅ Admin - Stock Approval")



st.caption(

    "Review Manager stock entries before adding them to inventory."

)





# =========================================================

# GET PENDING ENTRIES

# =========================================================



def get_pending_entries():



    sql = text("""

        SELECT

            mse."ManagerStockEntryID",

            mse."EntryDate",

            mse."EnteredBy",

            u."FullName" AS ManagerName,

            mse."TotalPurchaseValue",

            mse."Status"

        FROM "ManagerStockEntry" mse

        LEFT JOIN "Users" u

            ON u."UserID" = mse."EnteredBy"

        WHERE mse."Status" = 'PENDING'

        ORDER BY mse."EntryDate" DESC

    """)



    with engine.connect() as conn:



        return conn.execute(sql).mappings().all()





# =========================================================

# GET ENTRY ITEMS

# =========================================================



def get_entry_items(entry_id):



    sql = text("""

        SELECT

            "ManagerStockEntryItemID",

            "ProductID",

            "ProductName",

            "Barcode",

            "BatchNo",

            "Quantity",

            "PurchasePrice",

            "SellingPrice",

            "ExpiryDate",

            "PurchaseValue",

            "ProductStatus"

        FROM "ManagerStockEntryItems"

        WHERE "ManagerStockEntryID" = :entry_id

        ORDER BY "ManagerStockEntryItemID"

    """)



    with engine.connect() as conn:



        return conn.execute(

            sql,

            {

                "entry_id": entry_id

            }

        ).mappings().all()





# =========================================================

# APPROVE STOCK ENTRY

# =========================================================



def approve_stock_entry(

    entry_id,

    invoice_value,

    admin_user_id

):



    try:



        # =================================================

        # ONE TRANSACTION

        # =================================================



        with engine.begin() as conn:



            # ---------------------------------------------

            # Lock Manager Stock Entry

            # ---------------------------------------------



            header_sql = text("""

                SELECT

                    "ManagerStockEntryID",

                    "TotalPurchaseValue",

                    "Status"

                FROM "ManagerStockEntry"

                WHERE "ManagerStockEntryID" = :entry_id
                        FOR UPDATE""")



            header = conn.execute(

                header_sql,

                {

                    "entry_id": entry_id

                }

            ).mappings().first()





            if not header:



                raise Exception(

                    "Stock entry not found."

                )





            if str(header["Status"]).upper() != "PENDING":



                raise Exception(

                    f"This entry is already "

                    f"{header['Status']}."

                )





            manager_total = float(

                header["TotalPurchaseValue"]

            )



            invoice_value = float(

                invoice_value

            )





            # ---------------------------------------------

            # Verify invoice

            # ---------------------------------------------



            difference = round(

                invoice_value - manager_total,

                2

            )





            if abs(difference) > 0.01:



                raise Exception(

                    "Invoice value does not match "

                    "Manager purchase total."

                )





            # ---------------------------------------------

            # Get all items

            # ---------------------------------------------



            items_sql = text("""

                SELECT

                    "ManagerStockEntryItemID",

                    "ProductID",

                    "ProductName",

                    "Barcode",

                    "BatchNo",

                    "Quantity",

                    "PurchasePrice",

                    "SellingPrice",

                    "ExpiryDate",

                    "PurchaseValue",

                    "ProductStatus"

                FROM "ManagerStockEntryItems"

                WHERE "ManagerStockEntryID" = :entry_id

                ORDER BY "ManagerStockEntryItemID"

            """)



            items = conn.execute(

                items_sql,

                {

                    "entry_id": entry_id

                }

            ).mappings().all()





            if not items:



                raise Exception(

                    "No products found in this stock entry."

                )





            # =================================================

            # PROCESS EACH PRODUCT

            # =================================================



            for item in items:



                product_id = item["ProductID"]



                product_name = (

                    item["ProductName"] or ""

                ).strip()



                barcode = (

                    item["Barcode"] or ""

                ).strip()



                quantity = float(

                    item["Quantity"]

                )



                purchase_price = float(

                    item["PurchasePrice"]

                )



                selling_price = float(

                    item["SellingPrice"]

                )





                if quantity <= 0:



                    raise Exception(

                        f"Invalid quantity for "

                        f"{product_name}."

                    )





                # =============================================

                # CHECK PRODUCT AGAIN

                #

                # This protects against duplicate products

                # if somebody created the product after the

                # Manager submitted the entry.

                # =============================================



                product = None





                # ---------------------------------------------

                # Existing ProductID

                # ---------------------------------------------



                if product_id is not None:



                    product_sql = text("""

                        SELECT

                            "ProductID",

                            "ProductName",

                            "Barcode",

                            "SellingPrice",

                            "Stock",

                            "GSTPercent",

                            "PurchasePrice"

                        FROM "Products"

                        WHERE "ProductID" = :product_id
                        FOR UPDATE""")



                    product = conn.execute(

                        product_sql,

                        {

                            "product_id": product_id

                        }

                    ).mappings().first()





                # ---------------------------------------------

                # If ProductID not found,

                # search by barcode

                # ---------------------------------------------



                if not product and barcode:



                    product_sql = text("""

                        SELECT

                            "ProductID",

                            "ProductName",

                            "Barcode",

                            "SellingPrice",

                            "Stock",

                            "GSTPercent",

                            "PurchasePrice"

                        FROM "Products"

                        WHERE BTRIM("Barcode")

                              = :barcode
                        FOR UPDATE""")



                    product = conn.execute(

                        product_sql,

                        {

                            "barcode": barcode

                        }

                    ).mappings().first()





                # ---------------------------------------------

                # If still not found,

                # search by product name

                # ---------------------------------------------



                if not product and product_name:



                    product_sql = text("""

                        SELECT

                            "ProductID",

                            "ProductName",

                            "Barcode",

                            "SellingPrice",

                            "Stock",

                            "GSTPercent",

                            "PurchasePrice"

                        FROM "Products"

                        WHERE LOWER(BTRIM("ProductName"))

                              =

                              LOWER(BTRIM(:product_name))
                        FOR UPDATE""")



                    product = conn.execute(

                        product_sql,

                        {

                            "product_name": product_name

                        }

                    ).mappings().first()





                # =================================================

                # EXISTING PRODUCT

                # =================================================



                if product:



                    product_id = int(

                        product["ProductID"]

                    )



                    final_product_name = (

                        product["ProductName"]

                    )



                    final_barcode = (

                        product["Barcode"]

                    )



                    gst_percent = float(

                        product["GSTPercent"] or 0

                    )





                    # ---------------------------------------------

                    # Update stock

                    # ---------------------------------------------



                    update_product_sql = text("""

                        UPDATE "Products"

                        SET

                            "Stock" =

                                COALESCE("Stock", 0)

                                + :quantity,



                            "PurchasePrice" =

                                :purchase_price,



                            "SellingPrice" =

                                :selling_price

                        WHERE "ProductID" = :product_id

                    """)



                    conn.execute(

                        update_product_sql,

                        {

                            "quantity": quantity,



                            "purchase_price":

                                purchase_price,



                            "selling_price":

                                selling_price,



                            "product_id":

                                product_id

                        }

                    )





                # =================================================

                # NEW PRODUCT

                # =================================================



                else:



                    final_product_name = product_name



                    final_barcode = (

                        barcode

                        if barcode

                        else None

                    )



                    gst_percent = 0





                    if not final_product_name:



                        raise Exception(

                            "New product must have "

                            "a product name."

                        )





                    # ---------------------------------------------

                    # Create Product

                    # ---------------------------------------------



                    insert_product_sql = text("""

                        INSERT INTO "Products"

                        (

                            "ProductName",

                            "Barcode",

                            "SellingPrice",

                            "Stock",

                            "GSTPercent",

                            "CreatedDate",

                            "PurchasePrice"

                        )
VALUES

                        (

                            :product_name,

                            :barcode,

                            :selling_price,

                            :stock,

                            :gst_percent,

                            CURRENT_TIMESTAMP,

                            :purchase_price

                        )
                        RETURNING "ProductID"
                    """)



                    result = conn.execute(

                        insert_product_sql,

                        {

                            "product_name":

                                final_product_name,



                            "barcode":

                                final_barcode,



                            "selling_price":

                                selling_price,



                            "stock":

                                quantity,



                            "gst_percent":

                                gst_percent,



                            "purchase_price":

                                purchase_price

                        }

                    )





                    product_id = int(

                        result.scalar_one()

                    )





                # =================================================

                # CREATE PRODUCT BATCH

                # =================================================



                insert_batch_sql = text("""

                    INSERT INTO "ProductBatches"

                    (

                       "ProductID",

                        "BatchNo",

                        "ManufacturingDate",

                        "ExpiryDate",

                        "PurchasePrice",

                        "SellingPrice",

                        "GSTPercent",

                        "Quantity",

                        "CreatedDate",

                        "IsActive"

                    )

                    VALUES

                    (

                        :product_id,

                        :batch_no,

                        NULL,

                        :expiry_date,

                        :purchase_price,

                        :selling_price,

                        :gst_percent,

                        :quantity,

                        CURRENT_TIMESTAMP,

                        TRUE

                    )

                """)



                conn.execute(

                    insert_batch_sql,

                    {

                        "product_id":

                            product_id,



                        "product_name":

                            final_product_name,



                        "barcode":

                            final_barcode,



                        "expiry_date":

                            item["ExpiryDate"],



                        "purchase_price":

                            purchase_price,



                        "selling_price":

                            selling_price,



                        "gst_percent":

                            gst_percent,



                        "quantity":

                            quantity,



                        "batch_no":

                            item["BatchNo"]

                    }

                )





            # =================================================

            # UPDATE MANAGER STOCK ENTRY

            # =================================================



            update_entry_sql = text("""

                UPDATE "ManagerStockEntry"

                SET

                    "Status" = 'APPROVED',



                    "InvoiceValue" =

                        :invoice_value,



                    "InvoiceDifference" =

                        :difference,



                    "InvoiceVerifiedBy" =

                        :admin_user_id,



                    "InvoiceVerifiedDate" =

                        CURRENT_TIMESTAMP,



                    "ApprovedBy" =

                        :admin_user_id,



                    "ApprovedDate" =

                        CURRENT_TIMESTAMP

                WHERE "ManagerStockEntryID" =

                    :entry_id

            """)



            conn.execute(

                update_entry_sql,

                {

                    "invoice_value":

                        invoice_value,



                    "difference":

                        difference,



                    "admin_user_id":

                        admin_user_id,



                    "entry_id":

                        entry_id

                }

            )





        # =================================================

        # COMMIT SUCCESS

        # =================================================



        return True, (

            "Stock approved successfully. "

            "Products and batches have been added to inventory."

        )





    except Exception as e:



        return False, str(e)





# =========================================================

# REJECT STOCK ENTRY

# =========================================================



def reject_stock_entry(

    entry_id,

    reason,

    admin_user_id

):



    try:



        with engine.begin() as conn:



            check_sql = text("""

                SELECT

                    "ManagerStockEntryID",

                    "Status"

                FROM "ManagerStockEntry"

                WHERE "ManagerStockEntryID" = :entry_id
                        FOR UPDATE""")



            entry = conn.execute(

                check_sql,

                {

                    "entry_id": entry_id

                }

            ).mappings().first()





            if not entry:



                raise Exception(

                    "Stock entry not found."

                )





            if str(entry["Status"]).upper() != "PENDING":



                raise Exception(

                    f"This entry is already "

                    f"{entry['Status']}."

                )





            reject_sql = text("""

                UPDATE "ManagerStockEntry"

                SET

                    "Status" = 'REJECTED',



                    "RejectionReason" =

                        :reason,



                    "ApprovedBy" =

                        :admin_user_id,



                    "ApprovedDate" =

                        CURRENT_TIMESTAMP

                WHERE "ManagerStockEntryID" =

                    :entry_id

            """)



            conn.execute(

                reject_sql,

                {

                    "reason": reason,



                    "admin_user_id":

                        admin_user_id,



                    "entry_id":

                        entry_id

                }

            )





        return True, "Stock entry rejected."





    except Exception as e:



        return False, str(e)





# =========================================================

# LOAD PENDING ENTRIES

# =========================================================



try:



    pending_entries = get_pending_entries()



except Exception as e:



    st.error(

        "Unable to load pending stock entries."

    )



    st.exception(e)



    st.stop()





# =========================================================

# NO PENDING ENTRIES

# =========================================================



if not pending_entries:



    st.success(

        "🎉 No pending stock entries."

    )



    st.stop()





# =========================================================

# SELECT ENTRY

# =========================================================



st.subheader(

    "Pending Stock Entries"

)





entry_options = {



    f"Entry #{row['ManagerStockEntryID']} | "

    f"{row['EntryDate']} | "

    f"{row['ManagerName'] or '-'} | "

    f"₹{float(row['TotalPurchaseValue']):,.2f}":

        row["ManagerStockEntryID"]



    for row in pending_entries

}





selected_label = st.selectbox(

    "Select Stock Entry",

    list(entry_options.keys())

)





selected_entry_id = entry_options[

    selected_label

]





# =========================================================

# LOAD ITEMS

# =========================================================



try:



    items = get_entry_items(

        selected_entry_id

    )



except Exception as e:



    st.error(

        "Unable to load stock entry items."

    )



    st.exception(e)



    st.stop()





if not items:



    st.warning(

        "This stock entry contains no products."

    )



    st.stop()





# =========================================================

# SELECTED HEADER

# =========================================================



selected_header = next(

    row

    for row in pending_entries

    if row["ManagerStockEntryID"]

    == selected_entry_id

)





# =========================================================

# ENTRY SUMMARY

# =========================================================



st.divider()



st.subheader(

    f"Stock Entry #{selected_entry_id}"

)





col1, col2, col3 = st.columns(3)





with col1:



    st.write(

        "\*\*Entry Date\*\*"

    )



    st.write(

        selected_header["EntryDate"]

    )





with col2:



    st.write(

        "\*\*Manager\*\*"

    )



    st.write(

        selected_header["ManagerName"]

        or "-"

    )





with col3:



    st.write(

        "\*\*Status\*\*"

    )



    st.warning(

        "PENDING"

    )





# =========================================================

# PRODUCTS

# =========================================================



st.subheader(

    "Products"

)





total_purchase_value = 0.0





for item in items:



    total_purchase_value += float(

        item["PurchaseValue"]

    )





    with st.container(

        border=True

    ):



        col1, col2, col3, col4 = st.columns(

            [3, 2, 2, 2]

        )





        with col1:



            st.markdown(

                f"\*\*{item['ProductName']}\*\*"

            )



            st.caption(

                f"Barcode: "

                f"{item['Barcode'] or '-'}"

            )





            if item["ProductStatus"] == "NEW":



                st.warning(

                    "🆕 NEW PRODUCT"

                )



            else:



                st.success(

                    "Existing Product"

                )





        with col2:



            st.write(

                f"Quantity: "

                f"{float(item['Quantity']):,.3f}"

            )



            st.write(

                f"Purchase: "

                f"₹{float(item['PurchasePrice']):,.2f}"

            )



            st.write(

                f"Selling: "

                f"₹{float(item['SellingPrice']):,.2f}"

            )





        with col3:



            st.write(

                f"Batch: "

                f"\*\*{item['BatchNo']}\*\*"

            )



            st.write(

                f"Expiry: "

                f"{item['ExpiryDate'] or '-'}"

            )





        with col4:



            st.metric(

                "Purchase Value",

                f"₹{float(item['PurchaseValue']):,.2f}"

            )





# =========================================================

# TOTAL

# =========================================================



st.divider()



col1, col2 = st.columns(2)





with col1:



    st.metric(

        "Manager Purchase Total",

        f"₹{total_purchase_value:,.2f}"

    )





with col2:



    invoice_value = st.number_input(

        "Purchase Invoice Value",

        min_value=0.0,

        value=0.0,

        step=0.01,

        format="%.2f"

    )





# =========================================================

# INVOICE DIFFERENCE

# =========================================================



difference = round(

    invoice_value - total_purchase_value,

    2

)





if invoice_value > 0:



    if abs(difference) <= 0.01:



        st.success(

            f"✅ Invoice matches. "

            f"Difference: ₹{difference:,.2f}"

        )



        invoice_matches = True



    else:



        st.error(

            f"❌ Invoice mismatch. "

            f"Difference: ₹{difference:,.2f}"

        )



        invoice_matches = False



else:



    st.info(

        "Enter the purchase invoice value."

    )



    invoice_matches = False





# =========================================================

# ACTIONS

# =========================================================



st.divider()



st.subheader(

    "Approval"

)





col1, col2 = st.columns(2)





with col1:



    approve_clicked = st.button(

        "✅ Approve",

        type="primary",

        use_container_width=True

    )





with col2:



    reject_clicked = st.button(

        "❌ Reject",

        use_container_width=True

    )





# =========================================================

# APPROVE

# =========================================================



if approve_clicked:



    if not invoice_matches:



        st.error(

            "Invoice value must exactly match "

            "the Manager purchase total before approval."

        )



    else:



        with st.spinner(

            "Adding stock to inventory..."

        ):



            success, message = approve_stock_entry(

                selected_entry_id,

                invoice_value,

                admin_user_id

            )





        if success:



            st.success(

                f"✅ {message}"

            )



            st.balloons()



            st.rerun()



        else:



            st.error(

                f"❌ Approval failed: {message}"

            )





# =========================================================

# REJECT

# =========================================================



if reject_clicked:



    st.session_state[

        "show_rejection_box"

    ] = True





if st.session_state.get(

    "show_rejection_box",

    False

):



    st.divider()



    st.subheader(

        "Reject Stock Entry"

    )



    rejection_reason = st.text_area(

        "Rejection Reason",

        placeholder=(

            "Enter the reason for rejecting "

            "this stock entry..."

        ),

        key="rejection_reason"

    )





    if st.button(

        "Confirm Rejection",

        type="secondary",

        use_container_width=True

    ):



        if not rejection_reason.strip():



            st.error(

                "Please enter a rejection reason."

            )



        else:



            success, message = reject_stock_entry(

                selected_entry_id,

                rejection_reason.strip(),

                admin_user_id

            )





            if success:



                st.success(

                    f"❌ {message}"

                )



                st.session_state[

                    "show_rejection_box"

                ] = False



                st.rerun()



            else:



                st.error(

                    f"❌ Rejection failed: {message}"

                )