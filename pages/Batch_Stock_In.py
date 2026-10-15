import streamlit as st



from logging_config import log_exception



import pandas as pd



from datetime import date, datetime



from sqlalchemy import text







from database.database import engine



from auth import require_role











# =========================================================



# ACCESS



# =========================================================







user = require_role("Manager", "Admin")











# =========================================================



# PAGE



# =========================================================







st.set_page_config(



    page_title="Batch Stock In",



    page_icon="📦",



    layout="wide"



)







#st.title("📦 Batch Stock In")



st.caption(



    f"Logged in as: {user['FullName']} • {user['Role']}"



)











# =========================================================



# LOAD PRODUCTS



# =========================================================







@st.cache_data(ttl=30)



def load_products(search=""):







    query = """

        SELECT

            "ProductID",

            "ProductName",

            "Barcode",

            "PurchasePrice",

            "SellingPrice",

            "Stock",

            "GSTPercent"

        FROM "Products"

    """







    params = {}







    if search.strip():







        query += """



            WHERE "ProductName" ILIKE :search



               OR "Barcode" ILIKE :search



        """







        params["search"] = f"%{search.strip()}%"







    query += """



        ORDER BY "ProductName"



    """







    with engine.connect() as connection:







        result = connection.execute(



            text(query),



            params



        )







        return pd.DataFrame(



            result.fetchall(),



            columns=result.keys()



        )











# =========================================================



# LOAD BATCHES



# =========================================================







@st.cache_data(ttl=10)



def load_batches(product_id=None):







    query = """

        SELECT

            b."BatchID",

            b."ProductID",

            p."ProductName",

            p."Barcode",

            b."BatchNo",

            b."ManufacturingDate",

            b."ExpiryDate",

            b."PurchasePrice",

            b."MRP",

            b."SellingPrice",

            b."GSTPercent",

            b."Quantity",

            b."CreatedDate",

            CASE

                WHEN b."ExpiryDate" < CURRENT_DATE

                    THEN 'Expired'

                WHEN b."ExpiryDate" <= CURRENT_DATE + INTERVAL '7 days'

                    THEN 'Expires in 7 days'

                WHEN b."ExpiryDate" <= CURRENT_DATE + INTERVAL '30 days'

                    THEN 'Expires in 30 days'

                ELSE 'Good'

            END AS "ExpiryStatus"

        FROM "ProductBatches" b

        INNER JOIN "Products" p

            ON p."ProductID" = b."ProductID"

        WHERE b."IsActive" = TRUE

    """







    params = {}







    if product_id is not None:







        query += """



            AND b."ProductID" = :product_id



        """







        params["product_id"] = int(product_id)







    query += """



       ORDER BY

    b."ExpiryDate" ASC,

    p."ProductName" ASC



    """







    with engine.connect() as connection:







        result = connection.execute(



            text(query),



            params



        )







        return pd.DataFrame(



            result.fetchall(),



            columns=result.keys()



        )











# =========================================================



# SUMMARY



# =========================================================







try:







    all_batches = load_batches()







    if all_batches.empty:







        total_batches = 0



        total_batch_stock = 0



        expired_batches = 0



        expiring_batches = 0







    else:







        total_batches = len(all_batches)







        total_batch_stock = float(



            all_batches["Quantity"]



            .fillna(0)



            .sum()



        )







        expired_batches = int(



            (



                all_batches["ExpiryStatus"]



                == "Expired"



            ).sum()



        )







        expiring_batches = int(



            all_batches["ExpiryStatus"]



            .isin(



                [



                    "Expires in 7 days",



                    "Expires in 30 days"



                ]



            ).sum()



        )







    c1, c2, c3, c4 = st.columns(4)







    c1.metric(



        "📦 Total Batches",



        total_batches



    )







    c2.metric(



        "📊 Batch Stock",



        f"{total_batch_stock:,.2f}"



    )







    c3.metric(



        "🔴 Expired",



        expired_batches



    )







    c4.metric(



        "🟠 Expiring Soon",



        expiring_batches



    )







except Exception as e:







    st.error("Unable to load batch information.")



    log_exception(e)



    st.exception(e)











st.divider()











# =========================================================



# ADD BATCH



# =========================================================







st.subheader("➕ Add New Batch")











search_product = st.text_input(



    "🔍 Search Product",



    placeholder="Product name or barcode..."



)











products = load_products(search_product)











if products.empty:







    st.warning("No products found.")







