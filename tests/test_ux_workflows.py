"""Analytical-honesty checks for source identity and complete query batches."""

import io
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import interpolation
from tests.app_test_support import AppTestCase


class SourceAndBatchWorkflowTests(AppTestCase):
    def test_replacing_query_upload_with_equal_values_requires_new_calculation(self):
        content = b"X,Y\n0.5,0.5\n1.5,1"
        self.app.session_state["cached_upload_queries_2d"] = ("first.csv", content)
        self.app.radio(key="input_query_source_2d").set_value("Upload CSV").run()
        self.app.button(key="calculate_2d").click().run()
        previous = self.app.session_state["result_2d"]["data"].copy()
        self.assertFalse(self.download("2d").proto.disabled)

        self.app.session_state["cached_upload_queries_2d"] = ("replacement.csv", content)
        self.app.run()
        self.assert_no_exception()
        pd.testing.assert_frame_equal(previous, self.app.session_state["result_2d"]["data"])
        self.assertTrue(self.download("2d").proto.disabled)
        self.app.button(key="calculate_2d").click().run()
        self.assert_no_exception()
        self.assertFalse(self.download("2d").proto.disabled)

    def test_export_format_reuses_prepared_inputs_and_preserves_calculation(self):
        self.app.radio(key="input_source_1d").set_value("Paste table").run()
        self.app.text_area(key="input_reference_1d").set_value(
            "Distance,Reading\n0,0\n1,2\n2,4").run()
        self.app.text_area(key="input_queries_1d_Paste table").set_value("0.5\n1.5").run()
        self.app.button(key="calculate_1d").click().run()
        saved = self.app.session_state["result_1d"]
        values = saved["data"].copy(deep=True)
        fingerprint = saved["fingerprint"]
        chart_revision = saved["chart"].layout.uirevision

        # Each AppTest rerun imports the real parser/preparation functions anew.
        # Only the output format changes; neither input should need that work.
        with patch.object(interpolation, "read_pasted_table", wraps=interpolation.read_pasted_table) as parse, \
                patch.object(interpolation, "prepare_reference", wraps=interpolation.prepare_reference) as prepare:
            self.app.selectbox(key="input_export_decimal_1d").set_value(",").run()
            self.assert_no_exception()
            parse.assert_not_called()
            prepare.assert_not_called()

        current = self.app.session_state["result_1d"]
        pd.testing.assert_frame_equal(values, current["data"])
        self.assertEqual(current["fingerprint"], fingerprint)
        self.assertEqual(current["chart"].layout.uirevision, chart_revision)
        self.assertEqual(current["export_format"], (",", ","))
        self.assertFalse(self.download("1d").proto.disabled)

    def test_replacing_upload_with_equal_values_requires_new_calculation(self):
        content = b"X,Y\n0,0\n1,2\n2,4"
        self.app.session_state["cached_upload_reference_1d"] = ("first.csv", content)
        self.app.radio(key="input_source_1d").set_value("Upload CSV").run()
        self.app.text_area(key="input_queries_1d_Upload CSV").set_value("0.5\n1.5").run()
        self.app.button(key="calculate_1d").click().run()
        previous = self.app.session_state["result_1d"]["data"].copy()
        self.assertFalse(self.download("1d").proto.disabled)

        # A different file is a new source even when its prepared values match.
        self.app.session_state["cached_upload_reference_1d"] = ("replacement.csv", content)
        self.app.run()
        self.assert_no_exception()
        pd.testing.assert_frame_equal(previous, self.app.session_state["result_1d"]["data"])
        self.assertTrue(self.download("1d").proto.disabled)
        self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        self.assertFalse(self.download("1d").proto.disabled)

        # Original cells are part of import provenance, including spelling.
        self.app.session_state["cached_upload_reference_1d"] = (
            "replacement.csv", b"X,Y\n0.0,0.0\n1.0,2.0\n2.0,4.0")
        self.app.run()
        self.assert_no_exception()
        self.assertTrue(self.download("1d").proto.disabled)
        pd.testing.assert_frame_equal(previous, self.app.session_state["result_1d"]["data"])

    def test_full_query_batch_keeps_precision_order_duplicates_and_export_rows(self):
        queries = [8.1, 1.23456789012345, 8.1] * 833 + [0.0, 10.0]
        self.app.text_area(key="input_queries_1d_Example data").set_value(
            "\n".join(str(value) for value in queries)).run()
        with self.capture_downloads() as files:
            self.app.button(key="calculate_1d").click().run()
        self.assert_no_exception()
        saved = self.app.session_state["result_1d"]
        self.assertEqual(len(saved["data"]), 2501)
        np.testing.assert_array_equal(saved["data"]["xi"], queries)
        self.assertEqual(saved["data"]["status"].tolist(), ["Interpolated"] * 2501)
        points = next(trace for trace in saved["chart"].data
                      if trace.name == "Interpolated queries")
        np.testing.assert_array_equal(points.x, queries)

        exported = pd.read_csv(io.BytesIO(files["interpolated_1d.csv"]["data"]))
        pd.testing.assert_frame_equal(saved["data"], exported)
        self.assertIn(b"1.23456789012345", files["interpolated_1d.csv"]["data"])


if __name__ == "__main__":
    unittest.main()
