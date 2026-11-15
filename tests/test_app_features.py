"""Feature-level checks for numerical choices, recovery, previews, and files."""

import io
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from tests.app_test_support import AppTestCase


class FeatureWorkflowTests(AppTestCase):
    def assert_stale(self, dimension, original):
        self.assert_no_exception()
        self.assertTrue(self.download(dimension).proto.disabled)
        self.assertTrue(any("Inputs have changed" in item.value for item in self.app.warning))
        pd.testing.assert_frame_equal(original, self.app.session_state[f"result_{dimension}"]["data"])

    def test_minimum_distinct_reference_points_are_required_before_calculation(self):
        cases = [
            ("1d", "X,Y\n0,10\n0,20", "0", "two different numeric X values"),
            ("2d", "X,Y,Z\n0,0,10\n1,1,20", "X,Y\n0.5,0.5", "three different numeric coordinate pairs"),
        ]
        for dimension, reference, query, message in cases:
            with self.subTest(dimension=dimension):
                self.app.radio(key=f"input_source_{dimension}").set_value("Paste table").run()
                self.app.text_area(key=f"input_reference_{dimension}").set_value(reference).run()
                self.app.text_area(key=f"input_queries_{dimension}_Paste table").set_value(query).run()
                self.assert_no_exception()
                self.assertTrue(self.app.button(key=f"calculate_{dimension}").disabled)
                self.assertTrue(any(message in item.value for item in self.app.error))

    def test_chart_rendering_failure_keeps_result_table_and_download_available(self):
        for dimension in ("1d", "2d"):
            with self.subTest(dimension=dimension):
                with patch("plotly.graph_objects.Figure", side_effect=RuntimeError("Chart unavailable")):
                    with self.capture_downloads() as files:
                        self.app.button(key=f"calculate_{dimension}").click().run()
                self.assert_no_exception()
                result = self.app.session_state[f"result_{dimension}"]
                self.assertIsNone(result["chart"])
                self.assertTrue(any("table is still available" in item.value for item in self.app.info))
                self.assertFalse(self.download(dimension).proto.disabled)
                exported = pd.read_csv(io.BytesIO(files[f"interpolated_{dimension}.csv"]["data"]))
                pd.testing.assert_frame_equal(result["data"], exported, check_dtype=False)

    def test_ambiguous_auto_format_is_visible_and_explicit_settings_resolve_it(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value("X;Y\n0;1,234\n1;2,345").run()
        self.assert_no_exception()
        self.assertTrue(any("could use a decimal mark or a thousands separator" in item.value
                            for item in self.app.warning))
        np.testing.assert_allclose(self.number_preview("Y")["Y (number)"], [1.234, 2.345])
        context = "reference_1d_Paste table"
        self.import_setting(context, "decimal").set_value(".").run()
        self.import_setting(context, "thousands").set_value(",").run()
        self.assert_no_exception()
        self.assertFalse(list(self.app.warning))
        np.testing.assert_allclose(self.number_preview("Y")["Y (number)"], [1234, 2345])

    def test_linear_outside_policies_control_values_statuses_and_chart(self):
        self.app.text_area(key="input_queries_1d_Example data").set_value("-1\n1\n12").run()
        cases = [
            ("nan", [np.nan, 20, np.nan], "left blank"),
            ("clamp", [18, 20, 42], "boundary value"),
            ("linear", [16, 20, 45], "extended slope"),
        ]
        for policy, expected, status in cases:
            with self.subTest(policy=policy):
                self.app.selectbox(key="input_outside_1d").set_value(policy).run()
                self.app.button(key="calculate_1d").click().run()
                self.assert_no_exception()
                saved = self.app.session_state["result_1d"]
                np.testing.assert_allclose(saved["data"]["yi"], expected)
                self.assertEqual(saved["outside_count"], 2)
                self.assertEqual(saved["data"]["status"].iloc[1], "Interpolated")
                for index in (0, 2):
                    self.assertIn(status, saved["data"]["status"].iloc[index])
                outside = [trace for trace in saved["chart"].data if trace.name == "Outside known data"]
                if policy == "nan":
                    self.assertEqual(outside, [])
                else:
                    np.testing.assert_allclose(outside[0].x, [-1, 12])
                    np.testing.assert_allclose(outside[0].y, [expected[0], expected[2]])

    def test_nearest_returns_samples_and_honors_blank_or_boundary_policy(self):
        self.app.selectbox(key="input_method_1d").set_value("nearest").run()
        self.app.text_area(key="input_queries_1d_Example data").set_value("1\n3\n12").run()
        for policy, expected in [("nan", [18, 22, np.nan]), ("clamp", [18, 22, 42])]:
            with self.subTest(policy=policy):
                self.app.selectbox(key="input_outside_1d").set_value(policy).run()
                self.app.button(key="calculate_1d").click().run()
                self.assert_no_exception()
                saved = self.app.session_state["result_1d"]
                np.testing.assert_allclose(saved["data"]["yi"], expected)
                self.assertEqual(saved["method"], "Nearest sample")
                self.assertTrue(saved["data"]["status"].iloc[-1].startswith("Outside"))
                self.assertEqual(saved["chart"].data[0].line.shape, "hv")

    def test_all_2d_methods_honor_both_outside_policies(self):
        self.app.text_area(key="input_queries_2d_Example data").set_value("X,Y\n1,1\n3,1").run()
        for method in ("auto", "linear", "nearest", "regular", "rbf"):
            for policy, outside_value in [("nan", np.nan), ("nearest", 19)]:
                with self.subTest(method=method, policy=policy):
                    self.app.selectbox(key="input_method_2d").set_value(method).run()
                    self.app.selectbox(key="input_outside_2d").set_value(policy).run()
                    self.app.button(key="calculate_2d").click().run()
                    self.assert_no_exception()
                    self.assertFalse(list(self.app.error))
                    saved = self.app.session_state["result_2d"]
                    np.testing.assert_allclose(saved["data"]["zi"], [16, outside_value], atol=1e-10)
                    self.assertEqual(saved["outside_count"], 1)
                    self.assertEqual(saved["data"]["status"].iloc[0], "Interpolated")
                    expected_status = "left blank" if policy == "nan" else "nearest sample"
                    self.assertIn(expected_status, saved["data"]["status"].iloc[1])
                    self.assertEqual(saved["chart"].data[0].type, "heatmap")
                    self.assertFalse(self.download("2d").proto.disabled)

    def test_automatic_scattered_surface_uses_triangle_domain(self):
        self.app.radio(key="input_source_2d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_2d").set_value(
            "X,Y,Z\n0,0,0\n1,0,1\n0,1,2").run()
        self.app.text_area(key="input_queries_2d_Paste table").set_value(
            "X,Y\n0.25,0.25\n0.8,0.8").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        saved = self.app.session_state["result_2d"]
        self.assertIn("scattered", saved["method"])
        np.testing.assert_allclose(saved["data"]["zi"], [.75, np.nan])
        self.assertTrue(saved["data"]["status"].iloc[1].startswith("Outside"))
        self.assertTrue(np.isnan(np.asarray(saved["chart"].data[0].z, dtype=float)[-1, -1]))

    def test_invalid_grid_preserves_old_results_and_recovers_with_automatic(self):
        self.app.button(key="calculate_2d").click().run()
        original = self.app.session_state["result_2d"]["data"].copy()
        self.app.radio(key="input_source_2d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_2d").set_value(
            "X,Y,Z\n0,0,0\n1,0,1\n0,1,2").run()
        self.app.text_area(key="input_queries_2d_Paste table").set_value("X,Y\n0.25,0.25").run()
        self.app.selectbox(key="input_method_2d").set_value("regular").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_stale("2d", original)
        self.assertTrue(any("every X/Y combination" in item.value for item in self.app.error))
        self.app.selectbox(key="input_method_2d").set_value("auto").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        self.assertFalse(list(self.app.error))
        self.assertFalse(self.download("2d").proto.disabled)
        np.testing.assert_allclose(self.app.session_state["result_2d"]["data"]["zi"], [.75])

    def test_collinear_surface_error_preserves_results_and_corrected_data_recovers(self):
        self.app.button(key="calculate_2d").click().run()
        original = self.app.session_state["result_2d"]["data"].copy()
        self.app.radio(key="input_source_2d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_2d").set_value(
            "X,Y,Z\n0,0,0\n1,1,2\n2,2,4").run()
        self.app.text_area(key="input_queries_2d_Paste table").set_value("X,Y\n0.5,0.5").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_stale("2d", original)
        self.assertTrue(any("line" in item.value for item in self.app.error))
        self.app.text_area(key="input_reference_2d").set_value(
            "X,Y,Z\n0,0,0\n1,0,1\n0,1,1\n1,1,2").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        self.assertFalse(list(self.app.error))
        self.assertFalse(self.download("2d").proto.disabled)
        self.assertEqual(self.app.session_state["result_2d"]["data"]["zi"].iloc[0], 1)

    def test_reference_edits_mark_results_stale_until_recalculated(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value("X,Y\n0,0\n1,2\n2,4").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5").run()
        self.app.button(key="calculate_1d").click().run()
        original = self.app.session_state["result_1d"]["data"].copy()
        self.app.text_area(key="input_reference_1d").set_value("X,Y\n0,0\n1,4\n2,8").run()
        self.assert_stale("1d", original)
        self.app.button(key="calculate_1d").click().run()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 2)
        self.assertFalse(self.download("1d").proto.disabled)

    def test_reference_column_change_marks_results_stale_and_retains_old_labels(self):
        self.app.button(key="calculate_2d").click().run()
        original = self.app.session_state["result_2d"]["data"].copy()
        original_columns = self.app.session_state["result_2d"]["columns"].copy()
        self.reference_column("2d", 0).set_value("Y").run()
        self.assert_stale("2d", original)
        self.assertEqual(self.app.session_state["result_2d"]["columns"], original_columns)

    def test_method_and_outside_changes_each_invalidate_previous_results(self):
        for dimension in ("1d", "2d"):
            self.app.button(key=f"calculate_{dimension}").click().run()
            original = self.app.session_state[f"result_{dimension}"]["data"].copy()
            method_key = f"input_method_{dimension}"
            original_method = self.app.selectbox(key=method_key).value
            self.app.selectbox(key=method_key).set_value("nearest").run()
            self.assert_stale(dimension, original)
            self.app.selectbox(key=method_key).set_value(original_method).run()
            self.assertFalse(self.download(dimension).proto.disabled)
            outside_key = f"input_outside_{dimension}"
            self.app.selectbox(key=outside_key).set_value("clamp" if dimension == "1d" else "nearest").run()
            self.assert_stale(dimension, original)
            self.app.selectbox(key=outside_key).set_value("nan").run()
            self.assertFalse(self.download(dimension).proto.disabled)

    def test_uploaded_2d_reference_and_queries_parse_locale_and_clear_independently(self):
        # Isolate locale parsing and independent cache clearing from upload transport.
        self.app.session_state["cached_upload_reference_2d"] = (
            "surface.csv", b"X;Y;Z\n0,0;0,0;0,0\n1,0;0,0;1,0\n0,0;1,0;2,0\n1,0;1,0;3,0")
        self.app.radio(key="input_source_2d").set_value("Upload CSV").run()
        reference_context = "reference_2d_Upload CSV"
        self.import_setting(reference_context, "delimiter").set_value(";").run()
        self.import_setting(reference_context, "decimal").set_value(",").run()
        self.app.session_state["cached_upload_queries_2d"] = (
            "points.csv", b"note;QX;QY\nfirst;0,25;0,25\nsecond;0,5;0,5")
        self.app.radio(key="input_query_source_2d").set_value("Upload CSV").run()
        query_context = "queries_2d_Upload CSV_Upload CSV"
        self.import_setting(query_context, "delimiter").set_value(";").run()
        self.import_setting(query_context, "decimal").set_value(",").run()
        self.query_column("x").set_value("QX").run()
        self.query_column("y").set_value("QY").run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        original = self.app.session_state["result_2d"]["data"].copy()
        np.testing.assert_allclose(original["zi"], [.75, 1.5])
        self.assertTrue(any("Loaded: surface.csv" in item.value for item in self.app.caption))
        self.assertTrue(any("Loaded: points.csv" in item.value for item in self.app.caption))
        self.app.button(key="clear_upload_reference_2d").click().run()
        self.assert_stale("2d", original)
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertTrue(any("Loaded: points.csv" in item.value for item in self.app.caption))
        self.app.button(key="clear_upload_queries_2d").click().run()
        self.assert_no_exception()
        self.assertFalse(any("Loaded: points.csv" in item.value for item in self.app.caption))

    @unittest.skipUnless(hasattr(AppTest, "file_uploader"),
                         "This Streamlit version does not simulate file uploads")
    def test_actual_upload_widgets_read_references_and_queries_and_clear(self):
        self.app.radio(key="input_source_1d").set_value("Upload CSV").run()
        self.app.file_uploader(key="upload_reference_1d_0").set_value(
            ("curve.csv", b"X,Y\n0,0\n1,2\n2,4", "text/csv")).run()
        self.app.text_area(key="input_queries_1d_Upload CSV").set_value("0.5").run()
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        self.assertEqual(self.app.session_state["result_1d"]["data"]["yi"].iloc[0], 1)
        self.app.radio(key="input_source_2d").set_value("Upload CSV").run()
        self.app.file_uploader(key="upload_reference_2d_0").set_value(
            ("surface.csv", b"X,Y,Z\n0,0,0\n1,0,1\n0,1,2\n1,1,3", "text/csv")).run()
        self.app.radio(key="input_query_source_2d").set_value("Upload CSV").run()
        self.app.file_uploader(key="upload_queries_2d_0").set_value(
            ("queries.csv", b"QX,QY\n0.25,0.25", "text/csv")).run()
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        self.assertEqual(self.app.session_state["result_2d"]["data"]["zi"].iloc[0], .75)
        self.app.button(key="clear_upload_queries_2d").click().run()
        self.assert_no_exception()
        self.assertIsNone(self.app.file_uploader(key="upload_queries_2d_1").value)
        self.assertTrue(self.app.button(key="calculate_2d").disabled)
        self.assertTrue(self.download("2d").proto.disabled)
        self.app.button(key="clear_upload_reference_2d").click().run()
        self.assert_no_exception()
        self.assertIsNone(self.app.file_uploader(key="upload_reference_2d_1").value)

    def test_example_downloads_are_valid_bom_encoded_csv_files(self):
        with self.capture_downloads() as files:
            self.app.run()
        for dimension, rows, columns in [("1d", 6, 2), ("2d", 9, 3)]:
            with self.subTest(dimension=dimension):
                download = files[f"example_{dimension}.csv"]
                self.assertEqual(download["mime"], "text/csv")
                self.assertTrue(download["data"].startswith(b"\xef\xbb\xbf"))
                table = pd.read_csv(io.BytesIO(download["data"]))
                self.assertEqual(table.shape, (rows, columns))
                if dimension == "1d":
                    self.assertEqual(table.columns.tolist(), ["Time (s)", "Temperature (°C)"])
                    self.assertEqual(table.iloc[0].tolist(), [0, 18])
                else:
                    self.assertEqual(table.columns.tolist(), ["X", "Y", "Value"])
                    self.assertEqual(table.iloc[0].tolist(), [0, 0, 10])

    def test_2d_tsv_download_has_correct_name_mime_precision_and_status(self):
        self.app.text_area(key="input_queries_2d_Example data").set_value(
            "X,Y\n0.123456789012345,0.987654321098765\n3,1").run()
        self.app.button(key="calculate_2d").click().run()
        original = self.app.session_state["result_2d"]["data"].copy()
        with self.capture_downloads() as files:
            self.app.selectbox(key="input_export_delimiter_2d").set_value("\t").run()
        self.assert_no_exception()
        self.assertFalse(self.download("2d").proto.disabled)
        self.assertEqual(self.download("2d").proto.label, "Download results as TSV")
        download = files["interpolated_2d.tsv"]
        self.assertEqual(download["mime"], "text/tab-separated-values")
        self.assertEqual(self.download("2d").proto.url, download["url"])
        self.assertTrue(download["data"].startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"0.123456789012345", download["data"])
        self.assertIn("Outside · left blank".encode(), download["data"])
        table = pd.read_csv(io.BytesIO(download["data"]), sep="\t")
        pd.testing.assert_frame_equal(original, table, check_exact=False, rtol=1e-14)
        pd.testing.assert_frame_equal(original, self.app.session_state["result_2d"]["data"])

    def test_conflicting_decimal_and_thousands_settings_block_and_recover(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value("X,Y\n0,0\n1,2").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5").run()
        context = "reference_1d_Paste table"
        self.import_setting(context, "decimal").set_value(".").run()
        self.import_setting(context, "thousands").set_value(".").run()
        self.assert_no_exception()
        self.assertTrue(self.app.button(key="calculate_1d").disabled)
        self.assertTrue(any("must be different" in item.value for item in self.app.error))
        self.import_setting(context, "thousands").set_value(None).run()
        self.assert_no_exception()
        self.assertFalse(self.app.button(key="calculate_1d").disabled)
        self.assertFalse(list(self.app.error))

    def test_empty_and_header_only_reference_and_query_tables_block_calculation(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5").run()
        for text in ("", "X,Y"):
            with self.subTest(reference=text):
                self.app.text_area(key="input_reference_1d").set_value(text).run()
                self.assert_no_exception()
                self.assertTrue(self.app.button(key="calculate_1d").disabled)
        for text in ("", "X,Y"):
            with self.subTest(query=text):
                self.app.text_area(key="input_queries_2d_Example data").set_value(text).run()
                self.assert_no_exception()
                self.assertTrue(self.app.button(key="calculate_2d").disabled)

    def test_numeric_preview_keeps_first_five_raw_rows_before_cleaning(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value(
            "X,Y\n3,30\n1,10\n1,12\nbad,4\n2,20\n4,40\n5,50").run()
        self.assert_no_exception()
        preview = self.number_preview("X", "3")
        self.assertEqual(len(preview), 5)
        self.assertEqual(preview["X (original)"].tolist(), ["3", "1", "1", "bad", "2"])
        np.testing.assert_allclose(preview["X (number)"], [3, 1, 1, np.nan, 2])
        self.assertTrue(any("1 of 7 reference rows excluded" in item.value for item in self.app.warning))
        self.assertTrue(any("1 duplicate" in item.value for item in self.app.info))
        prepared = next(element.value for element in self.app.dataframe
                        if element.value.columns.tolist() == ["X", "Y"] and len(element.value) == 5)
        np.testing.assert_allclose(prepared["X"], [1, 2, 3, 4, 5])
        self.assertEqual(prepared["Y"].iloc[0], 11)


if __name__ == "__main__":
    unittest.main()
