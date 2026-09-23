# Antigravity DataFlow (Alteryx-like Visual ETL Local App)

A drag-and-drop data processing application that reproduces the core workflow, node canvas, and data profiling experience of Alteryx Designer. Completely local, fast, and powered by Python (Pandas & OpenPyXL).

---

## Quick Start

### 1. Launch the Application

**Option A: Double-click `run.bat` (Windows)**

**Option B: Terminal Command**
```powershell
& "C:\Users\Ahmed Gad\anaconda3\python.exe" run.py
```
Or if Python is in your PATH:
```bash
python run.py
```

The application will start the local server and automatically open your default browser at:
`http://127.0.0.1:5000`

---

## Key Features & Tool Palette

### 1. In / Out (Green)
* **Input Data**: Ingest data from CSV, TSV, or Excel (`.xlsx`, `.xls`) files. Includes automatic header detection, delimiter choices, and sheet selection.
* **Output Data**: Export your pipeline results directly to CSV or Excel (`.xlsx`).

### 2. Preparation (Blue)
* **Select**: Check/uncheck columns to keep or drop, rename column headers, reorder fields, and cast data types (`String`, `Integer`, `Float`, `Boolean`, `DateTime`).
* **Filter**: Visual condition builder with AND/OR logic (`=, !=, >, <, >=, <=, contains, starts_with, ends_with, is_null, not_null, in`) or custom expressions. Features Alteryx-authentic dual output anchors:
  * `T` (True): Records matching the filter criteria.
  * `F` (False): Records not matching the filter criteria.
* **Formula**: Compute new columns or update existing ones using math expressions (`+ - * /`), string functions (`UPPER`, `LOWER`, `TRIM`, `LENGTH`, `ROUND`), and conditionals (`IF(...)`).
* **Sort**: Multi-column sorting in ascending or descending sequence.
* **Data Clean**: Trim whitespace, normalize casing (UPPERCASE, lowercase, Title Case), remove empty rows, and impute null values (fill with constant, mean, or median).
* **Unique**: Identify duplicate rows based on key columns with dual output anchors:
  * `U` (Unique): First unique occurrence of each record.
  * `D` (Duplicate): All duplicate records.

### 3. Join (Purple)
* **Join**: Multi-key join matching with authentic Alteryx 3-way output anchors:
  * `J` (Joined): Records that matched on key fields.
  * `L` (Left Unmatched): Unmatched records from Left input.
  * `R` (Right Unmatched): Unmatched records from Right input.
* **Union**: Stack multiple datasets vertically by column name or by column position.

### 4. Transform (Orange)
* **Summarize**: Group by fields and calculate aggregate metrics (`Sum`, `Average/Mean`, `Count`, `Count Distinct`, `Min`, `Max`).

---

## Interactive Results & Data Profiling Panel

* **Data View**: Paginated data grid (100 rows per page), column search filtering, sticky headers, and record counts.
* **Multi-Port Switching**: When viewing tools with multiple output ports (e.g. Filter `T`/`F` or Join `J`/`L`/`R`), click the port tabs to instantly inspect intermediate datasets.
* **Metadata & Data Profiler**: Comprehensive statistics for each field including non-null counts, null percentages, unique value counts, min/max/mean/median for numbers, and sample frequency bars for strings.
* **Execution Log**: Step-by-step pipeline execution duration and record count audit trail.
* **Direct Export**: One-click download of any node's output as CSV or Excel.

---

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl + Enter` | **Run Workflow** |
| `Delete` / `Backspace` | Delete selected tool or connection wire |
| Mouse Wheel | Zoom in / Zoom out of canvas |
| Click & Drag Background | Pan canvas |
| Double-click Tool in Palette | Place tool at canvas center |

---

## Pre-built Sample Workflows

The app comes pre-packaged with sample datasets and ready-to-run workflows accessible from the **Samples** dropdown:
1. **Customer Sales Analysis**: Ingests customer CSV and order Excel files, joins on CustomerID, computes net revenue with discounts, filters high-value orders, and summarizes total revenue by region and segment.
2. **Data Cleaning & Deduplication**: Ingests dirty data with whitespace and nulls, trims text, handles missing values, and deduplicates records.

---

## Automated Tests

Run test suites using Python:
```powershell
& "C:\Users\Ahmed Gad\anaconda3\python.exe" -m unittest tests/test_engine.py
& "C:\Users\Ahmed Gad\anaconda3\python.exe" -m unittest tests/test_api.py
```
