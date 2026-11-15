"""Feature contracts that complement the focused interpolation regressions."""

import csv
import io
import tempfile
import unittest

import numpy as np
import pandas as pd

from interpolation import (
    build_forward_interpolator,
    interp_linear,
    interp_nearest,
    numeric_columns,
    parse_float_list,
    prepare_reference,
    read_csv_smart,
    read_pasted_table,
    result_csv,
)


def write_table(rows, delimiter):
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return stream.getvalue()


class UploadedFileFeatures(unittest.TestCase):
    def test_utf8_bom_and_windows1252_keep_header_characters(self):
        examples = (
            ("位置;résultat\n1,5;2,5", "utf-8-sig", ["位置", "résultat"]),
            ("Température;Valeur €\n1,5;2,5", "cp1252", ["Température", "Valeur €"]),
        )
        for source, encoding, headers in examples:
            with self.subTest(encoding=encoding):
                table = read_csv_smart(io.BytesIO(source.encode(encoding)),
                                       delimiter=";", decimal=",")
                self.assertEqual(table.columns.tolist(), headers)
                np.testing.assert_allclose(numeric_columns(table, headers), [[1.5, 2.5]])

    def test_seekable_text_file_is_read_from_start_on_every_import(self):
        # A real text file exercises the public file-like contract without a
        # getvalue method, including a cursor left at the end after upload.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="") as uploaded:
            uploaded.write("x,y\n1.25,2.5\n3.75,4.5")
            for _ in range(2):
                table = read_csv_smart(uploaded, delimiter=",", decimal=".")
                np.testing.assert_allclose(numeric_columns(table, ["x", "y"]),
                                           [[1.25, 2.5], [3.75, 4.5]])

    def test_multiline_quoted_headers_and_quotes_survive_csv_import(self):
        headers = ["Reading\nposition", 'Result "quoted"; valeur']
        source = write_table([headers, ["1.25", "2.5"]], ",")
        table = read_csv_smart(io.BytesIO(source.encode("utf-8")),
                               delimiter=",", decimal=".", header=True)
        self.assertEqual(table.columns.tolist(), headers)
        np.testing.assert_allclose(numeric_columns(table, headers), [[1.25, 2.5]])

    def test_unfinished_csv_quotes_give_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "quotes.*CSV formatting"):
            read_csv_smart(io.BytesIO(b'x,y\n"1,2'), delimiter=",")


class ExplicitTableFormatFeatures(unittest.TestCase):
    def test_each_column_separator_accepts_both_decimal_formats(self):
        # This is the user-facing format contract: commas can be decimal
        # marks even in comma CSV when the numeric fields are properly quoted.
        headers = ['Travel "distance"', "Reference output"]
        for delimiter in (",", ";", "\t", "|", "whitespace"):
            for decimal, row in ((".", ["1.25", "-2.5e-2"]),
                                 (",", ["1,25", "-2,5e-2"])):
                with self.subTest(delimiter=delimiter, decimal=decimal):
                    source = write_table([headers, row],
                                         " " if delimiter == "whitespace" else delimiter)
                    table = read_pasted_table(source, delimiter=delimiter,
                                              decimal=decimal, header=True)
                    self.assertEqual(table.columns.tolist(), headers)
                    self.assertEqual(table.iloc[0].tolist(), row)
                    self.assertEqual(table.attrs["import_format"]["delimiter"], delimiter)
                    self.assertEqual(table.attrs["import_format"]["decimal"], decimal)
                    np.testing.assert_allclose(numeric_columns(table, headers), [[1.25, -.025]])

    def test_quoted_space_grouping_with_whitespace_columns(self):
        source = '"Travel distance" "Output value"\n"1 234,5" "-2 345,5"'
        table = read_pasted_table(source, delimiter="whitespace", decimal=",", thousands=" ")
        np.testing.assert_allclose(numeric_columns(table, table.columns), [[1234.5, -2345.5]])

    def test_auto_detected_pipe_format_is_reported_and_converted(self):
        table = read_pasted_table("x|y\n1,25|-2,5\n2,25|3,5")
        settings = table.attrs["import_format"]
        self.assertEqual((settings["delimiter"], settings["decimal"], settings["header"]),
                         ("|", ",", True))
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]),
                                   [[1.25, -2.5], [2.25, 3.5]])

    def test_auto_decimal_with_explicit_grouping_uses_remaining_decimal_mark(self):
        table = read_pasted_table("x;y\n1,234.5;2,345.5", delimiter=";", thousands=",")
        self.assertEqual(table.attrs["import_format"]["decimal"], ".")
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]), [[1234.5, 2345.5]])


