"""Regression tests for the interactive interpolation workflows."""

import logging
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "main.py"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Streamlit emits expected bare-mode and version deprecation logs in AppTest.
        for name in ("streamlit.runtime.scriptrunner_utils.script_run_context",
                     "streamlit.elements.lib.policies", "streamlit.deprecation_util"):
            logging.getLogger(name).setLevel(logging.ERROR)

    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assert_no_exception()

    def assert_no_exception(self):
        self.assertFalse(list(self.app.exception))

    def download(self, dimension):
        return next(element for element in self.app.get("download_button")
                    if element.proto.id.endswith(f"-download_{dimension}"))

    def reference_column(self, dimension, index):
        return next(element for element in self.app.selectbox
                    if element.key.startswith(f"input_column_{dimension}_")
                    and element.key.endswith(f"_{index}"))

    def query_column(self, axis):
        return next(element for element in self.app.selectbox
                    if element.key.startswith(f"input_query_{axis}_2d"))

    def test_both_workflows_render_and_compute_independently(self):
        self.assertEqual(len(self.app.tabs), 2)
        self.assertFalse(self.app.button(key="calculate_1d").disabled)
        self.assertFalse(self.app.button(key="calculate_2d").disabled)
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        surface = self.app.session_state["result_2d"]["data"].copy()
        np.testing.assert_allclose(surface["zi"], [12.75, 17.5, np.nan])
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        np.testing.assert_allclose(self.app.session_state["result_1d"]["data"]["yi"],
                                   [20, 25, 37, np.nan])
        pd.testing.assert_frame_equal(surface, self.app.session_state["result_2d"]["data"])

    def test_result_survives_rerun_with_download_enabled(self):
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.app.run()
        self.assert_no_exception()
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])
        self.assertFalse(self.download("1d").proto.disabled)
        self.assertFalse(any("Inputs have changed" in item.value for item in self.app.warning))

    def test_changed_queries_retain_previous_result_and_disable_download(self):
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.app.text_area(key="input_queries_1d_Example data").set_value("2\n4").run()
        self.assert_no_exception()
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])
        self.assertTrue(self.download("1d").proto.disabled)
        self.assertTrue(any("Inputs have changed" in item.value for item in self.app.warning))
        self.app.button(key="calculate_1d").click().run()
        self.assertFalse(self.download("1d").proto.disabled)
        np.testing.assert_allclose(self.app.session_state["result_1d"]["data"]["yi"], [22, 28])

    def test_nearest_removes_inapplicable_slope_option(self):
        self.app.selectbox(key="input_outside_1d").set_value("linear").run()
        self.app.selectbox(key="input_method_1d").set_value("nearest").run()
        self.assert_no_exception()
        outside = self.app.selectbox(key="input_outside_1d")
        self.assertEqual(outside.value, "nan")
        self.assertNotIn("Extend end slopes", outside.options)

    def test_invalid_query_is_rejected_without_losing_previous_results(self):
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.app.text_area(key="input_queries_1d_Example data").set_value("1\noops\n3").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(self.download("1d").proto.disabled)
        self.assertTrue(len(self.app.error))
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])

    def test_decimal_comma_queries_compute_as_decimal_values(self):
        self.app.text_area(key="input_queries_1d_Example data").set_value("1,5\n2,5").run()
        self.app.checkbox(key="input_decimal_1d_Example data").check().run()
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        result = self.app.session_state["result_1d"]["data"]
        np.testing.assert_allclose(result["xi"], [1.5, 2.5])
        np.testing.assert_allclose(result["yi"], [21, 23.5])

    def test_default_comma_lists_keep_all_values_across_lines(self):
        self.app.text_area(key="input_queries_1d_Example data").set_value("1,2\n3,4").run()
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        np.testing.assert_allclose(self.app.session_state["result_1d"]["data"]["xi"], [1, 2, 3, 4])

    def test_delimiters_without_numbers_do_not_enable_calculation(self):
        self.app.text_area(key="input_queries_1d_Example data").set_value(", ; \n\t").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)

    def test_nearest_chart_uses_steps_at_midpoints(self):
        self.app.selectbox(key="input_method_1d").set_value("nearest").run()
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        curve = self.app.session_state["result_1d"]["chart"].data[0]
        self.assertEqual(curve.line.shape, "hv")
        self.assertIn(1.0, curve.x)
        self.assertIn(3.0, curve.x)

    def test_reference_cleaning_reports_exclusions_and_averaging(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value(
            "X,Y\n0,0\n1,2\n1,4\n2,8\nbad,9").run()
        self.assert_no_exception()
        self.assertTrue(any("1 of 5 reference rows excluded" in item.value for item in self.app.warning))
        self.assertTrue(any("1 duplicate" in item.value for item in self.app.info))
        self.app.text_area(key="input_queries_1d_Paste table").set_value("1").run()
        self.app.button(key="calculate_1d").click().run()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 3)

    def test_reference_column_roles_stay_distinct(self):
        self.reference_column("1d", 0).set_value("Temperature (°C)").run()
        self.assert_no_exception()
        self.assertEqual(self.reference_column("1d", 1).value, "Time (s)")
        self.reference_column("2d", 0).set_value("Value").run()
        self.assert_no_exception()
        chosen = [self.reference_column("2d", i).value for i in range(3)]
        self.assertEqual(len(set(chosen)), 3)

    def test_2d_extra_query_columns_can_be_mapped_and_duplicates_kept(self):
        self.app.text_area(key="input_queries_2d_Example data").set_value(
            "label,QY,QX\nfirst,0.5,1.5\nsecond,0.5,1.5").run()
        self.query_column("x").set_value("QX").run()
        self.query_column("y").set_value("QY").run()
        self.assert_no_exception()
        self.assertFalse(self.app.button(key="calculate_2d").disabled)
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        result = self.app.session_state["result_2d"]["data"]
        np.testing.assert_allclose(result["xi"], [1.5, 1.5])
        np.testing.assert_allclose(result["yi"], [.5, .5])
        np.testing.assert_allclose(result["zi"], [15.25, 15.25])

    def test_invalid_2d_query_rows_block_whole_batch(self):
        self.app.text_area(key="input_queries_2d_Example data").set_value("X,Y\n0,0\nbad,1").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertTrue(any("row(s) 2" in item.value for item in self.app.error))
        self.assertFalse(self.app.button(key="calculate_1d").disabled)

    def test_pasted_reference_and_queries_survive_source_switch(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        reference = "X,Y\n0,0\n1,2\n2,4"
        self.app.text_area(key="input_reference_1d").set_value(reference).run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5\n1.5").run()
        self.app.radio(key="input_source_1d").set_value("Example data").run()
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.assert_no_exception()
        self.assertEqual(self.app.text_area(key="input_reference_1d").value, reference)
        self.assertEqual(self.app.text_area(key="input_queries_1d_Paste table").value, "0.5\n1.5")
        self.assertFalse(self.app.button(key="calculate_1d").disabled)

    def test_cached_reference_upload_survives_source_switch_and_can_be_cleared(self):
        # AppTest does not implement file-uploader interactions. Seed the exact
        # cached file record created by uploaded_table, then exercise the UI.
        self.app.session_state["cached_upload_reference_1d"] = (
            "known.csv", b"X,Y\n0,0\n1,2\n2,4")
        self.app.radio(key="input_source_1d").set_value("Upload CSV").run()
        self.app.text_area(key="input_queries_1d_Upload CSV").set_value("0.5").run()
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.app.radio(key="input_source_1d").set_value("Example data").run()
        self.app.radio(key="input_source_1d").set_value("Upload CSV").run()
        self.assert_no_exception()
        self.assertFalse(self.download("1d").proto.disabled)
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])
        self.assertTrue(any("Loaded: known.csv" in item.value for item in self.app.caption))
        self.app.button(key="clear_upload_reference_1d").click().run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(self.download("1d").proto.disabled)
        self.assertEqual(self.app.session_state["generation_upload_reference_1d"], 1)
        self.assertFalse(any("Loaded: known.csv" in item.value for item in self.app.caption))

    def test_cached_query_upload_survives_mode_switch_and_can_be_cleared(self):
        self.app.session_state["cached_upload_queries_2d"] = (
            "queries.csv", b"X,Y\n0.5,0.5\n1.5,1")
        self.app.radio(key="input_query_source_2d").set_value("Upload CSV").run()
        self.app.button(key="calculate_2d").click().run()
        original = self.app.session_state["result_2d"]["data"].copy()
        self.app.radio(key="input_query_source_2d").set_value("Paste table").run()
        self.app.radio(key="input_query_source_2d").set_value("Upload CSV").run()
        self.assert_no_exception()
        self.assertFalse(self.download("2d").proto.disabled)
        pd.testing.assert_frame_equal(original, self.app.session_state["result_2d"]["data"])
        self.app.button(key="clear_upload_queries_2d").click().run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertTrue(self.download("2d").proto.disabled)
        self.assertEqual(self.app.session_state["generation_upload_queries_2d"], 1)


if __name__ == "__main__":
    unittest.main()
