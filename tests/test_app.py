"""Regression tests for the interactive interpolation workflows."""

import io
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.runtime.media_file_manager import MediaFileManager

from tests.app_test_support import AppTestCase


class WorkflowTests(AppTestCase):

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
        # Isolate cached-file persistence from upload transport. Newer Streamlit
        # uploader integration is checked separately in test_app_features.py.
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

    def test_explicit_delimiter_override_recovers_from_wrong_interpretation(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "delimiter").set_value("|").run()
        self.app.text_area(key="input_reference_1d").set_value("X;Y\n0;0\n1;2\n2;4").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.import_setting(context, "delimiter").set_value(";").run()
        self.assert_no_exception()
        self.assertFalse(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(any("Read as:" in item.value for item in self.app.markdown))
        self.app.button(key="calculate_1d").click().run()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 1)

    def test_decimal_comma_and_dot_grouping_are_visible_and_used(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "delimiter").set_value(";").run()
        self.import_setting(context, "decimal").set_value(",").run()
        self.import_setting(context, "thousands").set_value(".").run()
        self.app.text_area(key="input_reference_1d").set_value(
            "X;Y\n1.000,00;2.000,00\n2.000,00;4.000,00\n3.000,00;6.000,00").run()
        self.assert_no_exception()
        preview = self.number_preview("X", "1.000,00")
        np.testing.assert_allclose(preview["X (number)"], [1000, 2000, 3000])
        np.testing.assert_allclose(preview["Y (number)"], [2000, 4000, 6000])
        self.app.text_area(key="input_queries_1d_Paste table").set_value("1500").run()
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 3000)

    def test_decimal_dot_and_comma_grouping_are_honored(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "delimiter").set_value("|").run()
        self.import_setting(context, "decimal").set_value(".").run()
        self.import_setting(context, "thousands").set_value(",").run()
        self.app.text_area(key="input_reference_1d").set_value(
            "X|Y\n1,000.25|2,000.5\n2,000.25|4,000.5").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("1500.25").run()
        self.assert_no_exception()
        preview = self.number_preview("X", "1,000.25")
        np.testing.assert_allclose(preview["X (number)"], [1000.25, 2000.25])
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 3000.5)

    def test_header_override_preserves_first_numeric_row(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "header").set_value(False).run()
        self.app.text_area(key="input_reference_1d").set_value("0,10\n1,20\n2,30").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0").run()
        self.assert_no_exception()
        self.assertEqual(self.reference_column("1d", 0).value, "col1")
        self.app.button(key="calculate_1d").click().run()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 10)

    def test_import_format_settings_survive_and_are_scoped_to_their_source(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        paste_context = "reference_1d_Paste table"
        self.import_setting(paste_context, "delimiter").set_value(";").run()
        self.import_setting(paste_context, "decimal").set_value(",").run()
        self.import_setting(paste_context, "thousands").set_value(".").run()
        self.app.session_state["cached_upload_reference_1d"] = ("known.csv", b"X,Y\n0,0\n1,2")
        self.app.radio(key="input_source_1d").set_value("Upload CSV").run()
        upload_context = "reference_1d_Upload CSV"
        self.assertEqual(self.import_setting(upload_context, "delimiter").value, "auto")
        self.assertEqual(self.import_setting(upload_context, "decimal").value, "auto")
        self.assertIsNone(self.import_setting(upload_context, "thousands").value)
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.assert_no_exception()
        self.assertEqual(self.import_setting(paste_context, "delimiter").value, ";")
        self.assertEqual(self.import_setting(paste_context, "decimal").value, ",")
        self.assertEqual(self.import_setting(paste_context, "thousands").value, ".")

    def test_2d_query_import_has_independent_number_settings_and_preview(self):
        context = "queries_2d_Example data_Paste table"
        self.import_setting(context, "delimiter").set_value(";").run()
        self.import_setting(context, "decimal").set_value(",").run()
        self.app.text_area(key="input_queries_2d_Example data").set_value("X;Y\n0,5;0,5\n1,5;1,0").run()
        self.assert_no_exception()
        preview = self.number_preview("X", "0,5")
        np.testing.assert_allclose(preview["X (number)"], [.5, 1.5])
        np.testing.assert_allclose(preview["Y (number)"], [.5, 1])
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        np.testing.assert_allclose(self.app.session_state["result_2d"]["data"]["zi"], [12.75, 17.5])

    def test_number_interpretation_change_marks_previous_result_stale(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "delimiter").set_value(";").run()
        self.import_setting(context, "decimal").set_value(".").run()
        self.app.text_area(key="input_reference_1d").set_value("X;Y\n0;1.000\n1;2.000\n2;3.000").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5").run()
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.assertEqual(original["yi"].iloc[0], 1.5)
        self.import_setting(context, "decimal").set_value(",").run()
        self.import_setting(context, "thousands").set_value(".").run()
        self.assert_no_exception()
        self.assertTrue(self.download("1d").proto.disabled)
        self.assertTrue(any("Inputs have changed" in item.value for item in self.app.warning))
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 1500)

    def test_export_format_changes_csv_bytes_without_invalidating_results(self):
        self.app.text_area(key="input_queries_1d_Example data").set_value("1.5\n2.5").run()
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        captured = {}
        original_add = MediaFileManager.add

        def capture(manager, path_or_data, mimetype, coordinates, file_name=None,
                    is_for_static_download=False):
            if file_name == "interpolated_1d.csv":
                captured["csv"] = path_or_data
            return original_add(manager, path_or_data, mimetype, coordinates, file_name,
                                is_for_static_download)

        with patch.object(MediaFileManager, "add", new=capture):
            self.app.selectbox(key="input_export_delimiter_1d").set_value(";").run()
            self.app.selectbox(key="input_export_decimal_1d").set_value(",").run()
        self.assert_no_exception()
        self.assertFalse(self.download("1d").proto.disabled)
        self.assertFalse(any("Inputs have changed" in item.value for item in self.app.warning))
        pd.testing.assert_frame_equal(original, self.app.session_state["result_1d"]["data"])
        self.assertTrue(captured["csv"].startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"xi;yi;status", captured["csv"])
        self.assertIn(b"1,5;21", captured["csv"])
        exported = pd.read_csv(io.BytesIO(captured["csv"]), sep=";", decimal=",")
        pd.testing.assert_frame_equal(original, exported, check_dtype=False)


if __name__ == "__main__":
    unittest.main()
