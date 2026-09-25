"""
Comprehensive unit tests for the 6 new Alteryx tools and upgraded configuration options.
"""
import os
import unittest
import pandas as pd
import numpy as np

from backend.engine.node_registry import (
    NODE_REGISTRY, TOOL_METADATA, NodeExecutionError,
    InputDataNode, OutputDataNode, TextInputNode, SelectNode,
    FilterNode, FormulaNode, SortNode, CleanNode, UniqueNode,
    SampleNode, RecordIDNode, JoinNode, UnionNode,
    FindReplaceNode, SummarizeNode, TransposeNode, CrossTabNode
)
from backend.samples.generator import ensure_sample_data


class TestAlteryxTools(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.output_dir = os.path.join(self.data_dir, "outputs")
        os.makedirs(self.output_dir, exist_ok=True)
        ensure_sample_data(self.data_dir, os.path.join(self.base_dir, "workflows"))
        self.context = {"data_dir": self.data_dir, "output_dir": self.output_dir}

    # 1. Text Input Tool
    def test_text_input_grid(self):
        node = TextInputNode("ti1", {
            "columns": ["Product", "Price", "Qty"],
            "data": [["Widget", 10.5, 3], ["Gadget", 25.0, 1]]
        })
        res = node.execute({}, self.context)
        df = res["O"]
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df.columns), ["Product", "Price", "Qty"])
        self.assertEqual(df["Product"].tolist(), ["Widget", "Gadget"])
        self.assertEqual(df["Price"].tolist(), [10.5, 25.0])

    def test_text_input_tsv_paste(self):
        raw_tsv = "Name\tDepartment\tSalary\nAlice\tSales\t50000\nBob\tEngineering\t80000"
        node = TextInputNode("ti2", {
            "raw_text": raw_tsv,
            "delimiter": "\t"
        })
        res = node.execute({}, self.context)
        df = res["O"]
        self.assertEqual(len(df), 2)
        self.assertIn("Department", df.columns)
        self.assertEqual(df["Salary"].tolist(), [50000, 80000])

    # 2. Sample Tool
    def test_sample_modes(self):
        df = pd.DataFrame({"ID": range(1, 11), "Grp": ["A"] * 5 + ["B"] * 5})

        res_first = SampleNode("s1", {"sample_type": "first_n", "n_records": 3}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_first["ID"].tolist(), [1, 2, 3])

        res_last = SampleNode("s2", {"sample_type": "last_n", "n_records": 2}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_last["ID"].tolist(), [9, 10])

        res_skip = SampleNode("s3", {"sample_type": "skip_first_n", "n_records": 7}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_skip["ID"].tolist(), [8, 9, 10])

        res_step = SampleNode("s4", {"sample_type": "sample_1_in_n", "n_records": 3}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_step["ID"].tolist(), [1, 4, 7, 10])

        res_pct = SampleNode("s5", {"sample_type": "first_n_percent", "percent": 40}).execute({"I": df}, self.context)["O"]
        self.assertEqual(len(res_pct), 4)

        res_grp = SampleNode("s6", {"sample_type": "first_n", "n_records": 2, "group_by": ["Grp"]}).execute({"I": df}, self.context)["O"]
        self.assertEqual(len(res_grp), 4)
        self.assertEqual(res_grp["ID"].tolist(), [1, 2, 6, 7])

    # 3. Record ID Tool
    def test_record_id(self):
        df = pd.DataFrame({"Name": ["Alpha", "Beta", "Gamma"], "Dept": ["Sales", "Sales", "IT"]})

        res1 = RecordIDNode("rid1", {}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res1.columns[0], "RecordID")
        self.assertEqual(res1["RecordID"].tolist(), [1, 2, 3])

        res2 = RecordIDNode("rid2", {
            "column_name": "Row_Num",
            "start_value": 100,
            "position": "last"
        }).execute({"I": df}, self.context)["O"]
        self.assertEqual(res2.columns[-1], "Row_Num")
        self.assertEqual(res2["Row_Num"].tolist(), [100, 101, 102])

        res3 = RecordIDNode("rid3", {
            "column_name": "DeptSeq",
            "start_value": 1,
            "group_by": ["Dept"]
        }).execute({"I": df}, self.context)["O"]
        self.assertEqual(res3["DeptSeq"].tolist(), [1, 2, 1])

    # 4. Find Replace Tool
    def test_find_replace_text_replace(self):
        main_df = pd.DataFrame({"Desc": ["Buy an apple today", "Sweet banana pie", "Orange juice"]})
        ref_df = pd.DataFrame({"FindWord": ["apple", "banana"], "ReplaceWord": ["honeycrisp", "plantain"]})

        node = FindReplaceNode("fr1", {
            "find_field": "Desc",
            "find_value_field": "FindWord",
            "search_mode": "any_part",
            "action": "replace",
            "replace_with_field": "ReplaceWord"
        })
        res = node.execute({"F": main_df, "R": ref_df}, self.context)["O"]
        self.assertEqual(res["Desc"].iloc[0], "Buy an honeycrisp today")
        self.assertEqual(res["Desc"].iloc[1], "Sweet plantain pie")
        self.assertEqual(res["Desc"].iloc[2], "Orange juice")

    def test_find_replace_append_fields(self):
        main_df = pd.DataFrame({"StateCode": ["NY", "CA", "TX", "WA"]})
        ref_df = pd.DataFrame({
            "Code": ["NY", "CA", "TX"],
            "StateName": ["New York", "California", "Texas"],
            "Region": ["East", "West", "South"]
        })

        node = FindReplaceNode("fr2", {
            "find_field": "StateCode",
            "find_value_field": "Code",
            "search_mode": "entire_field",
            "action": "append",
            "append_fields": ["StateName", "Region"]
        })
        res = node.execute({"F": main_df, "R": ref_df}, self.context)["O"]
        self.assertIn("StateName", res.columns)
        self.assertIn("Region", res.columns)
        self.assertEqual(res["StateName"].iloc[0], "New York")
        self.assertTrue(pd.isna(res["StateName"].iloc[3]))

    # 5. Transpose Tool
    def test_transpose_wide_to_tall(self):
        df = pd.DataFrame({
            "Emp": ["Alice", "Bob"],
            "Q1": [100, 200],
            "Q2": [150, 250],
            "Q3": [180, 280]
        })
        node = TransposeNode("tr1", {
            "key_columns": ["Emp"],
            "data_columns": ["Q1", "Q2", "Q3"],
            "name_column": "Quarter",
            "value_column": "Sales"
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(len(res), 6)
        self.assertEqual(list(res.columns), ["Emp", "Quarter", "Sales"])
        self.assertEqual(res["Sales"].sum(), 1160)

    # 6. Cross Tab Tool
    def test_crosstab_tall_to_wide(self):
        df = pd.DataFrame({
            "Store": ["A", "A", "B", "B"],
            "Category": ["Food", "Electr", "Food", "Electr"],
            "Revenue": [100, 500, 200, 800]
        })
        node = CrossTabNode("ct1", {
            "group_by": ["Store"],
            "header_field": "Category",
            "value_field": "Revenue",
            "agg_func": "sum"
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertIn("Food", res.columns)
        self.assertIn("Electr", res.columns)
        self.assertEqual(len(res), 2)
        row_a = res[res["Store"] == "A"].iloc[0]
        self.assertEqual(row_a["Food"], 100)
        self.assertEqual(row_a["Electr"], 500)

    def test_crosstab_concat(self):
        df = pd.DataFrame({
            "Dept": ["IT", "IT", "HR"],
            "Role": ["Dev", "QA", "Recruiter"],
            "Name": ["Alice", "Bob", "Carol"]
        })
        node = CrossTabNode("ct2", {
            "group_by": ["Dept"],
            "header_field": "Role",
            "value_field": "Name",
            "agg_func": "concat",
            "separator": " & "
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertIn("Dev", res.columns)
        it_dev = res[res["Dept"] == "IT"]["Dev"].iloc[0]
        self.assertEqual(it_dev, "Alice")

    # 7. Upgraded Existing Tools
    def test_input_data_start_row_and_filename(self):
        node = InputDataNode("in_adv", {
            "file_path": "customers.csv",
            "file_type": "csv",
            "start_row": 5,
            "output_filename_field": "name_only"
        })
        res = node.execute({}, self.context)["O"]
        self.assertEqual(len(res), 1000 - 4)
        self.assertIn("FileName", res.columns)
        self.assertEqual(res["FileName"].iloc[0], "customers.csv")

    def test_output_data_append(self):
        df1 = pd.DataFrame({"A": [1, 2], "Cat": ["Alpha", "Beta"]})
        df2 = pd.DataFrame({"A": [3, 4], "Cat": ["Alpha", "Beta"]})
        out_node = OutputDataNode("out1", {
            "filename": "test_append_out",
            "format": "csv",
            "write_mode": "overwrite"
        })
        out_node.execute({"I": df1}, self.context)

        out_node_append = OutputDataNode("out2", {
            "filename": "test_append_out",
            "format": "csv",
            "write_mode": "append"
        })
        out_node_append.execute({"I": df2}, self.context)

        saved_file = os.path.join(self.output_dir, "test_append_out.csv")
        read_df = pd.read_csv(saved_file)
        self.assertEqual(len(read_df), 4)

    def test_select_date_casting(self):
        df = pd.DataFrame({"DStr": ["2026-05-12 14:30:00", "2026-11-20"]})
        node = SelectNode("sel_date", {
            "fields": [{"original": "DStr", "keep": True, "rename": "DOnly", "type": "date"}]
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(res["DOnly"].iloc[0], "2026-05-12")
        self.assertEqual(res["DOnly"].iloc[1], "2026-11-20")

    def test_filter_empty_operators(self):
        df = pd.DataFrame({"Notes": ["Hello", "", None, "World", "   "]})
        node_empty = FilterNode("flt_emp", {
            "mode": "basic",
            "logical_op": "AND",
            "conditions": [{"column": "Notes", "operator": "is_empty", "value": ""}]
        })
        res = node_empty.execute({"I": df}, self.context)
        self.assertEqual(len(res["T"]), 3)
        self.assertEqual(len(res["F"]), 2)

    def test_formula_alteryx_functions(self):
        df = pd.DataFrame({
            "Price": [10.0, -5.0],
            "Title": ["widget pro", "super gadget"],
            "DateStr": ["2026-01-01", "2026-01-10"]
        })
        node = FormulaNode("f_alteryx", {
            "formulas": [
                {
                    "output_field": "Status",
                    "expression": "IF [Price] > 0 THEN 'Valid' ELSE 'Invalid' ENDIF",
                    "type": "string"
                },
                {
                    "output_field": "AbsPrice",
                    "expression": "ABS([Price])",
                    "type": "float"
                },
                {
                    "output_field": "CleanTitle",
                    "expression": "PROPER([Title])",
                    "type": "string"
                },
                {
                    "output_field": "ShortCode",
                    "expression": "LEFT([Title], 3)",
                    "type": "string"
                },
                {
                    "output_field": "Days",
                    "expression": "DateTimeDiff('2026-01-15', [DateStr], 'days')",
                    "type": "integer"
                }
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(res["Status"].tolist(), ["Valid", "Invalid"])
        self.assertEqual(res["AbsPrice"].tolist(), [10.0, 5.0])
        self.assertEqual(res["CleanTitle"].tolist(), ["Widget Pro", "Super Gadget"])
        self.assertEqual(res["ShortCode"].tolist(), ["wid", "sup"])
        self.assertEqual(res["Days"].tolist(), [14, 5])

    def test_sort_case_sensitive(self):
        df = pd.DataFrame({"Name": ["apple", "Banana", "cherry", "Apple"]})
        res_ci = SortNode("s_ci", {"sort_by": [{"column": "Name", "ascending": True}], "case_sensitive": False}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_ci["Name"].str.lower().tolist(), ["apple", "apple", "banana", "cherry"])

        res_cs = SortNode("s_cs", {"sort_by": [{"column": "Name", "ascending": True}], "case_sensitive": True}).execute({"I": df}, self.context)["O"]
        self.assertEqual(res_cs["Name"].tolist(), ["Apple", "Banana", "apple", "cherry"])

    def test_clean_alteryx_options(self):
        df = pd.DataFrame({
            "Text": ["  hello\tworld \n ", "item-123!!", None],
            "Num": [10.0, None, np.nan]
        })
        node = CleanNode("c_alteryx", {
            "replace_nulls_string": True,
            "replace_nulls_numeric": True,
            "remove_tabs_linebreaks": True,
            "remove_punctuation": True,
            "case_mode": "title"
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(res["Text"].iloc[0], "Hello World")
        self.assertEqual(res["Text"].iloc[1], "Item123")
        self.assertEqual(res["Text"].iloc[2], "")
        self.assertEqual(res["Num"].iloc[1], 0.0)

    def test_summarize_advanced_aggs(self):
        df = pd.DataFrame({
            "Dept": ["Sales", "Sales", "IT", "IT"],
            "Score": [10, 20, 15, None],
            "Emp": ["Alice", "Bob", "Charlie", "Dan"]
        })
        node = SummarizeNode("sum_adv", {
            "actions": [
                {"field": "Dept", "action": "GroupBy", "output_name": "Department"},
                {"field": "Score", "action": "CountNull", "output_name": "Nulls"},
                {"field": "Score", "action": "CountNonNull", "output_name": "NonNulls"},
                {"field": "Score", "action": "Mean", "output_name": "AvgScore"},
                {"field": "Emp", "action": "Concat", "output_name": "AllEmps", "separator": " / "}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        sales_row = res[res["Department"] == "Sales"].iloc[0]
        self.assertEqual(sales_row["Nulls"], 0)
        self.assertEqual(sales_row["NonNulls"], 2)
        self.assertEqual(sales_row["AvgScore"], 15.0)
        self.assertEqual(sales_row["AllEmps"], "Alice / Bob")

        it_row = res[res["Department"] == "IT"].iloc[0]
        self.assertEqual(it_row["Nulls"], 1)
        self.assertEqual(it_row["NonNulls"], 1)

    def test_join_record_position_and_select(self):
        df_l = pd.DataFrame({"L_ID": [1, 2, 3], "Val": ["A", "B", "C"]})
        df_r = pd.DataFrame({"R_ID": [10, 20], "Val": ["X", "Y"]})

        node = JoinNode("j_pos", {
            "join_mode": "record_position",
            "select_fields": [
                {"field": "L_ID", "selected": True, "rename": "LeftID"},
                {"field": "Right_Val", "selected": False},
                {"field": "Val", "selected": True, "rename": "LeftVal"}
            ]
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]
        l_df = res["L"]
        r_df = res["R"]

        self.assertEqual(len(j_df), 2)
        self.assertIn("LeftID", j_df.columns)
        self.assertIn("LeftVal", j_df.columns)
        self.assertNotIn("Right_Val", j_df.columns)

        self.assertEqual(len(l_df), 1)
        self.assertEqual(len(r_df), 0)

    def test_union_non_matching_policies(self):
        df1 = pd.DataFrame({"A": [1], "B": [2]})
        df2 = pd.DataFrame({"A": [3], "C": [4]})

        node_common = UnionNode("u_com", {"non_matching": "common_only"})
        res_com = node_common.execute({"I": [df1, df2]}, self.context)["O"]
        self.assertEqual(list(res_com.columns), ["A"])
        self.assertEqual(res_com["A"].tolist(), [1, 3])

        node_err = UnionNode("u_err", {"non_matching": "error"})
        with self.assertRaises(NodeExecutionError):
            node_err.execute({"I": [df1, df2]}, self.context)

    def test_summarize_duplicate_output_names(self):
        """Validates that Summarize node handles identical/colliding output names gracefully without duplicate columns."""
        df = pd.DataFrame({
            "Status": ["Active", "Active", "Inactive", "Pending"],
            "Score": [10, 20, 30, 40]
        })
        # Exact configuration from user's screenshot
        cfg = {
            "actions": [
                {"field": "Status", "action": "GroupBy", "output_name": "Score"},
                {"field": "Score", "action": "Count", "output_name": "Score"}
            ]
        }
        node = SummarizeNode("sum_dup", cfg)
        res = node.execute({"I": df}, self.context)["O"]

        # Columns must be unique and non-empty
        self.assertEqual(len(res.columns), len(set(res.columns)))
        self.assertEqual(len(res), 3)
        self.assertIn("Score", res.columns)
        self.assertIn("Score_2", res.columns)

    def test_sanitize_dataframe_and_executor_caching(self):
        """Validates that WorkflowExecutor safely retrieves data and profiling for DataFrames with duplicate columns."""
        from backend.engine.executor import WorkflowExecutor
        from backend.engine.node_registry import sanitize_dataframe

        # MultiIndex and duplicate columns
        dup_df = pd.DataFrame([[1, 2, 3]], columns=["Val", "Val", "Val"])
        clean_df = sanitize_dataframe(dup_df)
        self.assertEqual(list(clean_df.columns), ["Val", "Val_2", "Val_3"])

        # Test executor data fetching and profiling on duplicate dataframe
        ex = WorkflowExecutor(context=self.context)
        ex.data_cache["test_node"] = {"O": pd.DataFrame([[10, 20], [30, 40]], columns=["Score", "Score"])}
        data_res = ex.get_node_data("test_node", "O")
        self.assertTrue(data_res["available"])
        self.assertEqual(len(data_res["columns"]), 2)
        self.assertEqual(data_res["records"][0]["Score"], 10)
        self.assertEqual(data_res["records"][0]["Score_2"], 20)

        prof_res = ex.get_node_profiling("test_node", "O")
        self.assertTrue(prof_res["available"])
        self.assertEqual(len(prof_res["columns"]), 2)


    def test_summarize_all_numeric_and_ignore_zeros(self):
        """Tests Product, Percentile, Mode, and Ignore 0's across numeric aggregations."""
        df = pd.DataFrame({
            "Dept": ["Finance", "Finance", "Finance", "IT", "IT"],
            "Val": [0.0, 10.0, 20.0, 5.0, 5.0]
        })
        node = SummarizeNode("sum_num", {
            "actions": [
                {"field": "Dept", "action": "GroupBy"},
                {"field": "Val", "action": "Sum", "output_name": "Sum_Val"},
                {"field": "Val", "action": "Sum", "ignore_zeros": True, "output_name": "Sum_NonZero"},
                {"field": "Val", "action": "Average", "ignore_zeros": True, "output_name": "Avg_NonZero"},
                {"field": "Val", "action": "Product", "ignore_zeros": True, "output_name": "Prod_NonZero"},
                {"field": "Val", "action": "Product", "ignore_zeros": False, "output_name": "Prod_WithZero"},
                {"field": "Val", "action": "Percentile", "percentile": 50, "output_name": "P50"},
                {"field": "Val", "action": "Mode", "output_name": "Mode_Val"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        fin_row = res[res["Dept"] == "Finance"].iloc[0]
        it_row = res[res["Dept"] == "IT"].iloc[0]

        # In Finance: values are 0.0, 10.0, 20.0
        self.assertEqual(fin_row["Sum_Val"], 30.0)
        self.assertEqual(fin_row["Sum_NonZero"], 30.0)
        # Average without 0 is (10+20)/2 = 15.0
        self.assertEqual(fin_row["Avg_NonZero"], 15.0)
        # Product without 0 is 10 * 20 = 200.0
        self.assertEqual(fin_row["Prod_NonZero"], 200.0)
        # Product with 0 is 0.0
        self.assertEqual(fin_row["Prod_WithZero"], 0.0)
        # Median/P50 of [0, 10, 20] is 10.0
        self.assertEqual(fin_row["P50"], 10.0)

        # In IT: values are 5.0, 5.0
        self.assertEqual(it_row["Mode_Val"], 5.0)

    def test_summarize_all_string_operations(self):
        """Tests Concat with start/sep/end, ConcatDistinct, Longest, Shortest, CountBlank, Mode."""
        df = pd.DataFrame({
            "Grp": ["A", "A", "A", "A"],
            "Txt": ["banana", "apple", "apple", "   "],
            "NullCol": ["val", None, "   ", None]
        })
        node = SummarizeNode("sum_str", {
            "actions": [
                {"field": "Grp", "action": "GroupBy"},
                {"field": "Txt", "action": "Concat", "start": "[", "separator": "|", "end": "]", "output_name": "Concat_Txt"},
                {"field": "Txt", "action": "ConcatDistinct", "start": "(", "separator": ", ", "end": ")", "output_name": "ConcatDist_Txt"},
                {"field": "Txt", "action": "Longest", "output_name": "Longest_Txt"},
                {"field": "Txt", "action": "Shortest", "output_name": "Shortest_Txt"},
                {"field": "Txt", "action": "CountBlank", "output_name": "Blank_Count"},
                {"field": "Txt", "action": "CountNonBlank", "output_name": "NonBlank_Count"},
                {"field": "Txt", "action": "Mode", "output_name": "Mode_Txt"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        row = res.iloc[0]

        self.assertEqual(row["Concat_Txt"], "[banana|apple|apple|   ]")
        self.assertEqual(row["ConcatDist_Txt"], "(banana, apple,    )")
        self.assertEqual(row["Longest_Txt"], "banana")
        self.assertEqual(row["Shortest_Txt"], "   ")
        self.assertEqual(row["Blank_Count"], 1)
        self.assertEqual(row["NonBlank_Count"], 3)
        # Mode is 'apple' (occurs twice, banana occurs once)
        self.assertEqual(row["Mode_Txt"], "apple")

    def test_summarize_string_mode_tie_breaker(self):
        """Alteryx returns the smallest string in alphabetical ascending order if tied."""
        df = pd.DataFrame({
            "Grp": [1, 1],
            "Letter": ["Zebra", "Apple"]
        })
        node = SummarizeNode("sum_tie", {
            "actions": [
                {"field": "Grp", "action": "GroupBy"},
                {"field": "Letter", "action": "Mode", "output_name": "Mode_Letter"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(res.iloc[0]["Mode_Letter"], "Apple")

    def test_summarize_financial_operations(self):
        """Tests NPV, IRR, MIRR, XNPV, XIRR."""
        # Standard investment cash flows: year 0: -1000, year 1: 400, year 2: 400, year 3: 400
        df = pd.DataFrame({
            "Project": ["Alpha", "Alpha", "Alpha", "Alpha"],
            "Date": ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"],
            "CashFlow": [-1000.0, 400.0, 400.0, 400.0]
        })
        node = SummarizeNode("sum_fin", {
            "actions": [
                {"field": "Project", "action": "GroupBy"},
                {"field": "CashFlow", "action": "NPV", "discount_rate": 10.0, "output_name": "Alpha_NPV"},
                {"field": "CashFlow", "action": "IRR", "output_name": "Alpha_IRR"},
                {"field": "CashFlow", "action": "MIRR", "finance_rate": 8.0, "reinvest_rate": 8.0, "output_name": "Alpha_MIRR"},
                {"field": "CashFlow", "action": "XNPV", "date_field": "Date", "discount_rate": 10.0, "output_name": "Alpha_XNPV"},
                {"field": "CashFlow", "action": "XIRR", "date_field": "Date", "output_name": "Alpha_XIRR"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        row = res.iloc[0]

        # NPV at 10%: -1000 + 400/1.1 + 400/1.21 + 400/1.331 = -5.2592
        self.assertAlmostEqual(row["Alpha_NPV"], -5.2592, places=3)
        # IRR should be ~ 0.09701 (9.70%)
        self.assertAlmostEqual(row["Alpha_IRR"], 0.09701, places=3)
        # MIRR should be valid float
        self.assertIsNotNone(row["Alpha_MIRR"])
        self.assertGreater(row["Alpha_MIRR"], 0.0)
        # XNPV should be close to NPV
        self.assertAlmostEqual(row["Alpha_XNPV"], row["Alpha_NPV"], places=0)
        # XIRR should be close to IRR
        self.assertAlmostEqual(row["Alpha_XIRR"], row["Alpha_IRR"], places=2)

    def test_summarize_counting_variants(self):
        """Tests Count, CountDistinct, CountDistinctNonNull, CountNull, CountNonNull."""
        df = pd.DataFrame({
            "Val": ["A", "B", "A", None, None]
        })
        node = SummarizeNode("sum_cnt", {
            "actions": [
                {"field": "Val", "action": "Count", "output_name": "Cnt"},
                {"field": "Val", "action": "CountDistinct", "output_name": "Distinct_All"},
                {"field": "Val", "action": "CountDistinctNonNull", "output_name": "Distinct_NonNull"},
                {"field": "Val", "action": "CountNull", "output_name": "Nulls"},
                {"field": "Val", "action": "CountNonNull", "output_name": "NonNulls"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        row = res.iloc[0]

        self.assertEqual(row["Cnt"], 5)
        self.assertEqual(row["Distinct_All"], 3)      # A, B, NaN
        self.assertEqual(row["Distinct_NonNull"], 2)  # A, B
        self.assertEqual(row["Nulls"], 2)
        self.assertEqual(row["NonNulls"], 3)

    def test_summarize_action_column_reordering(self):
        """Validates that output columns strictly match the configured actions sequence."""
        df = pd.DataFrame({
            "Region": ["East", "West"],
            "Sales": [100, 200],
            "Qty": [5, 10]
        })
        # Sequence: Qty Sum, Region GroupBy, Sales Sum (reordered intentionally)
        node = SummarizeNode("sum_ord", {
            "actions": [
                {"field": "Qty", "action": "Sum", "output_name": "Total_Qty"},
                {"field": "Region", "action": "GroupBy", "output_name": "Region_Key"},
                {"field": "Sales", "action": "Sum", "output_name": "Total_Sales"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(list(res.columns), ["Total_Qty", "Region_Key", "Total_Sales"])

    def test_summarize_groupby_only_text_fields_outputs_only_group_columns(self):
        """Verifies that configuring only GroupBy text fields outputs ONLY the group columns, excluding unselected columns."""
        df = pd.DataFrame({
            "Category": ["Electronics", "Electronics", "Furniture", "Furniture", "Electronics"],
            "Subcategory": ["Phone", "Phone", "Chair", "Table", "Laptop"],
            "Price": [800, 900, 150, 300, 1200],
            "Supplier": ["Acme", "Acme", "Ikea", "Ikea", "Dell"],
            "Notes": ["Flagship", "Budget", "Office", "Dining", "Pro"]
        })
        node = SummarizeNode("sum_grp_only", {
            "actions": [
                {"field": "Category", "action": "GroupBy"},
                {"field": "Subcategory", "action": "GroupBy"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]

        # Output columns must ONLY be Category and Subcategory
        self.assertEqual(list(res.columns), ["Category", "Subcategory"])
        self.assertNotIn("Price", res.columns)
        self.assertNotIn("Supplier", res.columns)
        self.assertNotIn("Notes", res.columns)

        # Output rows must be unique combinations
        self.assertEqual(len(res), 4)  # (Electronics, Phone), (Furniture, Chair), (Furniture, Table), (Electronics, Laptop)

    def test_summarize_groupby_only_with_rename(self):
        """Verifies that GroupBy-only configuration respects custom output column naming."""
        df = pd.DataFrame({
            "Dept": ["Sales", "Sales", "IT", "HR"],
            "Salary": [50000, 60000, 80000, 70000],
            "City": ["NYC", "LA", "NYC", "Chicago"]
        })
        node = SummarizeNode("sum_grp_ren", {
            "actions": [
                {"field": "Dept", "action": "GroupBy", "output_name": "Department_Name"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]

        self.assertEqual(list(res.columns), ["Department_Name"])
        self.assertNotIn("Salary", res.columns)
        self.assertNotIn("City", res.columns)
        self.assertEqual(sorted(res["Department_Name"].tolist()), ["HR", "IT", "Sales"])


if __name__ == "__main__":
    unittest.main()


