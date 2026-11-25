"""State and recovery contracts for the independent Excel tips workflow."""

import unittest
from unittest.mock import patch

import pandas as pd

from tests.app_test_support import AppTestCase


class ExcelTipsWorkflowTests(AppTestCase):
    def formula_codes(self):
        return [element.value for element in self.app.code
                if element.value.startswith("=IF(")]

    def formula(self):
        formulas = self.formula_codes()
        self.assertEqual(len(formulas), 1)
        return formulas[0]

    def test_final_tab_starts_with_copyable_formula_and_useful_guidance(self):
        self.assertEqual(self.app.tabs[-1].label, "Tips & tricks")
        formula = self.formula()
        self.assertNotIn("\n", formula)
        for reference in ("$A$2:$A$7", "$B$2:$B$7", "D2:D5"):
            self.assertIn(reference, formula)
        self.assertTrue(any("Microsoft 365 or Excel 2024" in item.value
                            for item in self.app.info))
        self.assertTrue(any("copy icon" in item.value for item in self.app.markdown))
        self.assertTrue(any("outside your X, Y, and Xi ranges" in item.value
                            for item in self.app.markdown))
        labels = [item.label for item in self.app.expander]
        self.assertIn("Try a worked example", labels)
        self.assertIn("Fix common Excel problems", labels)
        self.assertIn("Get dependable interpolation results", labels)

    def test_generator_works_with_both_calculation_workflows_missing_or_invalid(self):
        expected = self.formula()
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.radio(key="input_source_2d").set_value("Paste table").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertEqual(self.formula(), expected)
        self.app.text_area(key="input_reference_1d").set_value("X,Y\nbad,bad\nbad,bad").run()
        self.app.text_area(key="input_reference_2d").set_value("Only one column\nbad").run()
        self.assert_no_exception()
        self.assertTrue(len(self.app.error))
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertEqual(self.formula(), expected)

    def test_invalid_range_removes_formula_and_correcting_it_recovers(self):
        expected = self.formula()
        self.app.text_input(key="input_excel_x_range").set_value("A2:B7").run()
        self.assert_no_exception()
        self.assertEqual(self.formula_codes(), [])
        self.assertTrue(any("one row or one column" in item.value for item in self.app.error))
        self.app.text_input(key="input_excel_x_range").set_value("$A$2:$A$4").run()
        self.assertEqual(self.formula_codes(), [])
        self.assertTrue(any("equal length" in item.value for item in self.app.error))
        self.app.text_input(key="input_excel_x_range").set_value("$A$2:$A$7").run()
        self.assert_no_exception()
        self.assertEqual(self.formula(), expected)
        self.assertFalse(list(self.app.error))

    def test_custom_horizontal_ranges_and_scalar_query_update_immediately(self):
        # Streamlit reports this conflict only once per Python process. Reset
        # its notice flag so earlier workflow tests cannot hide a regression.
        with patch("streamlit.elements.lib.policies._shown_default_value_warning", False), \
                self.assertNoLogs("streamlit.elements.lib.policies", level="WARNING"):
            self.app.text_input(key="input_excel_x_range").set_value("'Inputs, 2026'!$B$2:$D$2").run()
            self.app.text_input(key="input_excel_y_range").set_value("'Inputs, 2026'!$B$3:$D$3").run()
            self.app.text_input(key="input_excel_query_range").set_value("Queries!G2:I2").run()
        self.assert_no_exception()
        formula = self.formula()
        for reference in ("'Inputs, 2026'!$B$2:$D$2", "'Inputs, 2026'!$B$3:$D$3", "Queries!G2:I2"):
            self.assertIn(reference, formula)
        self.assertNotIn("D2:D5", formula)
        self.assertTrue(any("3 known X/Y pairs · 3 query cell(s)" in item.value
                            for item in self.app.caption))
        self.app.text_input(key="input_excel_query_range").set_value("Queries!G2").run()
        self.assert_no_exception()
        self.assertIn("MAP(Queries!G2,", self.formula())
        self.assertTrue(any("1 query cell(s)" in item.value for item in self.app.caption))

    def test_separator_change_preserves_comma_in_sheet_name(self):
        reference = "'Data, 2026'!$A$2:$A$7"
        self.app.text_input(key="input_excel_x_range").set_value(reference).run()
        before = self.formula()
        self.app.selectbox(key="input_excel_separator").set_value(";").run()
        self.assert_no_exception()
        after = self.formula()
        self.assertNotEqual(before, after)
        self.assertIn(reference, after)
        self.assertIn("MAP(D2:D5;ISNUMBER(D2:D5);ISBLANK(D2:D5);", after)
        self.assertNotIn("'Data; 2026'", after)

    def test_outside_policy_updates_formula_and_worked_example(self):
        formulas = {self.formula()}
        for policy, expected in (("nan", "Blank"), ("clamp", "42"), ("linear", "45")):
            with self.subTest(policy=policy):
                self.app.selectbox(key="input_excel_outside").set_value(policy).run()
                self.assert_no_exception()
                formulas.add(self.formula())
                example = next(element.value for element in self.app.dataframe
                               if "E · expected Yi" in element.value.columns)
                self.assertEqual(example["E · expected Yi"].iloc[3], expected)
        self.assertEqual(len(formulas), 3)

    def test_generator_edits_preserve_both_saved_results_and_fresh_downloads(self):
        self.app.button(key="calculate_1d").click().run()
        self.app.button(key="calculate_2d").click().run()
        saved = {dimension: {
            "data": self.app.session_state[f"result_{dimension}"]["data"].copy(deep=True),
            "fingerprint": self.app.session_state[f"result_{dimension}"]["fingerprint"],
            "chart": self.app.session_state[f"result_{dimension}"]["chart"].to_json(),
        } for dimension in ("1d", "2d")}
        self.app.text_input(key="input_excel_query_range").set_value("H12:H15").run()
        self.app.selectbox(key="input_excel_outside").set_value("linear").run()
        self.app.selectbox(key="input_excel_separator").set_value(";").run()
        self.assert_no_exception()
        self.assertIn("H12:H15", self.formula())
        for dimension, expected in saved.items():
            actual = self.app.session_state[f"result_{dimension}"]
            pd.testing.assert_frame_equal(actual["data"], expected["data"])
            self.assertEqual(actual["fingerprint"], expected["fingerprint"])
            self.assertEqual(actual["chart"].to_json(), expected["chart"])
            self.assertFalse(self.download(dimension).proto.disabled)
        self.assertFalse(any("Inputs have changed" in item.value for item in self.app.warning))


if __name__ == "__main__":
    unittest.main()
