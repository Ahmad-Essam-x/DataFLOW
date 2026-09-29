# Antigravity DataFlow — Formula Tool Reference Guide

The **Formula Tool** in Antigravity DataFlow allows you to create new columns or update existing columns using vectorized mathematical, string, datetime, conditional, and regular expression operations.

Syntax is compatible with **Alteryx Designer formula standards** while running natively on optimized Python/Pandas vectorized backend execution.

---

## Table of Contents

1. [Core Syntax & Conventions](#1-core-syntax--conventions)
2. [Conditional Logic (IF / THEN / ELSE & IIF)](#2-conditional-logic)
3. [String Functions](#3-string-functions)
4. [DateTime Functions](#4-datetime-functions)
5. [Math & Numeric Functions](#5-math--numeric-functions)
6. [Type Conversion & Null Handling](#6-type-conversion--null-handling)
7. [Operators & Precedence](#7-operators--precedence)
8. [Multi-Row & Multi-Field Formulas](#8-multi-row--multi-field-formulas)
9. [Common Formula Recipes](#9-common-formula-recipes)

---

## 1. Core Syntax & Conventions

### Referencing Fields
- Field names are enclosed in square brackets: `[Field_Name]`.
- Field names containing spaces or special characters are supported: `[Total Revenue]`, `[Customer ID]`.
- Typing `[` in the Formula Editor triggers interactive column autocompletion.

```alteryx
[Price] * [Quantity] * (1 - [Discount_Rate])
```

### String Literals
- String constants must be enclosed in single (`'...'`) or double (`"..."`) quotes:
  ```alteryx
  "Active"
  'East Region'
  ```

### Numeric & Boolean Literals
- Numbers: `100`, `3.14159`, `-42`
- Booleans: `True`, `False`
- Nulls: `Null()`

### Execution Order
- Formulas configured within a single Formula tool execute **sequentially from top to bottom**.
- A formula card can immediately reference columns created or updated by earlier cards in the same tool.

---

## 2. Conditional Logic

DataFlow supports both Alteryx multi-branch conditional statements (`IF...THEN...ELSEIF...ELSE...ENDIF`) and inline conditional expressions (`IIF`).

### Multi-Branch IF Statement
Keywords are case-insensitive (`IF`, `THEN`, `ELSEIF`, `ELSE`, `ENDIF`).

```alteryx
IF [Sales] >= 10000 THEN
    "Tier 1 - Platinum"
ELSEIF [Sales] >= 5000 THEN
    "Tier 2 - Gold"
ELSEIF [Sales] >= 1000 THEN
    "Tier 3 - Silver"
ELSE
    "Tier 4 - Standard"
ENDIF
```

### Inline IF: `IIF()`
Evaluates a condition and returns the true value if satisfied, or the false value otherwise.

```alteryx
IIF([Units_Sold] > 100, [Price] * 0.9, [Price])
```

- **Signature:** `IIF(condition, true_value, false_value)`
- **Alias:** `IF(condition, true_value, false_value)`

---

## 3. String Functions

| Function | Signature | Description | Example |
| :--- | :--- | :--- | :--- |
| **Contains** | `Contains(str, target, [case_insensitive=True])` | Returns `True` if `target` is found within `str`. | `Contains([Email], "@gmail.com")` |
| **StartsWith** | `StartsWith(str, prefix, [case_insensitive=True])` | Returns `True` if `str` starts with `prefix`. | `StartsWith([SKU], "PROD-")` |
| **EndsWith** | `EndsWith(str, suffix, [case_insensitive=True])` | Returns `True` if `str` ends with `suffix`. | `EndsWith([Filename], ".csv")` |
| **Left** | `Left(str, len)` | Returns the first `len` characters of the string. | `Left([ZipCode], 5)` |
| **Right** | `Right(str, len)` | Returns the last `len` characters of the string. | `Right([Account_Number], 4)` |
| **Substring** | `Substring(str, start, [len])` | Extracts a substring starting at 0-based index `start` for optional length `len`. | `Substring([ID], 2, 4)` |
| **Uppercase** | `Uppercase(str)` / `Upper(str)` | Converts all characters to uppercase. | `Uppercase([Country])` |
| **Lowercase** | `Lowercase(str)` / `Lower(str)` | Converts all characters to lowercase. | `Lowercase([Email])` |
| **TitleCase** | `TitleCase(str)` / `Proper(str)` | Capitalizes the first character of each word. | `TitleCase([Full_Name])` |
| **Trim** | `Trim(str)` | Strips leading and trailing whitespace. | `Trim([Comments])` |
| **Length** | `Length(str)` / `Len(str)` | Returns the character count of the string. | `Length([Phone_Number])` |
| **Replace** | `Replace(str, target, replacement)` | Replaces occurrences of `target` with `replacement`. | `Replace([Phone], "-", "")` |
| **Concat** | `Concat(str1, str2, ...)` | Concatenates two or more strings together. | `Concat([First_Name], " ", [Last_Name])` |
| **RegexMatch** | `RegexMatch(str, pattern)` | Returns `True` if string matches regular expression. | `RegexMatch([Zip], "^\d{5}(-\d{4})?$")` |
| **RegexCountMatches** | `RegexCountMatches(str, pattern)` | Returns the count of regex pattern matches. | `RegexCountMatches([Text], "\b\w+\b")` |
| **RegexReplace** | `RegexReplace(str, pattern, replacement)` | Replaces regex pattern matches with replacement. | `RegexReplace([SSN], "\D", "")` |

---

## 4. DateTime Functions

Supported units for date arithmetic: `'days'`, `'hours'`, `'minutes'`, `'seconds'`, `'months'`, `'years'`.

| Function | Signature | Description | Example |
| :--- | :--- | :--- | :--- |
| **DateTimeToday** | `DateTimeToday()` / `Today()` | Returns the current date as `'YYYY-MM-DD'`. | `DateTimeToday()` |
| **DateTimeNow** | `DateTimeNow()` / `Now()` | Returns the current timestamp as `'YYYY-MM-DD HH:MM:SS'`. | `DateTimeNow()` |
| **DateTimeAdd** | `DateTimeAdd(dt, num, unit)` | Adds or subtracts interval units from a date/timestamp. | `DateTimeAdd([Order_Date], 14, "days")` |
| **DateTimeDiff** | `DateTimeDiff(dt1, dt2, unit)` | Calculates difference (`dt1 - dt2`) in units. | `DateTimeDiff([Delivery_Date], [Ship_Date], "days")` |
| **DateTimeFormat** | `DateTimeFormat(dt, pattern)` | Formats date using standard strftime directives. | `DateTimeFormat([Order_Date], "%b %d, %Y")` |
| **DateTimeYear** | `DateTimeYear(dt)` | Extracts 4-digit integer year (e.g. `2026`). | `DateTimeYear([Order_Date])` |
| **DateTimeMonth** | `DateTimeMonth(dt)` | Extracts month number (`1` to `12`). | `DateTimeMonth([Order_Date])` |
| **DateTimeDay** | `DateTimeDay(dt)` | Extracts day of the month (`1` to `31`). | `DateTimeDay([Order_Date])` |

---

## 5. Math & Numeric Functions

| Function | Signature | Description | Example |
| :--- | :--- | :--- | :--- |
| **Round** | `Round(num, [decimals=0])` | Rounds to specified decimal precision. | `Round([Total_Amount] * 1.0825, 2)` |
| **Abs** | `Abs(num)` | Returns the absolute positive value. | `Abs([Budget_Variance])` |
| **Ceil** | `Ceil(num)` / `Ceiling(num)` | Smallest integer greater than or equal to `num`. | `Ceil([Weight_Kg])` |
| **Floor** | `Floor(num)` | Largest integer less than or equal to `num`. | `Floor([Rating])` |
| **Min** | `Min(a, b, ...)` | Minimum value across arguments. | `Min([Discount], 0.25)` |
| **Max** | `Max(a, b, ...)` | Maximum value across arguments. | `Max([Base_Rate], 15.00)` |
| **Between** | `Between(val, min_val, max_val)` | Tests if `val >= min_val` and `val <= max_val`. | `Between([Score], 70, 89)` |
| **Sqrt** | `Sqrt(num)` | Square root of number. | `Sqrt([Variance])` |
| **Power** | `Power(base, exp)` / `Pow(b, e)` | Exponential power `base ** exp`. | `Power([Radius], 2) * 3.14159` |
| **Log** | `Log(num)` / `Ln(num)` | Natural logarithm (base $e$). | `Log([Value])` |
| **Log10** | `Log10(num)` | Base-10 logarithm. | `Log10([Richter_Scale])` |
| **Exp** | `Exp(num)` | Exponential $e^{num}$. | `Exp([Rate])` |

---

## 6. Type Conversion & Null Handling

| Function | Signature | Description | Example |
| :--- | :--- | :--- | :--- |
| **IsNull** | `IsNull(val)` | Returns `True` if value is null, missing, or NaN. | `IsNull([Cancellation_Date])` |
| **NotNull** | `NotNull(val)` | Returns `True` if value is present and non-null. | `NotNull([Shipping_Tracking_ID])` |
| **IsEmpty** | `IsEmpty(str)` | Returns `True` if value is null or empty/whitespace string. | `IsEmpty([Apartment_Suite])` |
| **NotEmpty** | `NotEmpty(str)` | Returns `True` if string contains non-whitespace text. | `NotEmpty([Special_Instructions])` |
| **IfNull** | `IfNull(val, default_val)` | Returns `val` if non-null; otherwise `default_val`. | `IfNull([Discount_Pct], 0.0)` |
| **Coalesce** | `Coalesce(val1, val2, ...)` | Returns the first non-null argument in the list. | `Coalesce([Mobile_Phone], [Home_Phone], "N/A")` |
| **Null** | `Null()` | Explicitly produces a Null / NaN value. | `IIF([Status] == "Void", Null(), [Amount])` |
| **ToNumber** | `ToNumber(val)` | Automatically cleans currency symbols (`$`, `€`), commas, and converts text to float. | `ToNumber([Raw_Revenue])` |
| **ToString** | `ToString(val)` | Converts numeric, boolean, or datetime to string. | `ToString([Postal_Code])` |
| **IsNumber** | `IsNumber(val)` | Returns `True` if value is numeric or parseable number. | `IsNumber([Input_Text])` |
| **IsInteger** | `IsInteger(val)` | Returns `True` if value represents a whole integer. | `IsInteger([Quantity])` |
| **IsDate** | `IsDate(val)` | Returns `True` if value can be parsed as a date/time. | `IsDate([User_Input_Date])` |

---

## 7. Operators & Precedence

### Arithmetic Operators
- `+` : Addition (Numbers) or String Concatenation (`[First] + " " + [Last]`)
- `-` : Subtraction
- `*` : Multiplication
- `/` : Division (safe division: zero denominators yield `Null()`)
- `%` : Modulo / Remainder
- `**` : Exponentiation

### Comparison Operators
- `==` : Equal to
- `!=` : Not equal to
- `<`  : Less than
- `<=` : Less than or equal to
- `>`  : Greater than
- `>=` : Greater than or equal to

### Logical Operators
- `AND` : Logical conjunction (`[Age] >= 21 AND [Has_License] == True`)
- `OR`  : Logical disjunction (`[State] == 'NY' OR [State] == 'NJ'`)
- `NOT` : Logical negation (`NOT IsNull([Email])`)

---

## 8. Multi-Row & Multi-Field Formulas

In addition to the standard **Formula Tool**, Antigravity DataFlow provides dedicated specialized formula tools:

### Multi-Row Formula
Allows formulas to inspect preceding or subsequent rows for running totals, lag/lead comparisons, and window metrics:
- `[Row-1:Field_Name]` : Value of column in the prior row
- `[Row+1:Field_Name]` : Value of column in the subsequent row
- `[Row-0:Field_Name]` : Current row value

```alteryx
// Running Total Example
IIF(IsNull([Row-1:RunningTotal]), [Amount], [Row-1:RunningTotal] + [Amount])
```

### Multi-Field Formula
Batch-transforms multiple columns simultaneously:
- `[_CurrentField_]` : Value of the active field being evaluated
- `[_CurrentFieldName_]` : String name of the active field

```alteryx
// Clean nulls across all selected numeric columns
IIF(IsNull([_CurrentField_]), 0, [_CurrentField_])
```

---

## 9. Common Formula Recipes

### 1. Data Cleaning: Clean Currency Strings to Numbers
```alteryx
ToNumber(Replace(Replace([Revenue_Raw], "$", ""), ",", ""))
```

### 2. Full Name Assembly with Null Safety
```alteryx
Trim(Concat(IfNull([First_Name], ""), " ", IfNull([Middle_Name], ""), " ", IfNull([Last_Name], "")))
```

### 3. Business Day / SLA Age in Days
```alteryx
DateTimeDiff(DateTimeToday(), [Created_Date], "days")
```

### 4. Fiscal Quarter Calculation
```alteryx
Concat("Q", ToString(Ceil(DateTimeMonth([Order_Date]) / 3.0)), "-", ToString(DateTimeYear([Order_Date])))
```

### 5. Categorical Risk Scoring
```alteryx
IF [Credit_Score] < 580 OR [Debt_To_Income] > 0.45 THEN
    "High Risk"
ELSEIF [Credit_Score] < 670 THEN
    "Moderate Risk"
ELSE
    "Prime"
ENDIF
```

### 6. Email Domain Extraction
```alteryx
IIF(Contains([Email], "@"), Substring([Email], Length(Left([Email], Length([Email]) - Length(Right([Email], Length([Email]) - Contains([Email], "@")))))), "Unknown")
```
*(Or cleanly using regex:)*
```alteryx
RegexReplace([Email], "^.*@", "")
```