class ReferenceCleaningFeatures(unittest.TestCase):
    def test_empty_and_all_invalid_2d_reference_keep_schema_and_counts(self):
        empty = pd.DataFrame(columns=["x", "y", "z"])
        invalid = pd.DataFrame({"x": ["bad", "inf", "0"],
                                "y": ["1", "1", "nan"],
                                "z": ["2", "3", "4"]})
        for frame in (empty, invalid):
            with self.subTest(input_rows=len(frame)):
                clean, report = prepare_reference(frame, ["x", "y", "z"])
                self.assertTrue(clean.empty)
                self.assertEqual(clean.columns.tolist(), ["x", "y", "z"])
                self.assertEqual(report, {"input_rows": len(frame),
                                          "invalid_rows": len(frame), "duplicates_merged": 0})

    def test_2d_duplicate_coordinate_means_do_not_merge_distinct_pairs(self):
        frame = pd.DataFrame({"x": [1, 0, 0, 1, 0, None, 0],
                              "y": [0, 1, 0, 0, 1, 0, 0],
                              "z": [4, 3, 1, 8, 5, 9, np.inf]})
        clean, report = prepare_reference(frame, ["x", "y", "z"])
        np.testing.assert_allclose(clean.values, [[0, 0, 1], [0, 1, 4], [1, 0, 6]])
        self.assertEqual(report, {"input_rows": 7, "invalid_rows": 2, "duplicates_merged": 2})

    def test_changed_or_missing_column_selection_has_recovery_message(self):
        frame = pd.DataFrame({"x": [0, 1], "y": [2, 3]})
        with self.assertRaisesRegex(ValueError, "Select the columns again"):
            prepare_reference(frame, ["x", "old column"])


class OneDimensionalFeatureContracts(unittest.TestCase):
    def setUp(self):
        self.x = [-2, 0, 3]
        self.y = [5, 1, 7]

    def test_scalar_query_returns_scalar_shaped_result(self):
        for method, expected in ((interp_linear, 4), (interp_nearest, 1)):
            with self.subTest(method=method.__name__):
                output = method(self.x, self.y, np.asarray(1.5))
                self.assertEqual(np.shape(output), ())
                self.assertEqual(float(output), expected)

    def test_query_matrix_keeps_shape_order_and_duplicates(self):
        queries = np.array([[-2, 0, 3], [1.5, 3, -2]])
        examples = ((interp_linear, [[5, 1, 7], [4, 7, 5]]),
                    (interp_nearest, [[5, 1, 7], [1, 7, 5]]))
        for method, expected in examples:
            with self.subTest(method=method.__name__):
                output = method(self.x, self.y, queries)
                self.assertEqual(output.shape, queries.shape)
                np.testing.assert_allclose(output, expected)

    def test_empty_query_arrays_are_valid_and_keep_their_shape(self):
        for method in (interp_linear, interp_nearest):
            for queries in (np.array([]), np.empty((2, 0))):
                with self.subTest(method=method.__name__, shape=queries.shape):
                    self.assertEqual(method(self.x, self.y, queries).shape, queries.shape)

    def test_data_endpoints_are_inside_for_every_outside_policy(self):
        for method in (interp_linear, interp_nearest):
            for policy in ("clamp", "linear", "nan"):
                with self.subTest(method=method.__name__, outside=policy):
                    np.testing.assert_allclose(method(self.x, self.y, [-2, 3], policy), [5, 7])

    def test_query_lists_accept_signed_exponents_without_reordering(self):
        np.testing.assert_allclose(parse_float_list("+1e3 ; -2.5E-2\t1000\n0"),
                                   [1000, -.025, 1000, 0])
        np.testing.assert_allclose(parse_float_list("+1,5e2 ; -2,5E-2", decimal_comma=True),
                                   [150, -.025])