else:







    product_options = {}







    for _, row in products.iterrows():







        barcode = (



            ""



            if pd.isna(row["Barcode"])



            else str(row["Barcode"])



        )







        label = (



            f"{row['ProductName']} "



            f"| Stock: {float(row['Stock'] or 0):g}"



        )







        if barcode:



            label += f" | {barcode}"







        product_options[label] = int(



            row["ProductID"]



        )







    selected_label = st.selectbox(



        "Select Product",



        list(product_options.keys())



    )







    selected_product_id = product_options[



        selected_label



    ]







    selected_product = products[



        products["ProductID"]



        == selected_product_id



    ].iloc[0]











    # -----------------------------------------------------



    # Existing product information



    # -----------------------------------------------------







    info1, info2, info3, info4 = st.columns(4)







    info1.metric(



        "Current Stock",



        f"{float(selected_product['Stock'] or 0):,.2f}"



    )







    info2.metric(



        "Purchase Price",



        f"₹{float(selected_product['PurchasePrice'] or 0):,.2f}"



    )







    info3.metric(



        "Selling Price",



        f"₹{float(selected_product['SellingPrice'] or 0):,.2f}"



    )







    info4.metric(



        "GST",



        f"{float(selected_product['GSTPercent'] or 0):g}%"



    )











    st.write("")











    # -----------------------------------------------------



    # Batch form



    # -----------------------------------------------------







    batch_no_generation_key = f"batch_no_generation_{selected_product_id}"
    batch_no_generation = st.session_state.get(batch_no_generation_key, 0)
    batch_no_widget_key = (
        f"batch_no_{selected_product_id}_{batch_no_generation}"
    )

    with st.form("batch_form"):







        c1, c2 = st.columns(2)







        with c1:







            batch_no = st.text_input(
                "Batch Number *",
                value=f"B{datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]}",
                key=batch_no_widget_key,
                help="Automatically generated; you can edit it if needed."
            )







            manufacturing_date = st.date_input(



                "Manufacturing Date",



                value=date.today()



            )







            purchase_price = st.number_input(



                "Purchase Price *",



                min_value=0.0,



                value=float(



                    selected_product["PurchasePrice"] or 0



                ),



                step=0.01



            )







            mrp = st.number_input(
                "MRP *",
                min_value=0.0,
                value=float(selected_product["SellingPrice"] or 0),
                step=0.01
            )


        with c2:







            expiry_date = st.date_input(



                "Expiry Date *",



                value=date(



                    date.today().year + 1,



                    date.today().month,



                    date.today().day



                )



            )







            selling_price = st.number_input(



                "Selling Price *",



                min_value=0.0,



                value=float(



                    selected_product["SellingPrice"] or 0



                ),



                step=0.01



            )







            gst_percent = st.number_input(



                "GST %",



                min_value=0.0,



                max_value=100.0,



                value=float(



                    selected_product["GSTPercent"] or 0



                ),



                step=0.5



            )







        quantity = st.number_input(



            "Quantity *",



            min_value=0.01,



            value=1.0,



            step=1.0



        )











        submitted = st.form_submit_button(



            "💾 SAVE BATCH",



            type="primary",



            use_container_width=True



        )











    # -----------------------------------------------------



    # Save batch



    # -----------------------------------------------------







    if submitted:







        if not batch_no.strip():







            st.error(



                "Batch number is required."



            )







        elif expiry_date < manufacturing_date:







            st.error(



                "Expiry date cannot be before manufacturing date."



            )







        elif expiry_date < date.today():







            st.error(



                "Cannot add an already expired batch."



            )







        elif quantity <= 0:







            st.error(



                "Quantity must be greater than zero."



            )







        elif selling_price <= 0:







            st.error(



                "Selling price must be greater than zero."



            )







        else:







            try:







                with engine.begin() as connection:







                    # -------------------------------------



                    # Check duplicate batch



                    # -------------------------------------







                    existing = connection.execute(



                        text("""



                            SELECT "BatchID"



                            FROM "ProductBatches"



                            WHERE "ProductID" = :product_id



                              AND "BatchNo" = :batch_no



                        """),



                        {



                            "product_id": selected_product_id,



                            "batch_no": batch_no.strip()



                        }



                    ).scalar()







                    if existing:







                        raise ValueError(



                            "This batch number already exists "



                            "for this product."



                        )











                    # -------------------------------------



                    # Insert batch



                    # -------------------------------------







                    connection.execute(



                        text("""



                            INSERT INTO "ProductBatches"



                            (



                                "ProductID",



                                "BatchNo",



                                "ManufacturingDate",



                                "ExpiryDate",



                                "PurchasePrice",
                                "MRP",



                                "SellingPrice",



                                "GSTPercent",



                                "Quantity",



                                "IsActive"



                            )



                            VALUES



                            (



                                :product_id,



                                :batch_no,



                                :manufacturing_date,



                                :expiry_date,



                                :purchase_price,
                                :mrp,



                                :selling_price,



                                :gst_percent,



                                :quantity,



                                TRUE



                            )



                        """),



                        {



                            "product_id": selected_product_id,



                            "batch_no": batch_no.strip(),



                            "manufacturing_date": manufacturing_date,



                            "expiry_date": expiry_date,



                            "purchase_price": purchase_price,
                            "mrp": mrp,



                            "selling_price": selling_price,



                            "gst_percent": gst_percent,



                            "quantity": quantity



                        }



                    )











                    # -------------------------------------



                    # Update total product stock



                    # -------------------------------------







                    connection.execute(



                        text("""



                            UPDATE "Products"



                            SET



                                "Stock" = COALESCE("Stock", 0)



                                         + :quantity,







                                "PurchasePrice" = :purchase_price,







                                "SellingPrice" = :selling_price,







                                "GSTPercent" = :gst_percent







                            WHERE "ProductID" = :product_id



                        """),



                        {



                            "quantity": quantity,



                            "purchase_price": purchase_price,



                            "selling_price": selling_price,



                            "gst_percent": gst_percent,



                            "product_id": selected_product_id



                        }



                    )











                # Clear cache







                load_products.clear()



                load_batches.clear()











                st.success(

                    f"✅ Batch {batch_no.strip()} "

                    f"added successfully."

                )

                st.session_state[batch_no_generation_key] = (
                    batch_no_generation + 1
                )

                st.rerun()











            except Exception as e:







                st.error(



                    "Unable to save batch."



                )







                log_exception(e)



                st.exception(e)











