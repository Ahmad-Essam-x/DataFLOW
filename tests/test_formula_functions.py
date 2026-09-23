import unittest
import numpy as np
import pandas as pd
from backend.engine.formula import evaluate_expression, FormulaExecutionError, parse_alteryx_conditionals
from backend.engine.nodes.preparation import FormulaNode, FilterNode
from backend.engine.nodes.base import NodeExecutionError


class TestFormulaEngineAndFunctions(unittest.TestCase):
    def setUp(self):
        self.context = {"project_path": "."}

    def test_parse_alteryx_conditionals(self):
        # Single branch IF ... ELSE ... ENDIF
        expr1 = "IF [Val] > 10 THEN 'High' ELSE 'Low' ENDIF"
        self.assertEqual(parse_alteryx_conditionals(expr1), "IIF([Val] > 10, 'High', 'Low')")

        # Multi-branch IF ... ELSEIF ... ELSE ... ENDIF
        expr2 = "IF [Score] >= 90 THEN 'A' ELSEIF [Score] >= 80 THEN 'B' ELSE 'C' ENDIF"
        self.assertEqual(
            parse_alteryx_conditionals(expr2),
            "IIF([Score] >= 90, 'A', IIF([Score] >= 80, 'B', 'C'))"
        )

        # 3 branches with ELSE IF space
        expr3 = "IF [Score] >= 90 THEN 'A' ELSE IF [Score] >= 80 THEN 'B' ELSE IF [Score] >= 70 THEN 'C' ELSE 'D' ENDIF"
        self.assertEqual(
            parse_alteryx_conditionals(expr3),
            "IIF([Score] >= 90, 'A', IIF([Score] >= 80, 'B', IIF([Score] >= 70, 'C', 'D')))"
        )

    def test_bracketed_column_names(self):
        df = pd.DataFrame({
            "Gross Sales": [100.0, 250.0],
            "Discount %": [0.10, 0.20],
            "Shipping Fee $": [5.0, 10.0]
        })
        expr = "([Gross Sales] * (1 - [Discount %])) + [Shipping Fee $]"
        res = evaluate_expression(df, expr)
        self.assertAlmostEqual(res.iloc[0], 95.0)
        self.assertAlmostEqual(res.iloc[1], 210.0)

    def test_multi_branch_conditional_evaluation(self):
        df = pd.DataFrame({"Score": [95, 85, 75, 50]})
        expr = '''
        IF [Score] >= 90 THEN 'Tier 1'
        ELSEIF [Score] >= 80 THEN 'Tier 2'
        ELSEIF [Score] >= 70 THEN 'Tier 3'
        ELSE 'Tier 4'
        ENDIF
        '''
        res = evaluate_expression(df, expr)
        self.assertEqual(res.tolist(), ["Tier 1", "Tier 2", "Tier 3", "Tier 4"])

    def test_iif_and_nested_iif(self):
        df = pd.DataFrame({"Category": ["Electronics", "Clothing", "Food", "Other"]})
        expr = "IIF([Category] == 'Electronics', 0.20, IIF([Category] == 'Clothing', 0.10, 0.05))"
        res = evaluate_expression(df, expr)
        self.assertEqual(res.tolist(), [0.20, 0.10, 0.05, 0.05])

    def test_string_functions(self):
        df = pd.DataFrame({
            "Code": ["TX-1002-US", "CA-5432-MX"],
            "Text": ["  alteryx engine  ", "PANDAS PIPELINE"],
            "Msg": ["Hello World", "Data Science"]
        })
        # Left, Right, Substring
        self.assertEqual(evaluate_expression(df, "Left([Code], 2)").tolist(), ["TX", "CA"])
        self.assertEqual(evaluate_expression(df, "Right([Code], 2)").tolist(), ["US", "MX"])
        self.assertEqual(evaluate_expression(df, "Substring([Code], 3, 4)").tolist(), ["1002", "5432"])

        # Uppercase, Lowercase, Trim, Length
        self.assertEqual(evaluate_expression(df, "Uppercase(Trim([Text]))").iloc[0], "ALTERYX ENGINE")
        self.assertEqual(evaluate_expression(df, "Lowercase([Msg])").iloc[0], "hello world")
        self.assertEqual(evaluate_expression(df, "Length(Trim([Text]))").iloc[0], 14)

        # Contains (case-insensitive by default)
        self.assertEqual(evaluate_expression(df, "Contains([Msg], 'WORLD')").tolist(), [True, False])
        # Contains case-sensitive
        self.assertEqual(evaluate_expression(df, "Contains([Msg], 'world', 0)").tolist(), [False, False])
        self.assertEqual(evaluate_expression(df, "Contains([Msg], 'World', 0)").tolist(), [True, False])

        # Replace & TitleCase
        self.assertEqual(evaluate_expression(df, "Replace([Code], '-', ':')").iloc[0], "TX:1002:US")
        self.assertEqual(evaluate_expression(df, "TitleCase(Trim([Text]))").iloc[0], "Alteryx Engine")

        # Concat
        self.assertEqual(evaluate_expression(df, "Concat([Code], ' -> ', [Msg])").iloc[0], "TX-1002-US -> Hello World")

    def test_datetime_functions(self):
        df = pd.DataFrame({
            "Start": ["2026-01-01 08:00:00", "2026-06-15 12:00:00"],
            "End": ["2026-01-05 14:00:00", "2026-06-20 18:00:00"]
        })
        # DateTimeDiff in days and hours
        diff_days = evaluate_expression(df, "DateTimeDiff([End], [Start], 'days')")
        self.assertEqual(diff_days.tolist(), [4, 5])

        diff_hours = evaluate_expression(df, "DateTimeDiff([End], [Start], 'hours')")
        self.assertEqual(diff_hours.tolist(), [102, 126])

        # DateTimeAdd
        added = evaluate_expression(df, "DateTimeAdd([Start], 10, 'days')")
        self.assertTrue(str(added.iloc[0]).startswith("2026-01-11"))

        added_month = evaluate_expression(df, "DateTimeAdd('2026-01-15', 2, 'months')")
        self.assertTrue(str(added_month.iloc[0]).startswith("2026-03-15"))

        # DateTimeYear, Month, Day, Format
        self.assertEqual(evaluate_expression(df, "DateTimeYear([Start])").tolist(), [2026, 2026])
        self.assertEqual(evaluate_expression(df, "DateTimeMonth([Start])").tolist(), [1, 6])
        self.assertEqual(evaluate_expression(df, "DateTimeDay([Start])").tolist(), [1, 15])
        self.assertEqual(evaluate_expression(df, "DateTimeFormat([Start], '%m/%d/%Y')").tolist(), ["01/01/2026", "06/15/2026"])

        # DateTimeToday and DateTimeNow
        today_res = evaluate_expression(df, "DateTimeToday()")
        self.assertTrue(len(str(today_res.iloc[0])) == 10)

    def test_math_functions(self):
        df = pd.DataFrame({
            "Val1": [12.3456, -45.67],
            "Val2": [10.0, 50.0],
            "Val3": [20.0, -10.0]
        })
        # Round, Abs, Ceil, Floor
        self.assertAlmostEqual(evaluate_expression(df, "Round([Val1], 2)").iloc[0], 12.35)
        self.assertAlmostEqual(evaluate_expression(df, "Abs([Val1])").iloc[1], 45.67)
        self.assertEqual(evaluate_expression(df, "Ceil([Val1])").iloc[0], 13)
        self.assertEqual(evaluate_expression(df, "Floor([Val1])").iloc[0], 12)

        # Min and Max
        min_res = evaluate_expression(df, "Min([Val2], [Val3])")
        self.assertEqual(min_res.tolist(), [10.0, -10.0])

        max_res = evaluate_expression(df, "Max([Val2], [Val3])")
        self.assertEqual(max_res.tolist(), [20.0, 50.0])

    def test_null_and_conversion_functions(self):
        df = pd.DataFrame({
            "A": [np.nan, 10.0, None, 40.0],
            "B": ["", "  ", "Valid", None],
            "C": ["$1,500.50", "-45.2", "abc", "100"]
        })
        # IsNull
        self.assertEqual(evaluate_expression(df, "IsNull([A])").tolist(), [True, False, True, False])

        # IsEmpty (empty string or null)
        self.assertEqual(evaluate_expression(df, "IsEmpty([B])").tolist(), [True, True, False, True])

        # ToNumber
        num_res = evaluate_expression(df, "ToNumber([C])")
        self.assertAlmostEqual(num_res.iloc[0], 1500.50)
        self.assertAlmostEqual(num_res.iloc[1], -45.2)
        self.assertAlmostEqual(num_res.iloc[3], 100.0)

        # ToString
        str_res = evaluate_expression(df, "ToString([A])")
        self.assertEqual(str_res.iloc[0], "")
        self.assertEqual(str_res.iloc[1], "10.0")

        # Null literal
        df_score = pd.DataFrame({"Score": [95, 80]})
        score_res = evaluate_expression(df_score, "IF [Score] >= 90 THEN 'A' ELSE Null() ENDIF")
        self.assertEqual(score_res.iloc[0], "A")
        self.assertTrue(pd.isna(score_res.iloc[1]))

    def test_logical_operators_vectorized(self):
        df = pd.DataFrame({
            "Active": [True, True, False, False],
            "Score": [90, 60, 95, 40]
        })
        # AND with Series: should NOT raise pandas AmbiguityError
        and_res = evaluate_expression(df, "[Active] and [Score] > 70")
        self.assertEqual(and_res.tolist(), [True, False, False, False])

        # OR with Series
        or_res = evaluate_expression(df, "[Active] or [Score] > 70")
        self.assertEqual(or_res.tolist(), [True, True, True, False])

        # && and || symbols
        sym_res = evaluate_expression(df, "[Active] && [Score] > 70")
        self.assertEqual(sym_res.tolist(), [True, False, False, False])

        # NOT / !
        not_res = evaluate_expression(df, "not [Active]")
        self.assertEqual(not_res.tolist(), [False, False, True, True])

    def test_formula_node_integration(self):
        df = pd.DataFrame({
            "Item": ["apple", "banana", "cherry"],
            "Price": [1.50, 0.75, 3.00],
            "Qty": [10, 20, 5]
        })
        node = FormulaNode("f_node", {
            "formulas": [
                {"output_field": "Subtotal", "expression": "[Price] * [Qty]", "type": "float"},
                {"output_field": "Discount", "expression": "IF [Subtotal] >= 20 THEN 0.10 ELSE 0.0 ENDIF", "type": "float"},
                {"output_field": "FinalTotal", "expression": "[Subtotal] * (1 - [Discount])", "type": "float"},
                {"output_field": "Label", "expression": "Concat(TitleCase([Item]), ': $', ToString([FinalTotal]))", "type": "string"}
            ]
        })
        res = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(res["Subtotal"].tolist(), [15.0, 15.0, 15.0])
        self.assertEqual(res["FinalTotal"].tolist(), [15.0, 15.0, 15.0])
        self.assertEqual(res["Label"].iloc[0], "Apple: $15.0")

    def test_filter_node_custom_alteryx_syntax(self):
        df = pd.DataFrame({
            "Region": ["North East", "South East", "West Coast", "Midwest"],
            "Revenue": [1500, 300, 2200, 800]
        })
        # Test custom filter with Contains and logical AND
        node = FilterNode("flt_custom", {
            "mode": "custom",
            "expression": "Contains([Region], 'East') AND [Revenue] > 500"
        })
        res = node.execute({"I": df}, self.context)
        self.assertEqual(len(res["T"]), 1)
        self.assertEqual(res["T"].iloc[0]["Region"], "North East")
        self.assertEqual(len(res["F"]), 3)

    def test_error_handling_missing_column(self):
        df = pd.DataFrame({"Existing": [1, 2, 3]})
        # In evaluate_expression
        with self.assertRaises(FormulaExecutionError) as cm:
            evaluate_expression(df, "[NonExistent] + 10")
        self.assertIn("Column [NonExistent] not found in dataset", str(cm.exception))

        # In FormulaNode
        node = FormulaNode("f_err", {
            "formulas": [{"output_field": "Out", "expression": "[BadCol] * 2"}]
        })
        with self.assertRaises(NodeExecutionError) as cm:
            node.execute({"I": df}, self.context)
        self.assertIn("Error in formula for 'Out'", str(cm.exception))
        self.assertIn("Column [BadCol] not found", str(cm.exception))

        # In FilterNode custom mode
        flt = FilterNode("flt_err", {
            "mode": "custom",
            "expression": "[UnknownCol] > 10"
        })
        with self.assertRaises(NodeExecutionError) as cm:
            flt.execute({"I": df}, self.context)
        self.assertIn("Column [UnknownCol] not found", str(cm.exception))

    def test_safe_ast_disallows_arbitrary_code(self):
        df = pd.DataFrame({"A": [1, 2]})
        # Attempting dangerous calls
        with self.assertRaises(FormulaExecutionError):
            evaluate_expression(df, "__import__('os').system('echo pwned')")
        with self.assertRaises(FormulaExecutionError):
            evaluate_expression(df, "open('secrets.txt').read()")


if __name__ == "__main__":
    unittest.main()
