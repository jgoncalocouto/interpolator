"""State and recovery contracts for the independent Excel tips workflow."""

import unittest
from unittest.mock import patch
from zipfile import ZipFile
import io
import xml.etree.ElementTree as ET

import pandas as pd

from tests.app_test_support import AppTestCase


class ExcelTipsWorkflowTests(AppTestCase):
    def formula_codes(self):
        return [element.value for element in self.app.code
                if element.value.startswith(("=IF(", "=LET("))]

    def formula(self):
        formulas = self.formula_codes()
        self.assertEqual(len(formulas), 1)
        return formulas[0]

    def test_final_tab_starts_with_copyable_formula_and_useful_guidance(self):
        self.assertEqual(self.app.tabs[-1].label, "Tips & tricks")
        self.assertEqual(self.app.radio(key="input_excel_formula_style").value, "compact")
        formula = self.formula()
        self.assertTrue(formula.startswith("=LET("))
        self.assertIn("XLOOKUP", formula)
        self.assertNotIn("\n", formula)
        for reference in ("$A$2:$A$7", "$B$2:$B$7", "D2:D5"):
            self.assertIn(reference, formula)
        self.assertTrue(any("Excel 2021" in item.value
                            for item in self.app.info))
        self.assertTrue(any("#N/A" in item.value for item in self.app.info))
        self.assertFalse(any(element.key == "input_excel_outside" for element in self.app.selectbox))
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
        self.assertIn("q,Queries!G2,", self.formula())
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
        self.assertIn("q;D2:D5;", after)
        self.assertIn("XLOOKUP(q;x;x;NA();-1)", after)
        self.assertNotIn("'Data; 2026'", after)

    def test_outside_policy_updates_formula_and_worked_example(self):
        self.app.radio(key="input_excel_formula_style").set_value("guarded").run()
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

    def test_guarded_mode_restores_policy_and_compact_exposes_na_outside(self):
        compact = self.formula()
        example = next(element.value for element in self.app.dataframe
                       if "E · expected Yi" in element.value.columns)
        self.assertEqual(example["E · expected Yi"].iloc[3], "#N/A")
        self.app.radio(key="input_excel_formula_style").set_value("guarded").run()
        self.app.selectbox(key="input_excel_outside").set_value("linear").run()
        guarded = self.formula()
        self.assertIn("MAP(", guarded)
        self.assertNotEqual(guarded, compact)
        self.app.radio(key="input_excel_formula_style").set_value("compact").run()
        self.assertEqual(self.formula(), compact)
        self.assertFalse(any(element.key == "input_excel_outside" for element in self.app.selectbox))
        self.app.radio(key="input_excel_formula_style").set_value("guarded").run()
        self.assertEqual(self.app.selectbox(key="input_excel_outside").value, "linear")
        self.assertEqual(self.formula(), guarded)

    def test_downloaded_example_preserves_native_excel_formula_and_verified_cache(self):
        with self.capture_downloads() as files:
            self.app.run()
        payload = next(value["data"] for name, value in files.items()
                       if name == "linear_interpolation_test.xlsx")
        self.assertTrue(payload.startswith(b"PK"))
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(io.BytesIO(payload)) as archive:
            root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            shared = ["".join(item.itertext()) for item in ET.fromstring(
                archive.read("xl/sharedStrings.xml")).findall("s:si", namespace)]
            cells = {cell.attrib["r"]: cell for cell in root.findall(".//s:c", namespace)}
            formula = cells["E6"].find("s:f", namespace)
            self.assertIn("XLOOKUP", formula.text)
            self.assertEqual(formula.attrib.get("ref"), "E6:E17")
            self.assertEqual([address for address, cell in cells.items()
                              if address.startswith("E") and cell.find("s:f", namespace) is not None], ["E6"])
            expected = [18, 20, 22, 25, 28, 37, 42, "#N/A", "#N/A", 25, 39, 40.5]
            for row, target in enumerate(expected, start=6):
                cell = cells[f"E{row}"]
                text = cell.find("s:v", namespace).text
                self.assertEqual(text if cell.attrib.get("t") == "e" else float(text), target)
                check = cells[f"G{row}"]
                check_value = check.find("s:v", namespace).text
                if check.attrib.get("t") == "s":
                    check_value = shared[int(check_value)]
                self.assertEqual(check_value, "Match")

    def test_generator_edits_preserve_both_saved_results_and_fresh_downloads(self):
        self.app.button(key="calculate_1d").click().run()
        self.app.button(key="calculate_2d").click().run()
        saved = {dimension: {
            "data": self.app.session_state[f"result_{dimension}"]["data"].copy(deep=True),
            "fingerprint": self.app.session_state[f"result_{dimension}"]["fingerprint"],
            "chart": self.app.session_state[f"result_{dimension}"]["chart"].to_json(),
        } for dimension in ("1d", "2d")}
        self.app.text_input(key="input_excel_query_range").set_value("H12:H15").run()
        self.app.radio(key="input_excel_formula_style").set_value("guarded").run()
        self.app.selectbox(key="input_excel_outside").set_value("linear").run()
        self.app.selectbox(key="input_excel_separator").set_value(";").run()
        self.app.radio(key="input_excel_formula_style").set_value("compact").run()
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
