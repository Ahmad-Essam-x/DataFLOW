"""
Sample Data & Pre-built Workflows Generator.
Creates realistic sample CSV and Excel datasets along with ready-to-run demo workflows
testing 100% of the tools in the product across exactly 3 curated pipelines.
"""
import os
import json
import random
import datetime
import numpy as np
import pandas as pd


def ensure_sample_data(data_dir: str, workflows_dir: str):
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(workflows_dir, exist_ok=True)

    # Legacy cleanup: Remove obsolete sample workflows
    obsolete_wf = os.path.join(workflows_dir, "data_cleaning_and_deduplication.json")
    if os.path.exists(obsolete_wf):
        try:
            os.remove(obsolete_wf)
        except OSError:
            pass

    # -------------------------------------------------------------------------
    # 1. Dataset: sales_orders.csv (Customer 360 & Sales Performance)
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

        df_sales = pd.DataFrame(orders)
        df_sales.to_csv(sales_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 2. Dataset: warehouse_inventory.xlsx (Inventory & Supplier Reconciliation)
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

        # Add intentional duplicates for Unique tool testing
        inventory.append(inventory[0].copy())
        inventory.append(inventory[1].copy())

        df_inv = pd.DataFrame(inventory)
        with pd.ExcelWriter(inv_xlsx_path, engine="openpyxl") as writer:
            df_inv.to_excel(writer, sheet_name="Inventory", index=False)

    # -------------------------------------------------------------------------
    # 3. Dataset: quarterly_campaign_responses.csv (Marketing Attribution)
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

        df_resp = pd.DataFrame(responses)
        df_resp.to_csv(camp_csv_path, index=False)

    # -------------------------------------------------------------------------
    # 4. Fallback/Legacy Datasets: customers.csv & orders.xlsx
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
    # 5. Workflow 1: Customer Sales Analysis
    # -------------------------------------------------------------------------
    wf1_path = os.path.join(workflows_dir, "sales_customer_enrichment.json")
    if not os.path.exists(wf1_path):
        wf1 = {
            "name": "Customer Sales Analysis",
            "description": "Cleans customer records, standardizes order dates with DateTime parsing, calculates net revenues and margins, filters high-value orders, and summarizes regional performance.",
            "containers": [
                {
                    "id": "container_sales_1",
                    "title": "Sales Performance & Customer Enrichment",
                    "x": 60,
                    "y": 60,
                    "width": 1840,
                    "height": 380,
                    "color": "rgba(34, 197, 94, 0.08)",
                    "headerColor": "#16a34a",
                    "collapsed": False,
                    "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_sales_1",
                    "text": "### Executive Sales KPIs\n- Auto Field optimizes incoming types automatically.\n- Data Clean trims whitespace and title-cases region names.\n- DateTime normalizes dates into ISO format.\n- Formula calculates Net Revenue after discounts.\n- High-value transactions (> $500) are aggregated by Region and Segment.\n- Multi-Row Formula calculates running cumulative revenues across segments.",
                    "x": 60,
                    "y": 460,
                    "width": 420,
                    "height": 140,
                    "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_sales_in",
                    "type": "input_data",
                    "name": "Input Sales Orders (CSV)",
                    "x": 100,
                    "y": 180,
                    "config": {
                        "file_path": "sales_orders.csv",
                        "file_type": "csv",
                        "delimiter": ",",
                        "has_header": True
                    }
                },
                {
                    "id": "node_sales_autofield",
                    "type": "auto_field",
                    "name": "Auto Field Types",
                    "x": 280,
                    "y": 180,
                    "config": {
                        "fields": []
                    }
                },
                {
                    "id": "node_sales_clean",
                    "type": "clean",
                    "name": "Clean Text & Region",
                    "x": 460,
                    "y": 180,
                    "config": {
                        "columns": ["CustomerNotes", "Region"],
                        "trim_whitespace": True,
                        "case_transformation": "title",
                        "remove_empty_rows": False
                    }
                },
                {
                    "id": "node_sales_dt",
                    "type": "date_time",
                    "name": "Parse OrderDate",
                    "x": 640,
                    "y": 180,
                    "config": {
                        "column": "OrderDate",
                        "conversion_type": "string_to_date",
                        "format_template": "yyyy-MM-dd",
                        "output_column": "OrderDate_ISO"
                    }
                },
                {
                    "id": "node_sales_formula",
                    "type": "formula",
                    "name": "Calculate Net Revenue",
                    "x": 820,
                    "y": 180,
                    "config": {
                        "formulas": [
                            {
                                "output_field": "GrossAmount",
                                "type": "float",
                                "expression": "[Quantity] * [UnitPrice]"
                            },
                            {
                                "output_field": "NetAmount",
                                "type": "float",
                                "expression": "[GrossAmount] * (1.0 - [Discount])"
                            }
                        ]
                    }
                },
                {
                    "id": "node_sales_filter",
                    "type": "filter",
                    "name": "Filter Orders > $500",
                    "x": 1000,
                    "y": 180,
                    "config": {
                        "mode": "basic",
                        "logical_op": "AND",
                        "conditions": [
                            {"column": "NetAmount", "operator": ">", "value": "500"}
                        ]
                    }
                },
                {
                    "id": "node_sales_summarize",
                    "type": "summarize",
                    "name": "Summarize by Region & Segment",
                    "x": 1200,
                    "y": 140,
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
                    "id": "node_sort_1",
                    "type": "sort",
                    "name": "Sort Revenue Desc",
                    "x": 1380,
                    "y": 140,
                    "config": {
                        "sort_by": [
                            {"column": "TotalRevenue", "ascending": False}
                        ]
                    }
                },
                {
                    "id": "node_sales_multirow",
                    "type": "multi_row_formula",
                    "name": "Cumulative Sales Total",
                    "x": 1560,
                    "y": 140,
                    "config": {
                        "output_field": "CumulativeRevenue",
                        "is_new_field": True,
                        "output_type": "float",
                        "values_for_rows_not_exist": "0",
                        "group_by_fields": [],
                        "expression": "[Row-1:CumulativeRevenue] + [TotalRevenue]"
                    }
                },
                {
                    "id": "node_sales_out",
                    "type": "output_data",
                    "name": "Export Sales Summary",
                    "x": 1740,
                    "y": 140,
                    "config": {
                        "filename": "regional_sales_summary",
                        "format": "csv",
                        "write_mode": "overwrite"
                    }
                },
                {
                    "id": "node_sales_browse",
                    "type": "browse",
                    "name": "Browse Sales Profile",
                    "x": 1740,
                    "y": 260,
                    "config": {}
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
        }
        with open(wf1_path, "w", encoding="utf-8") as f:
            json.dump(wf1, f, indent=2)

    # -------------------------------------------------------------------------
    # 6. Workflow 2: Inventory & Supplier Reconciliation
    # -------------------------------------------------------------------------
    wf2_path = os.path.join(workflows_dir, "inventory_supplier_reconciliation.json")
    if not os.path.exists(wf2_path):
        wf2 = {
            "name": "Inventory & Supplier Reconciliation",
            "description": "Splits composite warehouse SKUs, deduplicates counts, reconciles stock levels with supplier lead times via Join, cross-appends holding parameters, and generates audit ledger tracking IDs.",
            "containers": [
                {
                    "id": "container_inv_1",
                    "title": "Supply Chain & Warehouse Audit Ledger",
                    "x": 60,
                    "y": 60,
                    "width": 1480,
                    "height": 420,
                    "color": "rgba(168, 85, 247, 0.08)",
                    "headerColor": "#9333ea",
                    "collapsed": False,
                    "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_inv_1",
                    "text": "### Inventory Audit Protocol\n- Excel stock counts are parsed with Text to Columns into Supplier, Category, and Batch.\n- Unique separates distinct stock counts from duplicate entries.\n- Join matches warehouse quantities against Supplier contract terms.\n- Append Fields cross-appends corporate holding cost benchmarks.",
                    "x": 60,
                    "y": 500,
                    "width": 460,
                    "height": 140,
                    "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_inv_in",
                    "type": "input_data",
                    "name": "Input Warehouse Stock (Excel)",
                    "x": 100,
                    "y": 160,
                    "config": {
                        "file_path": "warehouse_inventory.xlsx",
                        "file_type": "excel",
                        "sheet_name": "Inventory",
                        "has_header": True
                    }
                },
                {
                    "id": "node_inv_split",
                    "type": "text_to_columns",
                    "name": "Split Batch Code",
                    "x": 280,
                    "y": 160,
                    "config": {
                        "column": "CompositeBatchCode",
                        "delimiters": "-",
                        "split_type": "columns",
                        "num_columns": 3,
                        "root_name": "BatchPart_",
                        "extra_characters": "last"
                    }
                },
                {
                    "id": "node_inv_unique",
                    "type": "unique",
                    "name": "Deduplicate Stock Counts",
                    "x": 460,
                    "y": 160,
                    "config": {
                        "columns": ["SKU", "WarehouseLocation"]
                    }
                },
                {
                    "id": "node_suppliers_input",
                    "type": "text_input",
                    "name": "Supplier Reference Catalog",
                    "x": 460,
                    "y": 320,
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
                    "id": "node_inv_join",
                    "type": "join",
                    "name": "Join Stock with Suppliers",
                    "x": 680,
                    "y": 200,
                    "config": {
                        "join_mode": "specific_fields",
                        "join_keys": [
                            {"left_key": "BatchPart_1", "right_key": "SupplierID"}
                        ]
                    }
                },
                {
                    "id": "node_inv_params",
                    "type": "text_input",
                    "name": "Audit Rate Parameters",
                    "x": 680,
                    "y": 340,
                    "config": {
                        "columns": ["HoldingRate", "Currency"],
                        "data": [
                            [0.085, "USD"]
                        ]
                    }
                },
                {
                    "id": "node_inv_append",
                    "type": "append_fields",
                    "name": "Append Financial Parameters",
                    "x": 900,
                    "y": 220,
                    "config": {
                        "cartesian_mode": "error_16",
                        "source_prefix": "Param_"
                    }
                },
                {
                    "id": "node_inv_recid",
                    "type": "record_id",
                    "name": "Generate Audit Ledger ID",
                    "x": 1120,
                    "y": 220,
                    "config": {
                        "column_name": "AuditTrackingID",
                        "start_value": 1001,
                        "position": "first"
                    }
                },
                {
                    "id": "node_inv_out",
                    "type": "output_data",
                    "name": "Export Audit Ledger",
                    "x": 1320,
                    "y": 220,
                    "config": {
                        "filename": "inventory_audit_ledger",
                        "format": "csv",
                        "write_mode": "overwrite"
                    }
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
                {"id": "ci8", "source": "node_inv_recid", "sourceHandle": "O", "target": "node_inv_out", "targetHandle": "I"}
            ]
        }
        with open(wf2_path, "w", encoding="utf-8") as f:
            json.dump(wf2, f, indent=2)

    # -------------------------------------------------------------------------
    # 7. Workflow 3: Marketing Attribution & Survey Matrix
    # -------------------------------------------------------------------------
    wf3_path = os.path.join(workflows_dir, "marketing_campaign_attribution.json")
    if not os.path.exists(wf3_path):
        wf3 = {
            "name": "Marketing Attribution & Survey Matrix",
            "description": "Unions web and mobile survey streams, replaces campaign codes with friendly names, selects key attributes, unpivots quarterly ratings with Transpose, samples records, and pivots into a Regional cross-tab matrix.",
            "containers": [
                {
                    "id": "container_mkt_1",
                    "title": "Marketing Attribution & Pivoting Pipeline",
                    "x": 60,
                    "y": 60,
                    "width": 1760,
                    "height": 420,
                    "color": "rgba(249, 115, 22, 0.08)",
                    "headerColor": "#f97316",
                    "collapsed": False,
                    "disabled": False
                }
            ],
            "comments": [
                {
                    "id": "comment_mkt_1",
                    "text": "### Survey Analysis Methodology\n- Web survey responses are unioned with mobile telemetry records.\n- Find Replace maps campaign codes to human-readable names.\n- Select casts scores and standardizes headers.\n- Multi-Field Formula applies batch numeric transformations to Q1-Q4 scores.\n- Transpose melts Q1-Q4 ratings into tall pairs.\n- Cross Tab aggregates average ratings into an Executive Regional Grid.",
                    "x": 60,
                    "y": 500,
                    "width": 460,
                    "height": 140,
                    "color": "#eab308"
                }
            ],
            "nodes": [
                {
                    "id": "node_mkt_in",
                    "type": "input_data",
                    "name": "Input Web Responses (CSV)",
                    "x": 100,
                    "y": 150,
                    "config": {
                        "file_path": "quarterly_campaign_responses.csv",
                        "file_type": "csv",
                        "delimiter": ",",
                        "has_header": True
                    }
                },
                {
                    "id": "node_mkt_mobile",
                    "type": "text_input",
                    "name": "Mobile Event Responses",
                    "x": 100,
                    "y": 300,
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
                    "id": "node_mkt_union",
                    "type": "union",
                    "name": "Union Web & Mobile Logs",
                    "x": 300,
                    "y": 210,
                    "config": {
                        "mode": "by_name",
                        "non_matching": "all"
                    }
                },
                {
                    "id": "node_mkt_lookup",
                    "type": "text_input",
                    "name": "Campaign Dictionary",
                    "x": 300,
                    "y": 340,
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
                    "id": "node_mkt_fr",
                    "type": "find_replace",
                    "name": "Replace Campaign Codes",
                    "x": 500,
                    "y": 240,
                    "config": {
                        "find_field": "CampaignCode",
                        "find_value_field": "Code",
                        "action": "replace",
                        "replace_with_field": "CampaignName",
                        "search_mode": "entire_field",
                        "case_sensitive": False
                    }
                },
                {
                    "id": "node_mkt_select",
                    "type": "select",
                    "name": "Select & Format Fields",
                    "x": 680,
                    "y": 240,
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
                    "id": "node_mkt_multifield",
                    "type": "multi_field_formula",
                    "name": "Standardize Scores",
                    "x": 860,
                    "y": 240,
                    "config": {
                        "selected_fields": ["Q1", "Q2", "Q3", "Q4"],
                        "field_type_filter": "numeric",
                        "output_mode": "update",
                        "output_prefix": "",
                        "output_suffix": "",
                        "output_type": "float",
                        "expression": "[_CurrentField_] * 1.0"
                    }
                },
                {
                    "id": "node_mkt_transpose",
                    "type": "transpose",
                    "name": "Unpivot Quarterly Scores",
                    "x": 1040,
                    "y": 240,
                    "config": {
                        "key_columns": ["UserEmail", "CampaignName", "Region"],
                        "data_columns": ["Q1", "Q2", "Q3", "Q4"],
                        "name_column": "Quarter",
                        "value_column": "Score"
                    }
                },
                {
                    "id": "node_mkt_sample",
                    "type": "sample",
                    "name": "Sample Validation Rows",
                    "x": 1220,
                    "y": 240,
                    "config": {
                        "sample_type": "first_n",
                        "n_records": 100
                    }
                },
                {
                    "id": "node_mkt_crosstab",
                    "type": "crosstab",
                    "name": "Pivot to Regional Matrix",
                    "x": 1420,
                    "y": 240,
                    "config": {
                        "group_by": ["Region"],
                        "header_field": "CampaignName",
                        "value_field": "Score",
                        "agg_func": "mean"
                    }
                },
                {
                    "id": "node_mkt_out",
                    "type": "output_data",
                    "name": "Export Attribution Matrix",
                    "x": 1620,
                    "y": 240,
                    "config": {
                        "filename": "campaign_attribution_matrix",
                        "format": "csv",
                        "write_mode": "overwrite"
                    }
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
        }
        with open(wf3_path, "w", encoding="utf-8") as f:
            json.dump(wf3, f, indent=2)
