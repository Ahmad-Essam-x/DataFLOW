"""
Sample Data & Workflow Templates Generator.
Generates realistic CSV and Excel datasets along with 9 production-grade,
curated workflow templates testing 100% of all 26 engine tools and canvas documentation tools.
"""
import os
import json
import random
import datetime
import numpy as np
import pandas as pd


def ensure_sample_data(data_dir: str, workflows_dir: str):
    """Generates all sample datasets and pre-built workflow templates."""
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(workflows_dir, exist_ok=True)
    templates_dir = os.path.join(workflows_dir, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    os.makedirs(os.path.join(templates_dir, "user"), exist_ok=True)

    # Legacy cleanup
    obsolete_wf = os.path.join(workflows_dir, "data_cleaning_and_deduplication.json")
    if os.path.exists(obsolete_wf):
        try:
            os.remove(obsolete_wf)
        except OSError:
            pass

    # -------------------------------------------------------------------------
    # 1. Dataset: sales_orders.csv
    # -------------------------------------------------------------------------
    sales_csv_path = os.path.join(data_dir, "sales_orders.csv")
    if not os.path.exists(sales_csv_path):
        np.random.seed(42)
        regions = ["North", "South", "East", "West"]
        segments = ["Consumer", "Corporate", "Home Office"]
        states = {
            "North": ["New York", "Massachusetts", "Illinois"],
            "South": ["Texas", "Florida", "Georgia"],
            "East": ["Pennsylvania", "Virginia", "Maryland"],
            "West": ["California", "Washington", "Colorado"]
        }
        notes = [
            "  urgent delivery requested  ",
            "Customer requested gift receipt.",
            "   VIP CLIENT - priority processing   ",
            "Regular recurring replenishment order.",
            " verified address with accounting department ",
            "First time buyer discount applied.",
            "   expedite shipping   ",
            "Standard checkout."
        ]
        orders = []
        for i in range(1, 101):
            region = np.random.choice(regions)
            state = np.random.choice(states[region])
            segment = np.random.choice(segments)
            qty = int(np.random.randint(1, 15))
            unit_price = round(float(np.random.uniform(25.0, 350.0)), 2)
            discount = float(np.random.choice([0.0, 0.05, 0.1, 0.15, 0.2]))
            month = np.random.randint(1, 13)
            day = np.random.randint(1, 28)
            order_date = f"2024-{month:02d}-{day:02d}"
            note = np.random.choice(notes)
            orders.append({
                "OrderID": f"ORD-{1000 + i}",
                "CustomerID": f"CUST-{np.random.randint(101, 140)}",
                "CustomerName": f"Client {chr(65 + (i % 26))} {i}",
                "Segment": segment,
                "Region": region.lower() if i % 4 == 0 else region.upper() if i % 5 == 0 else region,
                "State": state,
                "OrderDate": order_date,
                "Quantity": qty,
                "UnitPrice": unit_price,
                "Discount": discount,
                "CustomerNotes": note
            })
        pd.DataFrame(orders).to_csv(sales_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 2. Dataset: warehouse_inventory.xlsx
    # -------------------------------------------------------------------------
    inv_xlsx_path = os.path.join(data_dir, "warehouse_inventory.xlsx")
    if not os.path.exists(inv_xlsx_path):
        suppliers = ["SUP101", "SUP102", "SUP103", "SUP104", "SUP105"]
        categories = ["ELEC", "MECH", "CHEM", "PACK", "TOOL"]
        warehouses = ["WH-Central", "WH-East", "WH-West", "WH-South"]
        inventory = []
        for i in range(1, 61):
            sup = np.random.choice(suppliers)
            cat = np.random.choice(categories)
            batch = f"B{np.random.randint(10, 99)}"
            composite = f"{sup}-{cat}-{batch}"
            sku = f"SKU-{1000 + (i % 45)}"
            wh = np.random.choice(warehouses)
            qty = int(np.random.randint(10, 500))
            reorder = int(np.random.choice([50, 100, 150, 200]))
            inventory.append({
                "SKU": sku,
                "CompositeBatchCode": composite,
                "WarehouseLocation": wh,
                "QtyOnHand": qty,
                "ReorderLevel": reorder
            })
        inventory.append(inventory[0].copy())
        inventory.append(inventory[1].copy())
        df_inv = pd.DataFrame(inventory)
        with pd.ExcelWriter(inv_xlsx_path, engine="openpyxl") as writer:
            df_inv.to_excel(writer, sheet_name="Inventory", index=False)

    # -------------------------------------------------------------------------
    # 3. Dataset: quarterly_campaign_responses.csv
    # -------------------------------------------------------------------------
    camp_csv_path = os.path.join(data_dir, "quarterly_campaign_responses.csv")
    if not os.path.exists(camp_csv_path):
        campaign_codes = ["CAMP_SUM_24", "CAMP_AUT_24", "CAMP_WIN_24", "CAMP_SPR_24"]
        regions_list = ["North America", "EMEA", "APAC", "LATAM"]
        responses = []
        for i in range(1, 81):
            email = f"user_{i}@enterprise{i % 25}.com"
            code = np.random.choice(campaign_codes)
            reg = np.random.choice(regions_list)
            q1 = int(np.random.randint(40, 100))
            q2 = int(np.random.randint(45, 100))
            q3 = int(np.random.randint(50, 100))
            q4 = int(np.random.randint(55, 100))
            responses.append({
                "Email": email,
                "CampaignCode": code,
                "Region": reg,
                "Q1_Score": q1,
                "Q2_Score": q2,
                "Q3_Score": q3,
                "Q4_Score": q4
            })
        pd.DataFrame(responses).to_csv(camp_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 4. Dataset: customers.csv & orders.xlsx
    # -------------------------------------------------------------------------
    cust_csv_path = os.path.join(data_dir, "customers.csv")
    if not os.path.exists(cust_csv_path):
        first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        regions = ["North America", "Europe", "Asia-Pacific", "Latin America"]
        segments = ["Corporate", "Consumer", "Home Office"]
        random.seed(42)
        customers = []
        for i in range(1, 101):
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            customers.append({
                "CustomerID": f"CUST-{i:04d}",
                "CustomerName": f"{fn} {ln}",
                "Email": f"{fn.lower()}.{ln.lower()}{random.randint(10, 99)}@example.com",
                "Region": random.choice(regions),
                "Segment": random.choice(segments),
                "SignupDate": "2023-01-15"
            })
        pd.DataFrame(customers).to_csv(cust_csv_path, index=False)

    orders_xlsx_path = os.path.join(data_dir, "orders.xlsx")
    if not os.path.exists(orders_xlsx_path):
        orders_legacy = []
        for o_id in range(1001, 1150):
            orders_legacy.append({
                "OrderID": f"ORD-{o_id}",
                "CustomerID": f"CUST-{random.randint(1, 100):04d}",
                "Product": "Laptop Pro 15",
                "Category": "Technology",
                "Quantity": random.randint(1, 5),
                "UnitPrice": 1299.00,
                "Discount": 0.10,
                "OrderDate": "2023-06-20"
            })
        pd.DataFrame(orders_legacy).to_excel(orders_xlsx_path, index=False)

    # -------------------------------------------------------------------------
    # 5. Dataset: orders.csv (for RFM Segmentation)
    # -------------------------------------------------------------------------
    orders_csv_path = os.path.join(data_dir, "orders.csv")
    if not os.path.exists(orders_csv_path):
        np.random.seed(42)
        rows_orders = []
        for i in range(1, 151):
            cust_id = f"CUST-{np.random.randint(101, 140)}"
            dt = f"2024-{np.random.randint(1, 13):02d}-{np.random.randint(1, 28):02d}"
            val = round(float(np.random.uniform(20.0, 850.0)), 2)
            qty = int(np.random.randint(1, 10))
            rows_orders.append({
                "OrderID": f"ORD-{1000 + i}",
                "CustomerID": cust_id,
                "CustomerName": f"Customer {cust_id.split('-')[1]}",
                "OrderDate": dt,
                "OrderValue": val,
                "Quantity": qty,
                "PaymentMethod": np.random.choice(["Credit Card", "PayPal", "Bank Transfer", "Apple Pay"])
            })
        pd.DataFrame(rows_orders).to_csv(orders_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 6. Datasets: dirty_customer_data.csv & your_data.csv
    # -------------------------------------------------------------------------
    dirty_csv_path = os.path.join(data_dir, "dirty_customer_data.csv")
    your_csv_path = os.path.join(data_dir, "your_data.csv")
    if not os.path.exists(dirty_csv_path) or not os.path.exists(your_csv_path):
        np.random.seed(42)
        states_sample = ["NY", "CA", "TX", "FL", "IL", "ny", "ca", "  TX  ", "fl"]
        dirty_rows = []
        for i in range(1, 81):
            email = f"user_{i}@domain.com"
            if i % 3 == 0:
                email = f"  {email}  "
            income = round(float(np.random.uniform(35000, 140000)), 2) if i % 10 != 0 else np.nan
            phone = f"555-{np.random.randint(100, 999)}-{np.random.randint(1000, 9999)}" if i % 8 != 0 else None
            dirty_rows.append({
                "CustomerID": f"CUST-{1000 + i}",
                "FullName": f"  Customer Name {i}  " if i % 2 == 0 else f"Customer Name {i}",
                "Email": email,
                "PhoneNumber": phone,
                "PostalCode": f"{np.random.randint(10000, 99999)}",
                "State": np.random.choice(states_sample),
                "SignupDate": f"2023-{np.random.randint(1, 13):02d}-01",
                "AnnualIncome": income,
                "CreditScore": int(np.random.randint(580, 820))
            })
        dirty_rows.append(dirty_rows[0].copy())
        dirty_rows.append(dirty_rows[1].copy())
        df_dirty = pd.DataFrame(dirty_rows)
        df_dirty.to_csv(dirty_csv_path, index=False)
        df_dirty.to_csv(your_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 7. Dataset: crm_pipeline.csv
    # -------------------------------------------------------------------------
    crm_csv_path = os.path.join(data_dir, "crm_pipeline.csv")
    if not os.path.exists(crm_csv_path):
        np.random.seed(42)
        reps = ["Alice Johnson", "Bob Smith", "Charlie Davis", "Diana Prince", "Evan Wright"]
        stages = [
            ("Lead", 0.10),
            ("Qualification", 0.25),
            ("Proposal", 0.50),
            ("Negotiation", 0.75),
            ("Closed Won", 1.00),
            ("Closed Lost", 0.00)
        ]
        regions_crm = ["North America", "EMEA", "APAC", "LATAM"]
        crm_rows = []
        for i in range(1, 76):
            stage_tuple = stages[np.random.randint(0, len(stages))]
            val = round(float(np.random.uniform(5000, 120000)), 2)
            crm_rows.append({
                "DealID": f"DEAL-{2000 + i}",
                "AccountName": f"Enterprise Account {chr(65 + (i % 26))} {i}",
                "SalesRep": np.random.choice(reps),
                "Region": np.random.choice(regions_crm),
                "Stage": stage_tuple[0],
                "DealValue": val,
                "Probability": stage_tuple[1],
                "CloseDate": f"2024-{np.random.randint(1, 13):02d}-{np.random.randint(1, 28):02d}",
                "IsWon": stage_tuple[0] == "Closed Won"
            })
        pd.DataFrame(crm_rows).to_csv(crm_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 8. Datasets for MultiJoin: employee_performance, department_budgets, department_operating_expenses
    # -------------------------------------------------------------------------
    emp_csv_path = os.path.join(data_dir, "employee_performance.csv")
    dept_csv_path = os.path.join(data_dir, "department_budgets.csv")
    exp_csv_path = os.path.join(data_dir, "department_operating_expenses.csv")
    if not os.path.exists(emp_csv_path) or not os.path.exists(dept_csv_path) or not os.path.exists(exp_csv_path):
        np.random.seed(42)
        departments = ["Engineering", "Sales", "Marketing", "Finance", "Operations"]
        emp_rows = []
        for i in range(1, 51):
            dept = np.random.choice(departments)
            base = round(float(np.random.uniform(65000, 185000)), 2)
            bonus = round(float(np.random.choice([0.05, 0.10, 0.15, 0.20])), 2)
            emp_rows.append({
                "EmployeeID": f"EMP-{5000 + i}",
                "EmployeeName": f"Employee {chr(65 + (i % 26))} {i}",
                "Department": dept,
                "BaseSalary": base,
                "BonusPct": bonus,
                "PerformanceRating": np.random.choice(["Exceeds", "Meets", "Outstanding", "Developing"])
            })
        pd.DataFrame(emp_rows).to_csv(emp_csv_path, index=False)

        dept_rows = [
            {"Department": "Engineering", "BudgetCap": 2800000.0, "FiscalYear": 2024, "DepartmentHead": "Sarah Connor"},
            {"Department": "Sales", "BudgetCap": 2100000.0, "FiscalYear": 2024, "DepartmentHead": "Gordon Gekko"},
            {"Department": "Marketing", "BudgetCap": 1500000.0, "FiscalYear": 2024, "DepartmentHead": "Peggy Olson"},
            {"Department": "Finance", "BudgetCap": 1200000.0, "FiscalYear": 2024, "DepartmentHead": "Jordan Belfort"},
            {"Department": "Operations", "BudgetCap": 1400000.0, "FiscalYear": 2024, "DepartmentHead": "Dwight Schrute"}
        ]
        pd.DataFrame(dept_rows).to_csv(dept_csv_path, index=False)

        exp_rows = [
            {"Department": "Engineering", "SoftwareSpend": 450000.0, "EquipmentSpend": 180000.0, "TravelSpend": 65000.0},
            {"Department": "Sales", "SoftwareSpend": 280000.0, "EquipmentSpend": 85000.0, "TravelSpend": 320000.0},
            {"Department": "Marketing", "SoftwareSpend": 340000.0, "EquipmentSpend": 45000.0, "TravelSpend": 95000.0},
            {"Department": "Finance", "SoftwareSpend": 160000.0, "EquipmentSpend": 35000.0, "TravelSpend": 45000.0},
            {"Department": "Operations", "SoftwareSpend": 190000.0, "EquipmentSpend": 210000.0, "TravelSpend": 55000.0}
        ]
        pd.DataFrame(exp_rows).to_csv(exp_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 9. Dataset: customer_reviews.csv
    # -------------------------------------------------------------------------
    rev_csv_path = os.path.join(data_dir, "customer_reviews.csv")
    if not os.path.exists(rev_csv_path):
        reviews_catalog = [
            ("Client A", "UltraBook Pro 15", 5, "Absolutely stellar device! Lightweight, battery lasts over 12 hours, screen is gorgeous."),
            ("Client B", "ErgoWireless Mouse", 1, "Stopped working after only three days. Laser sensor doesn't track and plastic feels flimsy."),
            ("Client C", "4K Ultra Monitor", 4, "Great color calibration right out of the box. Stand could be sturdier but overall very pleased."),
            ("Client D", "NoiseCancel Pro Headphones", 5, "Best noise cancellation on the market. Blocks airplane hum completely. Very comfortable."),
            ("Client E", "SmartDock Thunderbolt", 2, "Constantly disconnects dual monitors on sleep resume. Firmware update did not resolve."),
            ("Client F", "Mechanical Keyboard RGB", 4, "Crisp tactile switches and pleasant keycap profile. Software is a bit clunky."),
            ("Client G", "USB-C Multiport Hub", 1, "Overheats severely when charging while driving external HDMI display. Not recommended."),
            ("Client H", "Executive Leather Sleeve", 5, "Exquisite stitching and snug fit. Protects laptop nicely in briefcase."),
            ("Client I", "Webcam 4K Streaming", 3, "Decent image quality in good lighting, but low-light performance is noisy. Autofocus hunts."),
            ("Client J", "Compact Power Adapter 100W", 5, "Tiny footprint yet charges laptop and phone simultaneously without getting too hot.")
        ]
        rev_rows = []
        for i in range(1, 41):
            r = reviews_catalog[i % len(reviews_catalog)]
            rev_rows.append({
                "ReviewID": f"REV-{3000 + i}",
                "CustomerName": f"{r[0]} {i}",
                "ProductName": r[1],
                "StarRating": r[2],
                "ReviewText": f"  {r[3]}  " if i % 2 == 0 else r[3],
                "ReviewDate": f"2024-{np.random.randint(1, 13):02d}-{np.random.randint(1, 28):02d}"
            })
        pd.DataFrame(rev_rows).to_csv(rev_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 10. Dataset: invoices_raw.csv
    # -------------------------------------------------------------------------
    inv_csv_path = os.path.join(data_dir, "invoices_raw.csv")
    if not os.path.exists(inv_csv_path):
        inv_catalog = [
            ("Apex Cloud Services LLC", "INV-2024-101", 3450.00, "2024-11-15", "Apex Cloud Services LLC Invoice INV-2024-101 for monthly cloud infrastructure hosting and kubernetes cluster compute. Total due: $3,450.00. Payment terms Net 30. Due date: 2024-11-15."),
            ("Global Office Logistics", "INV-2024-204", 1280.50, "2024-10-31", "Invoice INV-2024-204 from Global Office Logistics covering ergonomic desk furniture and ergonomic chairs. Balance: $1,280.50. Remit before 2024-10-31."),
            ("CyberShield Security Inc", "SEC-8891", 5600.00, "2024-12-01", "CyberShield Security Inc billing ref SEC-8891 for annual endpoint protection license renewals. Total payable: $5,600.00 due on 2024-12-01."),
            ("Metro Couriers Express", "EXP-4402", 420.75, "2024-11-05", "Billing statement EXP-4402 by Metro Couriers Express for express document delivery services. Amount $420.75 payable by 2024-11-05."),
            ("Precision Tooling Works", "PTW-9912", 2150.00, "2024-11-20", "Precision Tooling Works invoice PTW-9912 for warehouse replacement conveyor parts and maintenance. Total: $2,150.00 due 2024-11-20.")
        ]
        inv_rows = []
        for i in range(1, 31):
            t = inv_catalog[i % len(inv_catalog)]
            inv_rows.append({
                "InvoiceID": f"INV-RAW-{i:03d}",
                "InvoiceText": f"  {t[4]}  ",
                "VendorHint": t[0],
                "ReceivedDate": f"2024-10-{np.random.randint(1, 28):02d}"
            })
        pd.DataFrame(inv_rows).to_csv(inv_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 11. Curated Template Workflows Generation
    # -------------------------------------------------------------------------
    templates = _get_curated_templates()
    for fname, wf_data in templates.items():
        # Write to templates/
        tpl_path = os.path.join(templates_dir, fname)
        with open(tpl_path, "w", encoding="utf-8") as f:
            json.dump(wf_data, f, indent=2, ensure_ascii=False)

        # Write the 4 flagship workflows to workflows/ root as well
        if fname in ("sales_customer_enrichment.json", "inventory_supplier_reconciliation.json",
                     "marketing_campaign_attribution.json", "multijoin_expense_reconciliation.json"):
            wf_path = os.path.join(workflows_dir, fname)
            with open(wf_path, "w", encoding="utf-8") as f:
                json.dump(wf_data, f, indent=2, ensure_ascii=False)


def _get_curated_templates():
    """Returns the full definitions of all 9 curated workflow templates."""
    return {
        "sales_customer_enrichment.json": {
            "name": "Customer Sales Analysis",
            "description": "Cleans customer records, standardizes order dates with DateTime parsing, calculates net revenues and margins, filters high-value orders, and summarizes regional performance.",
            "category": "sales",
            "tags": ["sales", "revenue", "datetime", "summarize", "kpi"],
            "difficulty": "beginner",
            "containers": [
                {
                    "id": "container_sales_1",
                    "title": "Sales Performance & Customer Enrichment",
                    "x": 60, "y": 60, "width": 1840, "height": 380,
                    "color": "rgba(34, 197, 94, 0.08)", "headerColor": "#16a34a",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_sales_1",
                    "text": "### Executive Sales KPIs\n- Auto Field optimizes incoming types automatically.\n- Data Clean trims whitespace and title-cases region names.\n- DateTime normalizes dates into ISO format.\n- Formula calculates Net Revenue after discounts.\n- High-value transactions (> $500) are aggregated by Region and Segment.\n- Multi-Row Formula calculates running cumulative revenues across segments.",
                    "x": 60, "y": 460, "width": 440, "height": 140, "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_sales_in", "type": "input_data", "name": "Input Sales Orders (CSV)",
                    "x": 100, "y": 180,
                    "config": {"file_path": "sales_orders.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_sales_autofield", "type": "auto_field", "name": "Auto Field Types",
                    "x": 280, "y": 180, "config": {"fields": []}
                },
                {
                    "id": "node_sales_clean", "type": "clean", "name": "Clean Text & Region",
                    "x": 460, "y": 180,
                    "config": {"columns": ["CustomerNotes", "Region"], "trim_whitespace": True, "case_transformation": "title", "remove_empty_rows": False}
                },
                {
                    "id": "node_sales_dt", "type": "date_time", "name": "Parse OrderDate",
                    "x": 640, "y": 180,
                    "config": {"column": "OrderDate", "conversion_type": "string_to_date", "format_template": "yyyy-MM-dd", "output_column": "OrderDate_ISO"}
                },
                {
                    "id": "node_sales_formula", "type": "formula", "name": "Calculate Net Revenue",
                    "x": 820, "y": 180,
                    "config": {
                        "formulas": [
                            {"output_field": "GrossAmount", "type": "float", "expression": "[Quantity] * [UnitPrice]"},
                            {"output_field": "NetAmount", "type": "float", "expression": "[GrossAmount] * (1.0 - [Discount])"}
                        ]
                    }
                },
                {
                    "id": "node_sales_filter", "type": "filter", "name": "Filter Orders > $500",
                    "x": 1000, "y": 180,
                    "config": {"mode": "basic", "logical_op": "AND", "conditions": [{"column": "NetAmount", "operator": ">", "value": "500"}]}
                },
                {
                    "id": "node_sales_summarize", "type": "summarize", "name": "Summarize by Region & Segment",
                    "x": 1200, "y": 140,
                    "config": {
                        "actions": [
                            {"field": "Region", "action": "GroupBy", "output_name": "Region"},
                            {"field": "Segment", "action": "GroupBy", "output_name": "Segment"},
                            {"field": "NetAmount", "action": "Sum", "output_name": "TotalRevenue"},
                            {"field": "NetAmount", "action": "Average", "output_name": "AvgOrderValue"},
                            {"field": "OrderID", "action": "Count", "output_name": "HighValueOrderCount"}
                        ]
                    }
                },
                {
                    "id": "node_sort_1", "type": "sort", "name": "Sort Revenue Desc",
                    "x": 1380, "y": 140,
                    "config": {"sort_by": [{"column": "TotalRevenue", "ascending": False}]}
                },
                {
                    "id": "node_sales_multirow", "type": "multi_row_formula", "name": "Cumulative Sales Total",
                    "x": 1560, "y": 140,
                    "config": {
                        "output_field": "CumulativeRevenue", "is_new_field": True, "output_type": "float",
                        "values_for_rows_not_exist": "0", "group_by_fields": [], "expression": "[Row-1:CumulativeRevenue] + [TotalRevenue]"
                    }
                },
                {
                    "id": "node_sales_out", "type": "output_data", "name": "Export Sales Summary",
                    "x": 1740, "y": 140,
                    "config": {"filename": "regional_sales_summary", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_sales_browse", "type": "browse", "name": "Browse Sales Profile",
                    "x": 1740, "y": 260, "config": {}
                }
            ],
            "connections": [
                {"id": "c1", "source": "node_sales_in", "sourceHandle": "O", "target": "node_sales_autofield", "targetHandle": "I"},
                {"id": "c1_b", "source": "node_sales_autofield", "sourceHandle": "O", "target": "node_sales_clean", "targetHandle": "I"},
                {"id": "c2", "source": "node_sales_clean", "sourceHandle": "O", "target": "node_sales_dt", "targetHandle": "I"},
                {"id": "c3", "source": "node_sales_dt", "sourceHandle": "O", "target": "node_sales_formula", "targetHandle": "I"},
                {"id": "c4", "source": "node_sales_formula", "sourceHandle": "O", "target": "node_sales_filter", "targetHandle": "I"},
                {"id": "c5", "source": "node_sales_filter", "sourceHandle": "T", "target": "node_sales_summarize", "targetHandle": "I"},
                {"id": "c6", "source": "node_sales_summarize", "sourceHandle": "O", "target": "node_sort_1", "targetHandle": "I"},
                {"id": "c7", "source": "node_sort_1", "sourceHandle": "O", "target": "node_sales_multirow", "targetHandle": "I"},
                {"id": "c8", "source": "node_sales_multirow", "sourceHandle": "O", "target": "node_sales_out", "targetHandle": "I"},
                {"id": "c9", "source": "node_sales_multirow", "sourceHandle": "O", "target": "node_sales_browse", "targetHandle": "I"}
            ]
        },

        "inventory_supplier_reconciliation.json": {
            "name": "Inventory & Supplier Reconciliation",
            "description": "Splits composite warehouse SKUs, deduplicates counts, reconciles stock levels with supplier lead times via Join, cross-appends holding parameters, and generates audit ledger tracking IDs.",
            "category": "operations",
            "tags": ["inventory", "join", "unique", "text_to_columns", "append_fields", "supply_chain"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "container_inv_1", "title": "Supply Chain & Warehouse Audit Ledger",
                    "x": 60, "y": 60, "width": 1540, "height": 420,
                    "color": "rgba(168, 85, 247, 0.08)", "headerColor": "#9333ea",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_inv_1",
                    "text": "### Inventory Audit Protocol\n- Excel stock counts are parsed with Text to Columns into Supplier, Category, and Batch.\n- Unique separates distinct stock counts from duplicate entries.\n- Join matches warehouse quantities against Supplier contract terms.\n- Append Fields cross-appends corporate holding cost benchmarks.",
                    "x": 60, "y": 500, "width": 460, "height": 140, "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_inv_in", "type": "input_data", "name": "Input Warehouse Stock (Excel)",
                    "x": 100, "y": 160,
                    "config": {"file_path": "warehouse_inventory.xlsx", "file_type": "excel", "sheet_name": "Inventory", "has_header": True}
                },
                {
                    "id": "node_inv_split", "type": "text_to_columns", "name": "Split Batch Code",
                    "x": 280, "y": 160,
                    "config": {"column": "CompositeBatchCode", "delimiters": "-", "split_type": "columns", "num_columns": 3, "root_name": "BatchPart_", "extra_characters": "last"}
                },
                {
                    "id": "node_inv_unique", "type": "unique", "name": "Deduplicate Stock Counts",
                    "x": 460, "y": 160, "config": {"columns": ["SKU", "WarehouseLocation"]}
                },
                {
                    "id": "node_suppliers_input", "type": "text_input", "name": "Supplier Reference Catalog",
                    "x": 460, "y": 320,
                    "config": {
                        "columns": ["SupplierID", "SupplierName", "LeadTimeDays", "Rating"],
                        "data": [
                            ["SUP101", "Acme Electronics Corp", 5, "A"],
                            ["SUP102", "Global Mech Systems", 12, "A+"],
                            ["SUP103", "Apex Chemical Industries", 8, "B"],
                            ["SUP104", "Pacific Packaging Co", 3, "A"],
                            ["SUP105", "Titan Tooling Works", 15, "B+"]
                        ]
                    }
                },
                {
                    "id": "node_inv_join", "type": "join", "name": "Join Stock with Suppliers",
                    "x": 680, "y": 200,
                    "config": {"join_mode": "specific_fields", "join_keys": [{"left_key": "BatchPart_1", "right_key": "SupplierID"}]}
                },
                {
                    "id": "node_inv_params", "type": "text_input", "name": "Audit Rate Parameters",
                    "x": 680, "y": 340,
                    "config": {"columns": ["HoldingRate", "Currency"], "data": [[0.085, "USD"]]}
                },
                {
                    "id": "node_inv_append", "type": "append_fields", "name": "Append Financial Parameters",
                    "x": 900, "y": 220,
                    "config": {"cartesian_mode": "error_16", "source_prefix": "Param_"}
                },
                {
                    "id": "node_inv_recid", "type": "record_id", "name": "Generate Audit Ledger ID",
                    "x": 1120, "y": 220,
                    "config": {"column_name": "AuditTrackingID", "start_value": 1001, "position": "first"}
                },
                {
                    "id": "node_inv_out", "type": "output_data", "name": "Export Audit Ledger",
                    "x": 1320, "y": 220,
                    "config": {"filename": "inventory_audit_ledger", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_inv_browse", "type": "browse", "name": "Browse Reconciled Stock",
                    "x": 1320, "y": 340, "config": {}
                }
            ],
            "connections": [
                {"id": "ci1", "source": "node_inv_in", "sourceHandle": "O", "target": "node_inv_split", "targetHandle": "I"},
                {"id": "ci2", "source": "node_inv_split", "sourceHandle": "O", "target": "node_inv_unique", "targetHandle": "I"},
                {"id": "ci3", "source": "node_inv_unique", "sourceHandle": "U", "target": "node_inv_join", "targetHandle": "L"},
                {"id": "ci4", "source": "node_suppliers_input", "sourceHandle": "O", "target": "node_inv_join", "targetHandle": "R"},
                {"id": "ci5", "source": "node_inv_join", "sourceHandle": "J", "target": "node_inv_append", "targetHandle": "T"},
                {"id": "ci6", "source": "node_inv_params", "sourceHandle": "O", "target": "node_inv_append", "targetHandle": "S"},
                {"id": "ci7", "source": "node_inv_append", "sourceHandle": "O", "target": "node_inv_recid", "targetHandle": "I"},
                {"id": "ci8", "source": "node_inv_recid", "sourceHandle": "O", "target": "node_inv_out", "targetHandle": "I"},
                {"id": "ci9", "source": "node_inv_recid", "sourceHandle": "O", "target": "node_inv_browse", "targetHandle": "I"}
            ]
        },

        "marketing_campaign_attribution.json": {
            "name": "Marketing Attribution & Survey Matrix",
            "description": "Unions web and mobile survey streams, replaces campaign codes with friendly names, selects key attributes, unpivots quarterly ratings with Transpose, samples records, and pivots into a Regional cross-tab matrix.",
            "category": "marketing",
            "tags": ["marketing", "union", "find_replace", "transpose", "crosstab", "multi_field"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "container_mkt_1", "title": "Marketing Attribution & Pivoting Pipeline",
                    "x": 60, "y": 60, "width": 1760, "height": 420,
                    "color": "rgba(249, 115, 22, 0.08)", "headerColor": "#f97316",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_mkt_1",
                    "text": "### Survey Analysis Methodology\n- Web survey responses are unioned with mobile telemetry records.\n- Find Replace maps campaign codes to human-readable names.\n- Select casts scores and standardizes headers.\n- Multi-Field Formula applies batch numeric transformations to Q1-Q4 scores.\n- Transpose melts Q1-Q4 ratings into tall pairs.\n- Cross Tab aggregates average ratings into an Executive Regional Grid.",
                    "x": 60, "y": 500, "width": 460, "height": 140, "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_mkt_in", "type": "input_data", "name": "Input Web Responses (CSV)",
                    "x": 100, "y": 150,
                    "config": {"file_path": "quarterly_campaign_responses.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_mkt_mobile", "type": "text_input", "name": "Mobile Event Responses",
                    "x": 100, "y": 300,
                    "config": {
                        "columns": ["Email", "CampaignCode", "Region", "Q1_Score", "Q2_Score", "Q3_Score", "Q4_Score"],
                        "data": [
                            ["mobile_1@app.com", "CAMP_SUM_24", "North America", 88, 92, 85, 94],
                            ["mobile_2@app.com", "CAMP_WIN_24", "EMEA", 75, 78, 82, 89],
                            ["mobile_3@app.com", "CAMP_AUT_24", "APAC", 91, 90, 93, 95],
                            ["mobile_4@app.com", "CAMP_SPR_24", "LATAM", 80, 84, 82, 88]
                        ]
                    }
                },
                {
                    "id": "node_mkt_union", "type": "union", "name": "Union Web & Mobile Logs",
                    "x": 300, "y": 210, "config": {"mode": "by_name", "non_matching": "all"}
                },
                {
                    "id": "node_mkt_lookup", "type": "text_input", "name": "Campaign Dictionary",
                    "x": 300, "y": 340,
                    "config": {
                        "columns": ["Code", "CampaignName", "Tier"],
                        "data": [
                            ["CAMP_SUM_24", "Summer Brand Lift", "Tier-1"],
                            ["CAMP_AUT_24", "Autumn Customer Retarget", "Tier-2"],
                            ["CAMP_WIN_24", "Winter Holiday Blitz", "Tier-1"],
                            ["CAMP_SPR_24", "Spring Product Launch", "Tier-2"]
                        ]
                    }
                },
                {
                    "id": "node_mkt_fr", "type": "find_replace", "name": "Replace Campaign Codes",
                    "x": 500, "y": 240,
                    "config": {
                        "find_field": "CampaignCode", "find_value_field": "Code", "action": "replace",
                        "replace_with_field": "CampaignName", "search_mode": "entire_field", "case_sensitive": False
                    }
                },
                {
                    "id": "node_mkt_select", "type": "select", "name": "Select & Format Fields",
                    "x": 680, "y": 240,
                    "config": {
                        "fields": [
                            {"original": "Email", "keep": True, "rename": "UserEmail", "type": "string"},
                            {"original": "CampaignCode", "keep": True, "rename": "CampaignName", "type": "string"},
                            {"original": "Region", "keep": True, "rename": "Region", "type": "string"},
                            {"original": "Q1_Score", "keep": True, "rename": "Q1", "type": "float"},
                            {"original": "Q2_Score", "keep": True, "rename": "Q2", "type": "float"},
                            {"original": "Q3_Score", "keep": True, "rename": "Q3", "type": "float"},
                            {"original": "Q4_Score", "keep": True, "rename": "Q4", "type": "float"}
                        ]
                    }
                },
                {
                    "id": "node_mkt_multifield", "type": "multi_field_formula", "name": "Standardize Scores",
                    "x": 860, "y": 240,
                    "config": {
                        "selected_fields": ["Q1", "Q2", "Q3", "Q4"], "field_type_filter": "numeric",
                        "output_mode": "update", "output_prefix": "", "output_suffix": "", "output_type": "float",
                        "expression": "[_CurrentField_] * 1.0"
                    }
                },
                {
                    "id": "node_mkt_transpose", "type": "transpose", "name": "Unpivot Quarterly Scores",
                    "x": 1040, "y": 240,
                    "config": {
                        "key_columns": ["UserEmail", "CampaignName", "Region"],
                        "data_columns": ["Q1", "Q2", "Q3", "Q4"],
                        "name_column": "Quarter", "value_column": "Score"
                    }
                },
                {
                    "id": "node_mkt_sample", "type": "sample", "name": "Sample Validation Rows",
                    "x": 1220, "y": 240, "config": {"sample_type": "first_n", "n_records": 100}
                },
                {
                    "id": "node_mkt_crosstab", "type": "crosstab", "name": "Pivot to Regional Matrix",
                    "x": 1420, "y": 240,
                    "config": {"group_by": ["Region"], "header_field": "CampaignName", "value_field": "Score", "agg_func": "mean"}
                },
                {
                    "id": "node_mkt_out", "type": "output_data", "name": "Export Attribution Matrix",
                    "x": 1620, "y": 240,
                    "config": {"filename": "campaign_attribution_matrix", "format": "csv", "write_mode": "overwrite"}
                }
            ],
            "connections": [
                {"id": "cm1", "source": "node_mkt_in", "sourceHandle": "O", "target": "node_mkt_union", "targetHandle": "I"},
                {"id": "cm2", "source": "node_mkt_mobile", "sourceHandle": "O", "target": "node_mkt_union", "targetHandle": "I"},
                {"id": "cm3", "source": "node_mkt_union", "sourceHandle": "O", "target": "node_mkt_fr", "targetHandle": "F"},
                {"id": "cm4", "source": "node_mkt_lookup", "sourceHandle": "O", "target": "node_mkt_fr", "targetHandle": "R"},
                {"id": "cm5", "source": "node_mkt_fr", "sourceHandle": "O", "target": "node_mkt_select", "targetHandle": "I"},
                {"id": "cm6", "source": "node_mkt_select", "sourceHandle": "O", "target": "node_mkt_multifield", "targetHandle": "I"},
                {"id": "cm6_b", "source": "node_mkt_multifield", "sourceHandle": "O", "target": "node_mkt_transpose", "targetHandle": "I"},
                {"id": "cm7", "source": "node_mkt_transpose", "sourceHandle": "O", "target": "node_mkt_sample", "targetHandle": "I"},
                {"id": "cm8", "source": "node_mkt_sample", "sourceHandle": "O", "target": "node_mkt_crosstab", "targetHandle": "I"},
                {"id": "cm9", "source": "node_mkt_crosstab", "sourceHandle": "O", "target": "node_mkt_out", "targetHandle": "I"}
            ]
        },

        "multijoin_expense_reconciliation.json": {
            "name": "Workforce & Budget Multi-Join Reconciliation",
            "description": "Combines 3 distinct operational tables simultaneously using Join Multiple: merges employee payroll with departmental budget caps and operating expense ledgers, evaluates fiscal variances, and isolates over-budget departments.",
            "category": "finance",
            "tags": ["finance", "join_multiple", "multijoin", "budget", "variance", "workforce"],
            "difficulty": "advanced",
            "containers": [
                {
                    "id": "container_mj_1", "title": "Multi-Stream Fiscal Ledger Reconciliation",
                    "x": 60, "y": 60, "width": 1780, "height": 450,
                    "color": "rgba(139, 92, 246, 0.08)", "headerColor": "#7c3aed",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_mj_1",
                    "text": "### Multi-Table Reconciliation Architecture\n- **Inputs 1, 2, 3**: Ingests Employee Compensation, Department Budgets, and Operating Expenses.\n- **Join Multiple**: Unifies all 3 streams in a single multi-way join on `Department`.\n- **Formula**: Calculates Total Compensation `[BaseSalary] * (1.0 + [BonusPct])` and Total Operating Spend.\n- **Summarize & Filter**: Aggregates by Department and flags fiscal budget variances.",
                    "x": 60, "y": 530, "width": 520, "height": 150, "color": "#7c3aed"
                }
            ],
            "nodes": [
                {
                    "id": "node_mj_emp", "type": "input_data", "name": "Input 1: Employees (CSV)",
                    "x": 100, "y": 140,
                    "config": {"file_path": "employee_performance.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_mj_dept", "type": "input_data", "name": "Input 2: Budgets (CSV)",
                    "x": 100, "y": 260,
                    "config": {"file_path": "department_budgets.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_mj_exp", "type": "input_data", "name": "Input 3: OpEx (CSV)",
                    "x": 100, "y": 380,
                    "config": {"file_path": "department_operating_expenses.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_mj_join", "type": "join_multiple", "name": "Join Multiple (3 Tables)",
                    "x": 380, "y": 240,
                    "config": {
                        "join_mode": "specific_fields",
                        "join_keys": [{"1": "Department", "2": "Department", "3": "Department"}]
                    }
                },
                {
                    "id": "node_mj_select", "type": "select", "name": "Clean Joined Schema",
                    "x": 580, "y": 240,
                    "config": {
                        "fields": [
                            {"original": "Department", "keep": True, "rename": "Department", "type": "string"},
                            {"original": "EmployeeID", "keep": True, "rename": "EmployeeID", "type": "string"},
                            {"original": "EmployeeName", "keep": True, "rename": "EmployeeName", "type": "string"},
                            {"original": "BaseSalary", "keep": True, "rename": "BaseSalary", "type": "float"},
                            {"original": "BonusPct", "keep": True, "rename": "BonusPct", "type": "float"},
                            {"original": "BudgetCap", "keep": True, "rename": "BudgetCap", "type": "float"},
                            {"original": "DepartmentHead", "keep": True, "rename": "DepartmentHead", "type": "string"},
                            {"original": "SoftwareSpend", "keep": True, "rename": "SoftwareSpend", "type": "float"},
                            {"original": "TravelSpend", "keep": True, "rename": "TravelSpend", "type": "float"},
                            {"original": "EquipmentSpend", "keep": True, "rename": "EquipmentSpend", "type": "float"}
                        ]
                    }
                },
                {
                    "id": "node_mj_formula", "type": "formula", "name": "Compute Total Compensation",
                    "x": 780, "y": 240,
                    "config": {
                        "formulas": [
                            {"output_field": "TotalComp", "type": "float", "expression": "[BaseSalary] * (1.0 + [BonusPct])"}
                        ]
                    }
                },
                {
                    "id": "node_mj_sum", "type": "summarize", "name": "Aggregate by Department",
                    "x": 980, "y": 240,
                    "config": {
                        "actions": [
                            {"field": "Department", "action": "GroupBy", "output_name": "Department"},
                            {"field": "DepartmentHead", "action": "First", "output_name": "DepartmentHead"},
                            {"field": "BudgetCap", "action": "First", "output_name": "BudgetCap"},
                            {"field": "SoftwareSpend", "action": "First", "output_name": "SoftwareSpend"},
                            {"field": "TravelSpend", "action": "First", "output_name": "TravelSpend"},
                            {"field": "EmployeeID", "action": "Count", "output_name": "Headcount"},
                            {"field": "TotalComp", "action": "Sum", "output_name": "TotalPayroll"}
                        ]
                    }
                },
                {
                    "id": "node_mj_variance", "type": "formula", "name": "Calculate Budget Variance",
                    "x": 1180, "y": 240,
                    "config": {
                        "formulas": [
                            {"output_field": "TotalExpenditure", "type": "float", "expression": "[TotalPayroll] + [SoftwareSpend] + [TravelSpend]"},
                            {"output_field": "BudgetVariance", "type": "float", "expression": "[TotalExpenditure] - [BudgetCap]"}
                        ]
                    }
                },
                {
                    "id": "node_mj_sort", "type": "sort", "name": "Rank by Total Spend",
                    "x": 1380, "y": 240,
                    "config": {"sort_by": [{"column": "TotalExpenditure", "ascending": False}]}
                },
                {
                    "id": "node_mj_out", "type": "output_data", "name": "Export Fiscal Reconciliation",
                    "x": 1580, "y": 200,
                    "config": {"filename": "department_fiscal_reconciliation", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_mj_browse", "type": "browse", "name": "Browse Reconciled Budget Profile",
                    "x": 1580, "y": 320, "config": {}
                }
            ],
            "connections": [
                {"id": "cmj1", "source": "node_mj_emp", "sourceHandle": "O", "target": "node_mj_join", "targetHandle": "I"},
                {"id": "cmj2", "source": "node_mj_dept", "sourceHandle": "O", "target": "node_mj_join", "targetHandle": "I"},
                {"id": "cmj3", "source": "node_mj_exp", "sourceHandle": "O", "target": "node_mj_join", "targetHandle": "I"},
                {"id": "cmj4", "source": "node_mj_join", "sourceHandle": "J", "target": "node_mj_select", "targetHandle": "I"},
                {"id": "cmj5", "source": "node_mj_select", "sourceHandle": "O", "target": "node_mj_formula", "targetHandle": "I"},
                {"id": "cmj6", "source": "node_mj_formula", "sourceHandle": "O", "target": "node_mj_sum", "targetHandle": "I"},
                {"id": "cmj7", "source": "node_mj_sum", "sourceHandle": "O", "target": "node_mj_variance", "targetHandle": "I"},
                {"id": "cmj8", "source": "node_mj_variance", "sourceHandle": "O", "target": "node_mj_sort", "targetHandle": "I"},
                {"id": "cmj9", "source": "node_mj_sort", "sourceHandle": "O", "target": "node_mj_out", "targetHandle": "I"},
                {"id": "cmj10", "source": "node_mj_sort", "sourceHandle": "O", "target": "node_mj_browse", "targetHandle": "I"}
            ]
        },

        "data_quality_audit.json": {
            "name": "Data Quality Audit & Hygiene Scorecard",
            "description": "Profiles uncurated customer records for nulls, irregular text casing, whitespace padding, and duplicate emails. Separates clean records from flagged accounts and produces an executive audit scorecard.",
            "category": "data_quality",
            "tags": ["data_quality", "profiling", "clean", "unique", "nulls", "audit"],
            "difficulty": "beginner",
            "containers": [
                {
                    "id": "ctr_dq1", "title": "Data Cleansing & Duplicate Isolation",
                    "x": 60, "y": 60, "width": 860, "height": 380,
                    "color": "rgba(16, 185, 129, 0.08)", "headerColor": "#10b981",
                    "collapsed": False, "disabled": False
                },
                {
                    "id": "ctr_dq2", "title": "Validation Gate & Quality Scorecard",
                    "x": 960, "y": 60, "width": 880, "height": 380,
                    "color": "rgba(245, 158, 11, 0.08)", "headerColor": "#f59e0b",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_dq1",
                    "text": "### Data Quality Assurance Pipeline\n- **Auto Field**: Detects optimal column data types.\n- **Data Clean**: Strips whitespace padding and standardizes State casing.\n- **Unique**: Isolates duplicate customer accounts sharing the same email address.\n- **Formula**: Flags incomplete accounts missing Income or Phone credentials.\n- **Filter**: Routes validated records to clean storage and flags errors for audit.",
                    "x": 60, "y": 470, "width": 500, "height": 160, "color": "#10b981"
                }
            ],
            "nodes": [
                {
                    "id": "node_dq_in", "type": "input_data", "name": "Input Raw Accounts (CSV)",
                    "x": 100, "y": 170,
                    "config": {"file_path": "dirty_customer_data.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_dq_af", "type": "auto_field", "name": "Auto Detect Types",
                    "x": 280, "y": 170, "config": {"fields": []}
                },
                {
                    "id": "node_dq_clean", "type": "clean", "name": "Clean Strings & State",
                    "x": 460, "y": 170,
                    "config": {"columns": ["FullName", "Email", "State"], "trim_whitespace": True, "case_transformation": "title", "remove_empty_rows": False}
                },
                {
                    "id": "node_dq_unique", "type": "unique", "name": "Isolate Duplicate Emails",
                    "x": 660, "y": 170, "config": {"columns": ["Email"]}
                },
                {
                    "id": "node_dq_formula", "type": "formula", "name": "Evaluate Completeness",
                    "x": 1000, "y": 170,
                    "config": {
                        "formulas": [
                            {"output_field": "QualityStatus", "type": "string", "expression": "IF(IsNull([AnnualIncome]) OR IsNull([PhoneNumber]), \"Incomplete\", \"Verified\")"}
                        ]
                    }
                },
                {
                    "id": "node_dq_filter", "type": "filter", "name": "Route Verified vs Incomplete",
                    "x": 1200, "y": 170,
                    "config": {"mode": "basic", "logical_op": "AND", "conditions": [{"column": "QualityStatus", "operator": "==", "value": "Verified"}]}
                },
                {
                    "id": "node_dq_sum", "type": "summarize", "name": "Quality Audit Scorecard",
                    "x": 1400, "y": 280,
                    "config": {
                        "actions": [
                            {"field": "QualityStatus", "action": "GroupBy", "output_name": "QualityStatus"},
                            {"field": "CustomerID", "action": "Count", "output_name": "RecordCount"}
                        ]
                    }
                },
                {
                    "id": "node_dq_sort", "type": "sort", "name": "Sort Scorecard",
                    "x": 1600, "y": 280,
                    "config": {"sort_by": [{"column": "RecordCount", "ascending": False}]}
                },
                {
                    "id": "node_dq_out", "type": "output_data", "name": "Export Verified Accounts",
                    "x": 1420, "y": 140,
                    "config": {"filename": "verified_customer_accounts", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_dq_browse", "type": "browse", "name": "Browse Clean Dataset",
                    "x": 1620, "y": 140, "config": {}
                }
            ],
            "connections": [
                {"id": "cdq1", "source": "node_dq_in", "sourceHandle": "O", "target": "node_dq_af", "targetHandle": "I"},
                {"id": "cdq2", "source": "node_dq_af", "sourceHandle": "O", "target": "node_dq_clean", "targetHandle": "I"},
                {"id": "cdq3", "source": "node_dq_clean", "sourceHandle": "O", "target": "node_dq_unique", "targetHandle": "I"},
                {"id": "cdq4", "source": "node_dq_unique", "sourceHandle": "U", "target": "node_dq_formula", "targetHandle": "I"},
                {"id": "cdq5", "source": "node_dq_formula", "sourceHandle": "O", "target": "node_dq_filter", "targetHandle": "I"},
                {"id": "cdq6", "source": "node_dq_filter", "sourceHandle": "T", "target": "node_dq_out", "targetHandle": "I"},
                {"id": "cdq7", "source": "node_dq_out", "sourceHandle": "O", "target": "node_dq_browse", "targetHandle": "I"},
                {"id": "cdq8", "source": "node_dq_formula", "sourceHandle": "O", "target": "node_dq_sum", "targetHandle": "I"},
                {"id": "cdq9", "source": "node_dq_sum", "sourceHandle": "O", "target": "node_dq_sort", "targetHandle": "I"}
            ]
        },

        "sales_pipeline_report.json": {
            "name": "Sales Pipeline & Lead Velocity Report",
            "description": "Reads a CRM export, calculates probability-weighted deal revenue, excludes lost opportunities, summarizes pipeline velocity by representative, and calculates cumulative performance contributions.",
            "category": "sales",
            "tags": ["sales", "pipeline", "crm", "revenue", "multi_row_formula", "forecast"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "ctr_sp1", "title": "Pipeline Transformation & Weighted Valuation",
                    "x": 60, "y": 60, "width": 860, "height": 380,
                    "color": "rgba(59, 130, 246, 0.08)", "headerColor": "#3b82f6",
                    "collapsed": False, "disabled": False
                },
                {
                    "id": "ctr_sp2", "title": "Representative Ranking & Velocity Summary",
                    "x": 960, "y": 60, "width": 860, "height": 380,
                    "color": "rgba(34, 197, 94, 0.08)", "headerColor": "#16a34a",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_sp1",
                    "text": "### Sales Pipeline Forecasting Methodology\n- Ingests raw deal stages, accounts, and values from CRM.\n- Formula calculates Weighted Revenue = DealValue * Probability.\n- Filter eliminates closed-lost deals from active projections.\n- Summarize aggregates total and weighted pipeline per representative.\n- Multi-Row Formula computes cumulative running pipeline contributions.",
                    "x": 60, "y": 470, "width": 520, "height": 160, "color": "#3b82f6"
                }
            ],
            "nodes": [
                {
                    "id": "node_sp_in", "type": "input_data", "name": "Input CRM Deals (CSV)",
                    "x": 100, "y": 170,
                    "config": {"file_path": "crm_pipeline.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_sp_af", "type": "auto_field", "name": "Auto Detect Types",
                    "x": 280, "y": 170, "config": {"fields": []}
                },
                {
                    "id": "node_sp_clean", "type": "clean", "name": "Clean Rep & Stage Names",
                    "x": 460, "y": 170,
                    "config": {"columns": ["SalesRep", "Stage", "Region"], "trim_whitespace": True, "case_transformation": "title", "remove_empty_rows": False}
                },
                {
                    "id": "node_sp_formula", "type": "formula", "name": "Calculate Weighted Value",
                    "x": 660, "y": 170,
                    "config": {
                        "formulas": [
                            {"output_field": "WeightedRevenue", "type": "float", "expression": "[DealValue] * [Probability]"}
                        ]
                    }
                },
                {
                    "id": "node_sp_filter", "type": "filter", "name": "Filter Out Closed Lost",
                    "x": 1000, "y": 170,
                    "config": {"mode": "basic", "logical_op": "AND", "conditions": [{"column": "Stage", "operator": "!=", "value": "Closed Lost"}]}
                },
                {
                    "id": "node_sp_sum", "type": "summarize", "name": "Summarize by Sales Rep",
                    "x": 1180, "y": 170,
                    "config": {
                        "actions": [
                            {"field": "SalesRep", "action": "GroupBy", "output_name": "SalesRep"},
                            {"field": "DealValue", "action": "Sum", "output_name": "PipelineTotal"},
                            {"field": "WeightedRevenue", "action": "Sum", "output_name": "WeightedPipeline"},
                            {"field": "DealID", "action": "Count", "output_name": "OpportunityCount"}
                        ]
                    }
                },
                {
                    "id": "node_sp_sort", "type": "sort", "name": "Rank by Weighted Pipeline",
                    "x": 1360, "y": 170,
                    "config": {"sort_by": [{"column": "WeightedPipeline", "ascending": False}]}
                },
                {
                    "id": "node_sp_multirow", "type": "multi_row_formula", "name": "Cumulative Contribution",
                    "x": 1540, "y": 170,
                    "config": {
                        "output_field": "CumulativeWeighted", "is_new_field": True, "output_type": "float",
                        "values_for_rows_not_exist": "0", "group_by_fields": [], "expression": "[Row-1:CumulativeWeighted] + [WeightedPipeline]"
                    }
                },
                {
                    "id": "node_sp_out", "type": "output_data", "name": "Export Pipeline Forecast",
                    "x": 1720, "y": 170,
                    "config": {"filename": "sales_pipeline_forecast", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_sp_browse", "type": "browse", "name": "Browse Forecast Profile",
                    "x": 1720, "y": 280, "config": {}
                }
            ],
            "connections": [
                {"id": "csp1", "source": "node_sp_in", "sourceHandle": "O", "target": "node_sp_af", "targetHandle": "I"},
                {"id": "csp2", "source": "node_sp_af", "sourceHandle": "O", "target": "node_sp_clean", "targetHandle": "I"},
                {"id": "csp3", "source": "node_sp_clean", "sourceHandle": "O", "target": "node_sp_formula", "targetHandle": "I"},
                {"id": "csp4", "source": "node_sp_formula", "sourceHandle": "O", "target": "node_sp_filter", "targetHandle": "I"},
                {"id": "csp5", "source": "node_sp_filter", "sourceHandle": "T", "target": "node_sp_sum", "targetHandle": "I"},
                {"id": "csp6", "source": "node_sp_sum", "sourceHandle": "O", "target": "node_sp_sort", "targetHandle": "I"},
                {"id": "csp7", "source": "node_sp_sort", "sourceHandle": "O", "target": "node_sp_multirow", "targetHandle": "I"},
                {"id": "csp8", "source": "node_sp_multirow", "sourceHandle": "O", "target": "node_sp_out", "targetHandle": "I"},
                {"id": "csp9", "source": "node_sp_multirow", "sourceHandle": "O", "target": "node_sp_browse", "targetHandle": "I"}
            ]
        },

        "customer_rfm_segmentation.json": {
            "name": "Customer RFM Segmentation",
            "description": "Computes RFM (Recency, Frequency, Monetary) scores from order history to segment customers into High Value, At Risk, Lost, and New categories for targeted marketing.",
            "category": "sales",
            "tags": ["sales", "rfm", "segmentation", "retention", "customer", "datetime"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "ctr_rfm1", "title": "Order Ingestion & Customer Aggregation",
                    "x": 60, "y": 60, "width": 860, "height": 380,
                    "color": "rgba(59, 130, 246, 0.08)", "headerColor": "#3b82f6",
                    "collapsed": False, "disabled": False
                },
                {
                    "id": "ctr_rfm2", "title": "RFM Scoring & Strategic Segmentation",
                    "x": 960, "y": 60, "width": 860, "height": 380,
                    "color": "rgba(245, 158, 11, 0.08)", "headerColor": "#f59e0b",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_rfm1",
                    "text": "### RFM Segmentation Pipeline\n- Ingests order history records from orders.csv.\n- DateTime standardizes OrderDate strings to ISO dates.\n- Summarize calculates customer OrderCount, TotalSpend, and LastOrderDate.\n- Formula scores Frequency and Monetary value, assigning actionable segment labels.",
                    "x": 60, "y": 470, "width": 520, "height": 160, "color": "#f59e0b"
                }
            ],
            "nodes": [
                {
                    "id": "node_rfm_in", "type": "input_data", "name": "Input Order History (CSV)",
                    "x": 100, "y": 170,
                    "config": {"file_path": "orders.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_rfm_af", "type": "auto_field", "name": "Auto Detect Types",
                    "x": 280, "y": 170, "config": {"fields": []}
                },
                {
                    "id": "node_rfm_dt", "type": "date_time", "name": "Parse Order Dates",
                    "x": 460, "y": 170,
                    "config": {"column": "OrderDate", "conversion_type": "string_to_date", "format_template": "yyyy-MM-dd", "output_column": "OrderDate_ISO"}
                },
                {
                    "id": "node_rfm_sum", "type": "summarize", "name": "Aggregate Customer History",
                    "x": 660, "y": 170,
                    "config": {
                        "actions": [
                            {"field": "CustomerID", "action": "GroupBy", "output_name": "CustomerID"},
                            {"field": "CustomerName", "action": "First", "output_name": "CustomerName"},
                            {"field": "OrderDate_ISO", "action": "Max", "output_name": "LastOrderDate"},
                            {"field": "OrderID", "action": "Count", "output_name": "OrderCount"},
                            {"field": "OrderValue", "action": "Sum", "output_name": "TotalSpend"},
                            {"field": "OrderValue", "action": "Average", "output_name": "AvgOrderValue"}
                        ]
                    }
                },
                {
                    "id": "node_rfm_formula", "type": "formula", "name": "Calculate RFM Tiers",
                    "x": 1000, "y": 170,
                    "config": {
                        "formulas": [
                            {"output_field": "FrequencyScore", "type": "integer", "expression": "IF([OrderCount] >= 6, 5, IF([OrderCount] >= 4, 4, IF([OrderCount] >= 2, 3, 2)))"},
                            {"output_field": "MonetaryScore", "type": "integer", "expression": "IF([TotalSpend] >= 3000, 5, IF([TotalSpend] >= 1500, 4, IF([TotalSpend] >= 600, 3, 2)))"}
                        ]
                    }
                },
                {
                    "id": "node_rfm_seg", "type": "formula", "name": "Assign Segment Category",
                    "x": 1200, "y": 170,
                    "config": {
                        "formulas": [
                            {"output_field": "Segment", "type": "string", "expression": "IF([FrequencyScore] >= 4 AND [MonetaryScore] >= 4, \"High Value VIP\", IF([FrequencyScore] >= 3, \"Promising Growth\", \"Occasional Buyer\"))"}
                        ]
                    }
                },
                {
                    "id": "node_rfm_sort", "type": "sort", "name": "Rank by Total Spend",
                    "x": 1380, "y": 170,
                    "config": {"sort_by": [{"column": "TotalSpend", "ascending": False}]}
                },
                {
                    "id": "node_rfm_out", "type": "output_data", "name": "Export Segmented Customers",
                    "x": 1560, "y": 170,
                    "config": {"filename": "customer_rfm_segments", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_rfm_browse", "type": "browse", "name": "Browse RFM Distribution",
                    "x": 1560, "y": 280, "config": {}
                }
            ],
            "connections": [
                {"id": "crfm1", "source": "node_rfm_in", "sourceHandle": "O", "target": "node_rfm_af", "targetHandle": "I"},
                {"id": "crfm2", "source": "node_rfm_af", "sourceHandle": "O", "target": "node_rfm_dt", "targetHandle": "I"},
                {"id": "crfm3", "source": "node_rfm_dt", "sourceHandle": "O", "target": "node_rfm_sum", "targetHandle": "I"},
                {"id": "crfm4", "source": "node_rfm_sum", "sourceHandle": "O", "target": "node_rfm_formula", "targetHandle": "I"},
                {"id": "crfm5", "source": "node_rfm_formula", "sourceHandle": "O", "target": "node_rfm_seg", "targetHandle": "I"},
                {"id": "crfm6", "source": "node_rfm_seg", "sourceHandle": "O", "target": "node_rfm_sort", "targetHandle": "I"},
                {"id": "crfm7", "source": "node_rfm_sort", "sourceHandle": "O", "target": "node_rfm_out", "targetHandle": "I"},
                {"id": "crfm8", "source": "node_rfm_sort", "sourceHandle": "O", "target": "node_rfm_browse", "targetHandle": "I"}
            ]
        },

        "customer_sentiment_analysis.json": {
            "name": "Customer Sentiment Analysis",
            "description": "Reads customer product feedback, cleans text, executes AI sentiment classification using LLM Process, and routes negative reviews for customer escalation.",
            "category": "ai_llm",
            "tags": ["ai", "llm", "sentiment", "nlp", "reviews", "customer"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "ctr_s1", "title": "Feedback Ingestion & Text Preparation",
                    "x": 60, "y": 60, "width": 640, "height": 340,
                    "color": "rgba(139, 92, 246, 0.08)", "headerColor": "#8b5cf6",
                    "collapsed": False, "disabled": False
                },
                {
                    "id": "ctr_s2", "title": "AI Classification & Customer Escalation",
                    "x": 740, "y": 60, "width": 1040, "height": 340,
                    "color": "rgba(239, 68, 68, 0.08)", "headerColor": "#ef4444",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_s1",
                    "text": "### AI Sentiment Pipeline Architecture\n- Ingests customer review records from customer_reviews.csv.\n- Data Clean strips leading and trailing whitespaces.\n- LLM Process classifies sentiment with fallback for offline mode (`on_error='null'`).\n- Filter isolates low-rated customer accounts (StarRating <= 2) for retention review.",
                    "x": 60, "y": 430, "width": 520, "height": 160, "color": "#8b5cf6"
                }
            ],
            "nodes": [
                {
                    "id": "node_s_in", "type": "input_data", "name": "Input Customer Reviews (CSV)",
                    "x": 100, "y": 170,
                    "config": {"file_path": "customer_reviews.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_s_af", "type": "auto_field", "name": "Auto Detect Types",
                    "x": 280, "y": 170, "config": {"fields": []}
                },
                {
                    "id": "node_s_clean", "type": "clean", "name": "Trim Review Text",
                    "x": 460, "y": 170,
                    "config": {"columns": ["ReviewText"], "trim_whitespace": True, "case_transformation": "none", "remove_empty_rows": True}
                },
                {
                    "id": "node_s_llm", "type": "llm_process", "name": "AI Sentiment Classifier",
                    "x": 780, "y": 170,
                    "config": {
                        "provider_type": "ollama", "model": "llama3.2",
                        "user_prompt_template": "Classify the sentiment of this review as Positive, Neutral, or Negative:\n{{[ReviewText]}}",
                        "output_column": "Sentiment", "on_error": "null"
                    }
                },
                {
                    "id": "node_s_filter", "type": "filter", "name": "Escalate Low Ratings (<= 2 Stars)",
                    "x": 1000, "y": 170,
                    "config": {"mode": "basic", "logical_op": "AND", "conditions": [{"column": "StarRating", "operator": "<=", "value": "2"}]}
                },
                {
                    "id": "node_s_sort", "type": "sort", "name": "Sort by Rating Asc",
                    "x": 1200, "y": 170,
                    "config": {"sort_by": [{"column": "StarRating", "ascending": True}]}
                },
                {
                    "id": "node_s_out", "type": "output_data", "name": "Export Escalation Queue",
                    "x": 1400, "y": 170,
                    "config": {"filename": "negative_review_escalations", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_s_browse", "type": "browse", "name": "Browse Escalation Queue",
                    "x": 1580, "y": 170, "config": {}
                }
            ],
            "connections": [
                {"id": "cs1", "source": "node_s_in", "sourceHandle": "O", "target": "node_s_af", "targetHandle": "I"},
                {"id": "cs2", "source": "node_s_af", "sourceHandle": "O", "target": "node_s_clean", "targetHandle": "I"},
                {"id": "cs3", "source": "node_s_clean", "sourceHandle": "O", "target": "node_s_llm", "targetHandle": "I"},
                {"id": "cs4", "source": "node_s_llm", "sourceHandle": "O", "target": "node_s_filter", "targetHandle": "I"},
                {"id": "cs5", "source": "node_s_filter", "sourceHandle": "T", "target": "node_s_sort", "targetHandle": "I"},
                {"id": "cs6", "source": "node_s_sort", "sourceHandle": "O", "target": "node_s_out", "targetHandle": "I"},
                {"id": "cs7", "source": "node_s_out", "sourceHandle": "O", "target": "node_s_browse", "targetHandle": "I"}
            ]
        },

        "invoice_data_extraction.json": {
            "name": "Invoice Data Extraction",
            "description": "Uses an LLM to extract structured fields (vendor name, invoice number, total amount, due date) from free-text invoice descriptions into a clean structured table.",
            "category": "ai_llm",
            "tags": ["ai", "llm", "invoice", "extraction", "ap", "finance"],
            "difficulty": "intermediate",
            "containers": [
                {
                    "id": "ctr_ie1", "title": "Unstructured Invoices Ingestion",
                    "x": 60, "y": 60, "width": 520, "height": 340,
                    "color": "rgba(139, 92, 246, 0.08)", "headerColor": "#8b5cf6",
                    "collapsed": False, "disabled": False
                },
                {
                    "id": "ctr_ie2", "title": "AI Information Extraction & AP Ledger",
                    "x": 620, "y": 60, "width": 1180, "height": 340,
                    "color": "rgba(59, 130, 246, 0.08)", "headerColor": "#3b82f6",
                    "collapsed": False, "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_ie1",
                    "text": "### Invoice Processing Methodology\n- Reads unstructured invoice narrative texts from invoices_raw.csv.\n- Trims extra whitespace with Data Clean.\n- Calls LLM Process to extract accounting entities into structured fields.\n- Formulas and filters validate records and prepare an AP payment ledger.",
                    "x": 60, "y": 430, "width": 520, "height": 160, "color": "#8b5cf6"
                }
            ],
            "nodes": [
                {
                    "id": "node_ie_in", "type": "input_data", "name": "Input Raw Invoices (CSV)",
                    "x": 100, "y": 170,
                    "config": {"file_path": "invoices_raw.csv", "file_type": "csv", "delimiter": ",", "has_header": True}
                },
                {
                    "id": "node_ie_clean", "type": "clean", "name": "Trim Invoice Text",
                    "x": 300, "y": 170,
                    "config": {"columns": ["InvoiceText"], "trim_whitespace": True, "case_transformation": "none", "remove_empty_rows": True}
                },
                {
                    "id": "node_ie_llm", "type": "llm_process", "name": "AI Field Extractor",
                    "x": 660, "y": 170,
                    "config": {
                        "provider_type": "ollama", "model": "llama3.2",
                        "user_prompt_template": "Extract invoice information from:\n{{[InvoiceText]}}\nFormat as JSON with keys: vendor, invoice_num, amount.",
                        "output_column": "ExtractedJSON", "on_error": "null"
                    }
                },
                {
                    "id": "node_ie_formula", "type": "formula", "name": "Tag Processing Status",
                    "x": 880, "y": 170,
                    "config": {
                        "formulas": [
                            {"output_field": "AP_BatchID", "type": "string", "expression": "'BATCH-2024Q4'"}
                        ]
                    }
                },
                {
                    "id": "node_ie_filter", "type": "filter", "name": "Filter Processed Records",
                    "x": 1080, "y": 170,
                    "config": {"mode": "basic", "logical_op": "AND", "conditions": [{"column": "AP_BatchID", "operator": "==", "value": "BATCH-2024Q4"}]}
                },
                {
                    "id": "node_ie_sort", "type": "sort", "name": "Sort by Invoice ID",
                    "x": 1280, "y": 170,
                    "config": {"sort_by": [{"column": "InvoiceID", "ascending": True}]}
                },
                {
                    "id": "node_ie_out", "type": "output_data", "name": "Export Structured AP Ledger",
                    "x": 1480, "y": 170,
                    "config": {"filename": "structured_ap_ledger", "format": "csv", "write_mode": "overwrite"}
                },
                {
                    "id": "node_ie_browse", "type": "browse", "name": "Browse AP Ledger",
                    "x": 1660, "y": 170, "config": {}
                }
            ],
            "connections": [
                {"id": "cie1", "source": "node_ie_in", "sourceHandle": "O", "target": "node_ie_clean", "targetHandle": "I"},
                {"id": "cie2", "source": "node_ie_clean", "sourceHandle": "O", "target": "node_ie_llm", "targetHandle": "I"},
                {"id": "cie3", "source": "node_ie_llm", "sourceHandle": "O", "target": "node_ie_formula", "targetHandle": "I"},
                {"id": "cie4", "source": "node_ie_formula", "sourceHandle": "O", "target": "node_ie_filter", "targetHandle": "I"},
                {"id": "cie5", "source": "node_ie_filter", "sourceHandle": "T", "target": "node_ie_sort", "targetHandle": "I"},
                {"id": "cie6", "source": "node_ie_sort", "sourceHandle": "O", "target": "node_ie_out", "targetHandle": "I"},
                {"id": "cie7", "source": "node_ie_out", "sourceHandle": "O", "target": "node_ie_browse", "targetHandle": "I"}
            ]
        }
    }