class TwoDimensionalFeatureContracts(unittest.TestCase):
    @staticmethod
    def plane(x, y):
        return 2 * np.asarray(x) - 3 * np.asarray(y) + 7

    def grid(self):
        x, y = np.meshgrid([-2, 0, 4], [-1, 3])
        return pd.DataFrame({"x": x.ravel(), "y": y.ravel(),
                             "z": self.plane(x, y).ravel()}).iloc[[4, 0, 5, 2, 1, 3]]

    def scattered(self):
        x, y = np.array([0, 4, 0, 1]), np.array([0, 0, 3, 1])
        return pd.DataFrame({"x": x, "y": y, "z": self.plane(x, y)})

    def test_continuous_grid_methods_reproduce_plane_at_nodes_interior_and_edges(self):
        data = self.grid()
        xq, yq = np.array([[-2, 4], [1, -2]]), np.array([[-1, 3], [1, 3]])
        for method in ("auto", "regular", "linear", "rbf"):
            with self.subTest(method=method):
                function, metadata = build_forward_interpolator(data, "x", "y", "z", method=method)
                np.testing.assert_allclose(function(data["x"], data["y"]), data["z"], atol=1e-10)
                output = function(xq, yq)
                self.assertEqual(output.shape, (2, 2))
                np.testing.assert_allclose(output, self.plane(xq, yq), atol=1e-10)
                self.assertTrue(metadata["inside_domain"](xq, yq).all())

    def test_regular_grid_uses_bilinear_interior_values_for_non_affine_surface(self):
        data = pd.DataFrame({"x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [0, 0, 0, 1]})
        # z = x*y is bilinear. Triangulating this square gives different
        # interior values, so an affine-plane check alone cannot detect it.
        for method in ("auto", "regular"):
            with self.subTest(method=method):
                function, metadata = build_forward_interpolator(data, "x", "y", "z", method=method)
                self.assertEqual(metadata["type"], "regular")
                np.testing.assert_allclose(function([.25, .5], [.75, .5]), [.1875, .25])

    def test_smooth_rbf_recovers_nonlinear_sample_values_exactly(self):
        x, y = np.meshgrid([0, .25, 1], [0, .75, 2])
        z = x ** 2 + y ** 2 + x * y
        data = pd.DataFrame({"x": x.ravel(), "y": y.ravel(), "z": z.ravel()})
        function, metadata = build_forward_interpolator(data, "x", "y", "z", method="rbf")
        self.assertEqual(metadata["type"], "rbf")
        np.testing.assert_allclose(function(x, y), z, atol=1e-10)

    def test_scattered_methods_include_hull_edges_and_reproduce_a_plane(self):
        data = self.scattered()
        # (2, 1.5) lies on the sloping edge of this triangular hull.
        xq, yq = np.array([.5, 2, 0]), np.array([.5, 1.5, 3])
        for method in ("auto", "linear", "rbf"):
            with self.subTest(method=method):
                function, metadata = build_forward_interpolator(data, "x", "y", "z", method=method)
                np.testing.assert_allclose(function(xq, yq), self.plane(xq, yq), atol=1e-10)
                np.testing.assert_array_equal(metadata["inside_domain"](xq, yq), [True, True, True])
                self.assertFalse(metadata["inside_domain"]([2], [1.501])[0])
                self.assertTrue(np.isnan(function([2], [1.501])[0]))

    def test_nearest_uses_sample_values_at_nodes_and_nearby_points(self):
        data = self.scattered()
        function, _ = build_forward_interpolator(data, "x", "y", "z", method="nearest")
        np.testing.assert_allclose(function(data["x"], data["y"]), data["z"])
        np.testing.assert_allclose(function([.1, 3.9, .05], [.1, .05, 2.8]),
                                   data.loc[[0, 1, 2], "z"])

    def test_surface_scalar_and_empty_matrix_queries_preserve_shape(self):
        function, metadata = build_forward_interpolator(self.grid(), "x", "y", "z")
        output = function(np.asarray(1.0), np.asarray(1.0))
        self.assertEqual(output.shape, ())
        self.assertEqual(float(output), 6)
        self.assertEqual(metadata["inside_domain"](1.0, 1.0).shape, ())
        self.assertEqual(function(np.empty((2, 0)), np.empty((2, 0))).shape, (2, 0))

    def test_grid_and_smooth_methods_handle_axes_with_very_different_units(self):
        x, y = np.meshgrid([1e6, 2e6], [.001, .004])
        z = 2 * (x - 1e6) / 1e6 - 3 * (y - .001) / .003 + 7
        data = pd.DataFrame({"x": x.ravel(), "y": y.ravel(), "z": z.ravel()})
        for method in ("auto", "regular", "rbf"):
            with self.subTest(method=method):
                function, _ = build_forward_interpolator(data, "x", "y", "z", method=method)
                np.testing.assert_allclose(function([1.25e6], [.00325]), [5.25], atol=1e-10)

    def test_invalid_geometry_has_user_recovery_messages(self):
        examples = (
            (pd.DataFrame({"x": [0, 1], "y": [0, 1], "z": [1, 2]}), "at least three"),
            (pd.DataFrame({"x": [1, 1, 1], "y": [0, 1, 2], "z": [1, 2, 3]}), "vary in both"),
            (pd.DataFrame({"x": [0, 1, 2], "y": [1, 1, 1], "z": [1, 2, 3]}), "vary in both"),
        )
        for data, message in examples:
            with self.subTest(message=message, points=data.to_dict("list")):
                with self.assertRaisesRegex(ValueError, message):
                    build_forward_interpolator(data, "x", "y", "z")

    def test_surface_queries_reject_nonfinite_coordinates(self):
        function, metadata = build_forward_interpolator(self.grid(), "x", "y", "z")
        for evaluate in (function, metadata["inside_domain"]):
            with self.subTest(evaluate=evaluate.__name__):
                with self.assertRaisesRegex(ValueError, "finite numbers"):
                    evaluate([np.inf], [0])


class DownloadFeatureContracts(unittest.TestCase):
    def test_all_eight_download_formats_preserve_results_and_text(self):
        results = pd.DataFrame({
            "xi": [2.5, -1.25, 2.5],
            "yi": [np.pi, np.nan, 1e-12],
            "status": ["Interpolated", "Outside \u00b7 left blank", "Interpolated"],
            'résultat "notes"': ["comma, and semicolon;", 'tab\tpipe|quote"', "ligne\nsuivante"],
        })
        for delimiter in (",", ";", "\t", "|"):
            for decimal in (".", ","):
                with self.subTest(delimiter=delimiter, decimal=decimal):
                    content = result_csv(results, delimiter=delimiter, decimal=decimal)
                    self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
                    restored = read_csv_smart(io.BytesIO(content), delimiter=delimiter,
                                              decimal=decimal, header=True)
                    self.assertEqual(restored.columns.tolist(), results.columns.tolist())
                    np.testing.assert_allclose(numeric_columns(restored, ["xi", "yi"]),
                                               results[["xi", "yi"]], rtol=0, atol=0,
                                               equal_nan=True)
                    self.assertEqual(restored["status"].tolist(), results["status"].tolist())
                    self.assertEqual(restored['résultat "notes"'].tolist(),
                                     results['résultat "notes"'].tolist())
                    self.assertEqual(restored.loc[1, "yi"], "")


if __name__ == "__main__":
    unittest.main()
