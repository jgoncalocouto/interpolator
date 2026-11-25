"""Contracts for result presentation, upload ingestion, and support links."""

from html.parser import HTMLParser
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from streamlit.proto.Common_pb2 import FileURLs
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec

import coffee_widget
import main
from interpolation import numeric_columns


class ResultStatusTests(unittest.TestCase):
    def test_status_explains_each_outside_data_policy(self):
        cases = {
            "nan": "Outside · left blank",
            "clamp": "Outside · boundary value",
            "linear": "Outside · extended slope",
            "nearest": "Outside · nearest sample",
        }
        for policy, outside_label in cases.items():
            with self.subTest(policy=policy):
                result = main.result_status(
                    np.array([True, False, False]), np.array([2.0, 3.0, np.nan]), policy)
                self.assertEqual(result.tolist(),
                                 ["Interpolated", outside_label, "Outside · left blank"])

    def test_nonfinite_inside_results_are_unavailable(self):
        result = main.result_status(np.array([True, True, False, False]),
                                    np.array([np.nan, np.inf, np.nan, np.inf]), "nearest")
        self.assertEqual(result.tolist(),
                         ["Unavailable", "Unavailable", "Outside · left blank", "Outside · left blank"])


class CalculationPresentationTests(unittest.TestCase):
    def setUp(self):
        self.curve = pd.DataFrame({"Position": [0.0, 1.0, 2.0],
                                   "Reading": [10.0, 20.0, 40.0]})
        self.surface = pd.DataFrame({"Easting": [0.0, 2.0, 0.0],
                                     "Northing": [0.0, 0.0, 2.0],
                                     "Elevation": [0.0, 4.0, 6.0]})

    def test_record_retains_query_identity_and_calculation_metadata(self):
        query = pd.DataFrame({"xi": [3.0, 0.5, -1.0, 0.5]}, index=[8, 1, 1, 6])
        original = query.copy(deep=True)
        selected = ["Position", "Reading"]
        record = main.calculate("1d", self.curve, selected, query,
                                "nearest", "clamp", "calculation-id")
        pd.testing.assert_frame_equal(query, original)
        self.assertEqual(record["data"].index.tolist(), [8, 1, 1, 6])
        np.testing.assert_array_equal(record["data"]["xi"], original["xi"])
        self.assertEqual(record["fingerprint"], "calculation-id")
        self.assertEqual(record["columns"], selected)
        self.assertEqual(record["method"], "Nearest sample")
        self.assertEqual(record["outside"], "Keep boundary value")
        self.assertEqual(record["outside_count"], 2)
        self.assertIsNone(record["chart_error"])
        self.assertIsNotNone(record["chart"])

    def test_automatic_surface_reports_method_used_for_each_geometry(self):
        grid = pd.concat([self.surface, pd.DataFrame(
            {"Easting": [2.0], "Northing": [2.0], "Elevation": [10.0]})],
                         ignore_index=True)
        query = pd.DataFrame({"xi": [0.5], "yi": [0.5]})
        for data, expected in ((grid, "Bilinear · complete grid"),
                               (self.surface, "Linear · scattered points")):
            with self.subTest(method=expected):
                record = main.calculate("2d", data, list(data.columns), query,
                                        "auto", "nan", "surface-id")
                self.assertEqual(record["method"], expected)
                self.assertEqual(record["outside"], "Leave blank")
                self.assertEqual(record["outside_count"], 0)
                self.assertEqual(record["data"]["status"].tolist(), ["Interpolated"])

    def test_chart_errors_preserve_complete_calculated_table_and_status(self):
        cases = [
            ("1d", self.curve, pd.DataFrame({"xi": [0.5, 3.0]}), [15.0, np.nan], "yi"),
            ("2d", self.surface, pd.DataFrame({"xi": [0.5, 1.5], "yi": [0.5, 1.5]}),
             [2.5, np.nan], "zi"),
        ]
        for dimension, data, query, values, output_column in cases:
            for error_class in (ValueError, RuntimeError):
                with self.subTest(dimension=dimension, error=error_class.__name__):
                    with patch.object(main, "make_chart", side_effect=error_class("plot failed")):
                        record = main.calculate(dimension, data, list(data.columns), query,
                                                "linear", "nan", "still-valid")
                    np.testing.assert_allclose(record["data"][output_column], values)
                    self.assertEqual(record["data"]["status"].tolist(),
                                     ["Interpolated", "Outside · left blank"])
                    self.assertEqual(record["outside_count"], 1)
                    self.assertEqual(record["fingerprint"], "still-valid")
                    self.assertIsNone(record["chart"])
                    self.assertIn("table is still available", record["chart_error"])

    def test_blank_1d_results_remain_in_table_and_are_omitted_from_chart_markers(self):
        query = pd.DataFrame({"xi": [-1.0, 0.5, 3.0]})
        record = main.calculate("1d", self.curve, list(self.curve.columns), query,
                                "linear", "nan", "blank-policy")
        self.assertEqual(len(record["data"]), 3)
        self.assertEqual(record["outside_count"], 2)
        traces = {trace.name: trace for trace in record["chart"].data}
        self.assertNotIn("Outside known data", traces)
        np.testing.assert_allclose(traces["Interpolated queries"].x, [0.5])
        np.testing.assert_allclose(traces["Interpolated queries"].y, [15.0])
        np.testing.assert_allclose(traces["Reference samples"].x, self.curve["Position"])
        np.testing.assert_allclose(traces["Reference samples"].y, self.curve["Reading"])

    def test_numeric_outside_results_have_distinct_markers_and_hover_status(self):
        query = pd.DataFrame({"xi": [3.0, 0.5, -1.0, 0.5]})
        record = main.calculate("1d", self.curve, list(self.curve.columns), query,
                                "linear", "linear", "slope-policy")
        traces = {trace.name: trace for trace in record["chart"].data}
        outside = traces["Outside known data"]
        inside = traces["Interpolated queries"]
        np.testing.assert_allclose(outside.x, [3.0, -1.0])
        np.testing.assert_allclose(outside.y, [60.0, 0.0])
        self.assertEqual(outside.marker.symbol, "diamond")
        self.assertEqual(inside.marker.symbol, "circle")
        self.assertNotEqual(outside.marker.color, inside.marker.color)
        np.testing.assert_allclose(np.asarray(outside.customdata[:, 0], dtype=float), [60.0, 0.0])
        self.assertEqual(list(outside.customdata[:, 1]), ["Outside · extended slope"] * 2)
        np.testing.assert_allclose(inside.x, [0.5, 0.5])
        self.assertEqual(record["chart"].layout.xaxis.title.text, "Position")
        self.assertEqual(record["chart"].layout.yaxis.title.text, "Reading")

    def test_surface_chart_masks_hull_and_retains_reference_and_blank_query_payloads(self):
        query = pd.DataFrame({"xi": [0.5, 1.5], "yi": [0.5, 1.5]})
        record = main.calculate("2d", self.surface, list(self.surface.columns), query,
                                "linear", "nan", "triangular-hull")
        figure = record["chart"]
        heatmap = figure.data[0]
        self.assertEqual(heatmap.type, "heatmap")
        np.testing.assert_allclose([heatmap.x[0], heatmap.x[-1]], [0.0, 2.0])
        np.testing.assert_allclose([heatmap.y[0], heatmap.y[-1]], [0.0, 2.0])
        z = np.asarray(heatmap.z, dtype=float)
        self.assertAlmostEqual(z[0, 0], 0.0)
        self.assertAlmostEqual(z[len(heatmap.y) // 2, len(heatmap.x) // 2], 5.0)
        self.assertTrue(np.isnan(z[-1, -1]))
        traces = {trace.name: trace for trace in figure.data}
        np.testing.assert_allclose(traces["Reference samples"].x, self.surface["Easting"])
        np.testing.assert_allclose(traces["Reference samples"].y, self.surface["Northing"])
        np.testing.assert_allclose(traces["Interpolated queries"].x, [0.5])
        self.assertAlmostEqual(float(traces["Interpolated queries"].customdata[0, 0]), 2.5)
        outside = traces["Outside known data"]
        np.testing.assert_allclose(outside.x, [1.5])
        np.testing.assert_allclose(outside.y, [1.5])
        self.assertTrue(np.isnan(float(outside.customdata[0, 0])))
        self.assertEqual(outside.customdata[0, 1], "Outside · left blank")
        self.assertEqual(figure.layout.xaxis.title.text, "Easting")
        self.assertEqual(figure.layout.yaxis.title.text, "Northing")
        self.assertEqual(heatmap.colorbar.title.text, "Elevation")

    def test_nearest_curve_values_change_at_actual_sample_midpoints(self):
        data = pd.DataFrame({"X": [0.0, 2.0, 6.0], "Y": [10.0, 30.0, 60.0]})
        query = pd.DataFrame({"xi": [1.0, 4.0]})
        curve = main.calculate("1d", data, ["X", "Y"], query,
                               "nearest", "nan", "nearest-boundaries")["chart"].data[0]
        x, y = np.asarray(curve.x), np.asarray(curve.y)
        self.assertEqual(curve.line.shape, "hv")
        for midpoint, left_y, right_y in ((1.0, 10.0, 30.0), (4.0, 30.0, 60.0)):
            with self.subTest(midpoint=midpoint):
                self.assertEqual(y[np.flatnonzero(x == midpoint)[0]], left_y)
                self.assertEqual(y[np.flatnonzero(x == np.nextafter(midpoint, np.inf))[0]], right_y)

    def test_surface_distinguishes_display_grid_from_exact_queries_and_known_samples(self):
        query = pd.DataFrame({"xi": [0.123456789, 0.876543211], "yi": [0.234567891, 0.345678912]})
        record = main.calculate("2d", self.surface, list(self.surface.columns), query,
                                "nearest", "nan", "nearest-surface")
        heatmap = record["chart"].data[0]
        self.assertFalse(heatmap.zsmooth)
        self.assertEqual(np.asarray(heatmap.z).shape, (55, 55))
        self.assertIn("55 × 55 display grid", record["chart_note"])
        self.assertIn("exact coordinates", record["chart_note"])
        np.testing.assert_array_equal(record["data"]["xi"], query["xi"])
        np.testing.assert_array_equal(record["data"]["yi"], query["yi"])
        grid_values = np.asarray(heatmap.z, dtype=float)
        self.assertTrue(set(grid_values[np.isfinite(grid_values)]) <= set(self.surface["Elevation"]))
        traces = {trace.name: trace for trace in record["chart"].data}
        self.assertEqual(traces["Reference samples"].marker.symbol, "square")
        self.assertNotEqual(traces["Reference samples"].marker.symbol,
                            traces["Interpolated queries"].marker.symbol)
        np.testing.assert_array_equal(traces["Reference samples"].customdata[:, 0],
                                      self.surface["Elevation"])
        self.assertIn("Elevation", traces["Reference samples"].hovertemplate)

    def test_blank_curve_results_have_an_explicit_chart_explanation(self):
        record = main.calculate("1d", self.curve, list(self.curve.columns),
                                pd.DataFrame({"xi": [-1.0, 0.5]}), "linear", "nan", "blank-note")
        self.assertIn("Blank results remain in the table", record["chart_note"])
        nearest = main.calculate("1d", self.curve, list(self.curve.columns),
                                 pd.DataFrame({"xi": [0.5]}), "nearest", "nan", "nearest-note")
        self.assertIn("nearest-sample steps", nearest["chart_note"])


class UploadIngestionTests(unittest.TestCase):
    """Exercise the real UploadedFile boundary unavailable to AppTest."""

    def make_upload(self, name, content):
        return UploadedFile(UploadedFileRec("file-id", name, "text/csv", content), FileURLs())

    def make_ui(self, state, uploaded):
        return SimpleNamespace(session_state=state, file_uploader=Mock(return_value=uploaded),
                               caption=Mock(), button=Mock(return_value=False))

    def test_real_upload_caches_full_bytes_even_when_file_position_is_at_end(self):
        content = b"X;Y\n1.234,50;2.345,50\n2.234,50;3.345,50"
        upload = self.make_upload("measurements.csv", content)
        upload.read()
        state, options = {}, {"delimiter": ";", "decimal": ",", "thousands": ".", "header": True}
        ui = self.make_ui(state, upload)
        with patch.object(main, "st", ui), patch.object(main, "import_settings", return_value=options):
            table = main.uploaded_table("Reference", "reference", "reference-format")
        self.assertEqual(state["cached_reference"], ("measurements.csv", content))
        self.assertEqual(upload.tell(), len(content))
        np.testing.assert_allclose(numeric_columns(table, ["X", "Y"]),
                                   [[1234.5, 2345.5], [2234.5, 3345.5]])
        self.assertIn("measurements.csv", ui.caption.call_args.args[0])
        self.assertEqual(ui.button.call_args.kwargs["on_click"], main.clear_upload)
        self.assertEqual(ui.button.call_args.kwargs["args"], ("reference",))

    def test_upload_replacement_uses_new_name_and_contents(self):
        state = {"cached_reference": ("old.csv", b"X,Y\n0,1\n1,2")}
        content = b"X,Y\n10,20\n30,40"
        ui = self.make_ui(state, self.make_upload("replacement.csv", content))
        with patch.object(main, "st", ui), patch.object(main, "import_settings", return_value={}):
            table = main.uploaded_table("Reference", "reference", "reference-format")
        self.assertEqual(state["cached_reference"], ("replacement.csv", content))
        np.testing.assert_allclose(numeric_columns(table, ["X", "Y"]), [[10.0, 20.0], [30.0, 40.0]])

    def test_retained_upload_is_reparsed_after_number_format_changes(self):
        state = {"cached_reference": ("locale.csv", b"X;Y\n1,5;2,5")}
        ui = self.make_ui(state, None)
        options = {"delimiter": ";", "decimal": ","}
        with patch.object(main, "st", ui), patch.object(main, "import_settings", return_value=options):
            original = main.uploaded_table("Reference", "reference", "reference-format")
            options["decimal"] = "."
            changed = main.uploaded_table("Reference", "reference", "reference-format")
        np.testing.assert_allclose(numeric_columns(original, ["X", "Y"]), [[1.5, 2.5]])
        self.assertTrue(numeric_columns(changed, ["X", "Y"]).isna().all().all())
        self.assertEqual(state["cached_reference"][1], b"X;Y\n1,5;2,5")

    def test_clear_retires_the_upload_widget_and_leaves_format_controls_available(self):
        state = {"cached_reference": ("old.csv", b"X,Y\n0,1\n1,2")}
        ui = self.make_ui(state, None)
        with patch.object(main, "st", ui), patch.object(main, "import_settings", return_value={}) as settings:
            main.clear_upload("reference")
            self.assertIsNone(main.uploaded_table("Reference", "reference", "reference-format"))
        self.assertNotIn("cached_reference", state)
        self.assertEqual(state["generation_reference"], 1)
        self.assertEqual(ui.file_uploader.call_args.kwargs["key"], "reference_1")
        settings.assert_called_once_with("reference-format")
        ui.caption.assert_not_called()
        ui.button.assert_not_called()


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


class SupportWidgetTests(unittest.TestCase):
    def rendered_link(self, *args, **kwargs):
        with patch.object(coffee_widget.st, "markdown") as markdown:
            coffee_widget.add_buy_me_a_coffee(*args, **kwargs)
        markdown.assert_called_once()
        self.assertTrue(markdown.call_args.kwargs["unsafe_allow_html"])
        parser = LinkParser()
        parser.feed(markdown.call_args.args[0])
        self.assertEqual(len(parser.links), 1)
        return parser.links[0]

    def test_default_support_link_keeps_destination_title_and_new_tab_protection(self):
        link = self.rendered_link()
        self.assertEqual(link["href"], coffee_widget.DEFAULT_COFFEE_URL)
        self.assertEqual(link["title"], "Buy me a coffee")
        self.assertEqual(link["target"], "_blank")
        self.assertIn("noopener", link["rel"].split())

    def test_custom_destination_and_title_are_rendered(self):
        url = "https://example.test/support?currency=EUR&source=app"
        link = self.rendered_link(url, title="Support the project")
        self.assertEqual(link["href"], url)
        self.assertEqual(link["title"], "Support the project")
        self.assertEqual(link["target"], "_blank")
        self.assertIn("noopener", link["rel"].split())

    def test_quotes_and_html_characters_stay_inside_custom_attributes(self):
        url = 'https://example.test/support?message="coffee"&source=<app>'
        title = 'Support "Interpolator" & friends <today>'
        link = self.rendered_link(url, title=title)
        self.assertEqual(link["href"], url)
        self.assertEqual(link["title"], title)
        self.assertEqual(set(link), {"href", "target", "rel", "title"})


if __name__ == "__main__":
    unittest.main()