st.divider()











# =========================================================



# BATCH LIST



# =========================================================







st.subheader("📋 Batch Inventory")











filter_option = st.selectbox(



    "Show",



    [



        "All Batches",



        "Active Stock Only",



        "Expired",



        "Expires in 7 Days",



        "Expires in 30 Days"



    ]



)











try:







    batches = load_batches(



        selected_product_id



        if products is not None and not products.empty



        else None



    )











    # -----------------------------------------------------



    # Filters



    # -----------------------------------------------------







    if filter_option == "Active Stock Only":







        batches = batches[



            batches["Quantity"] > 0



        ]







    elif filter_option == "Expired":







        batches = batches[



            batches["ExpiryStatus"]



            == "Expired"



        ]







    elif filter_option == "Expires in 7 Days":







        batches = batches[



            batches["ExpiryStatus"]



            == "Expires in 7 days"



        ]







    elif filter_option == "Expires in 30 Days":







        batches = batches[



            batches["ExpiryStatus"]



            == "Expires in 30 days"



        ]











    if batches.empty:
        st.info("No batches found for the selected filter.")
    else:
        st.caption(f"Showing {len(batches):,} batch(es). Use Edit to update batch details.")

        # Responsive inventory rows: avoid narrow columns and wrapped headings.
        for _, row in batches.iterrows():
            batch_id = int(row["BatchID"])
            product_name = str(row["ProductName"] or "—")
            batch_no_value = str(row["BatchNo"] or "—")
            mfg_value = row["ManufacturingDate"]
            expiry_value = row["ExpiryDate"]
            mfg_text = mfg_value.strftime("%d %b %Y") if pd.notna(mfg_value) else "—"
            expiry_text = expiry_value.strftime("%d %b %Y") if pd.notna(expiry_value) else "—"
            status = str(row["ExpiryStatus"] or "Good")

            with st.container(border=True):
                top = st.columns([3.3, 1.3, 1.3, 1.0])
                top[0].markdown(f"**{product_name}**")
                top[0].caption(f"Batch: {batch_no_value}  ·  ID: {batch_id}")
                top[1].markdown("**Expiry**")
                top[1].write(expiry_text)
                top[2].markdown("**Status**")
                if status == "Expired":
                    top[2].markdown(":red[● Expired]")
                elif status.startswith("Expires"):
                    top[2].markdown(":orange[● " + status + "]")
                else:
                    top[2].markdown(":green[● Good]")
                if top[3].button("✏️ Edit", key=f"edit_batch_{batch_id}", use_container_width=True):
                    st.session_state["editing_batch_id"] = batch_id
                    st.rerun()

                details = st.columns(7)
                detail_values = [
                    ("Manufactured", mfg_text),
                    ("Purchase", f'₹{float(row["PurchasePrice"] or 0):,.2f}'),
                    ("MRP", f'₹{float(row["MRP"] or 0):,.2f}'),
                    ("Selling", f'₹{float(row["SellingPrice"] or 0):,.2f}'),
                    ("GST", f'{float(row["GSTPercent"] or 0):g}%'),
                    ("Quantity", f'{float(row["Quantity"] or 0):g}'),
                    ("Stock Value", f'₹{float(row["PurchasePrice"] or 0) * float(row["Quantity"] or 0):,.2f}')
                ]
                for col, (label, value) in zip(details, detail_values):
                    col.caption(label)
                    col.markdown(f"**{value}**")

        @st.dialog("✏️ Edit Batch Details", width="large")
        def edit_batch_dialog(batch_id):
            with engine.connect() as connection:
                record = connection.execute(text('''
                    SELECT b."BatchID", b."ProductID", p."ProductName", b."BatchNo",
                           b."ManufacturingDate", b."ExpiryDate", b."PurchasePrice", b."MRP",
                           b."SellingPrice", b."GSTPercent", b."Quantity"
                    FROM "ProductBatches" b
                    JOIN "Products" p ON p."ProductID" = b."ProductID"
                    WHERE b."BatchID" = :batch_id
                '''), {"batch_id": batch_id}).mappings().first()
            if not record:
                st.error("Batch not found.")
                if st.button("Close"):
                    st.session_state.pop("editing_batch_id", None)
                    st.rerun()
                return

            st.write(f'**Product:** {record["ProductName"]}  ·  **Batch:** {record["BatchNo"]}')
            with st.form(f"edit_batch_form_{batch_id}"):
                left, right = st.columns(2)
                with left:
                    edit_batch_no = st.text_input("Batch Number *", value=str(record["BatchNo"] or ""))
                    edit_mfg = st.date_input("Manufacturing Date", value=record["ManufacturingDate"] or date.today())
                    edit_purchase = st.number_input("Purchase Price *", min_value=0.0, value=float(record["PurchasePrice"] or 0), step=0.01)
                    edit_mrp = st.number_input("MRP *", min_value=0.0, value=float(record["MRP"] or 0), step=0.01)
                with right:
                    edit_expiry = st.date_input("Expiry Date *", value=record["ExpiryDate"] or date.today())
                    edit_selling = st.number_input("Selling Price *", min_value=0.0, value=float(record["SellingPrice"] or 0), step=0.01)
                    edit_gst = st.number_input("GST %", min_value=0.0, max_value=100.0, value=float(record["GSTPercent"] or 0), step=0.5)
                    edit_qty = st.number_input("Quantity *", min_value=0.0, value=float(record["Quantity"] or 0), step=1.0)
                save_edit = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

            cancel_col, _ = st.columns([1, 4])
            if cancel_col.button("Cancel", key=f"cancel_edit_{batch_id}"):
                st.session_state.pop("editing_batch_id", None)
                st.rerun()

            if save_edit:
                if not edit_batch_no.strip():
                    st.error("Batch number is required.")
                elif edit_expiry < edit_mfg:
                    st.error("Expiry date cannot be before manufacturing date.")
                elif edit_selling <= 0:
                    st.error("Selling price must be greater than zero.")
                else:
                    try:
                        with engine.begin() as connection:
                            duplicate = connection.execute(text('''
                                SELECT 1 FROM "ProductBatches"
                                WHERE "ProductID" = :product_id AND "BatchNo" = :batch_no
                                  AND "BatchID" <> :batch_id
                                LIMIT 1
                            '''), {"product_id": int(record["ProductID"]), "batch_no": edit_batch_no.strip(), "batch_id": batch_id}).scalar()
                            if duplicate:
                                raise ValueError("That batch number already exists for this product.")
                            old_qty = float(record["Quantity"] or 0)
                            delta_qty = edit_qty - old_qty
                            connection.execute(text('''
                                UPDATE "ProductBatches"
                                SET "BatchNo" = :batch_no,
                                    "ManufacturingDate" = :mfg,
                                    "ExpiryDate" = :expiry,
                                    "PurchasePrice" = :purchase,
                                    "MRP" = :mrp,
                                    "SellingPrice" = :selling,
                                    "GSTPercent" = :gst,
                                    "Quantity" = :qty
                                WHERE "BatchID" = :batch_id
                            '''), {"batch_no": edit_batch_no.strip(), "mfg": edit_mfg, "expiry": edit_expiry,
                                  "purchase": edit_purchase, "mrp": edit_mrp, "selling": edit_selling,
                                  "gst": edit_gst, "qty": edit_qty, "batch_id": batch_id})
                            if delta_qty:
                                connection.execute(text('''
                                    UPDATE "Products"
                                    SET "Stock" = COALESCE("Stock", 0) + :delta_qty
                                    WHERE "ProductID" = :product_id
                                '''), {"delta_qty": delta_qty, "product_id": int(record["ProductID"])})
                        load_products.clear()
                        load_batches.clear()
                        st.session_state.pop("editing_batch_id", None)
                        st.success("Batch updated successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error("Unable to update batch.")
                        log_exception(e)
                        st.exception(e)

        if st.session_state.get("editing_batch_id") is not None:
            edit_batch_dialog(int(st.session_state["editing_batch_id"]))




except Exception as e:







    st.error(



        "Unable to load batch inventory."



    )







    log_exception(e)



    log_exception(e)



    st.exception(e)