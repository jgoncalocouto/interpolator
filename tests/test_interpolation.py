import io
import unittest

import numpy as np
import pandas as pd

from interpolation import (
    build_forward_interpolator,
    interp_linear,
    interp_nearest,
    is_full_grid,
    numeric_columns,
    parse_float_list,
    prepare_reference,
    read_csv_smart,
    read_pasted_table,
    result_csv,
)


class ParsingTests(unittest.TestCase):
    def test_plain_comma_csv_preserves_all_columns_and_rows(self):
        table = read_pasted_table("x,y\n0,0\n1,2\n2,4")
        self.assertEqual(table.columns.tolist(), ["x", "y"])
        self.assertEqual(table.astype(float).values.tolist(), [[0, 0], [1, 2], [2, 4]])

    def test_headerless_csv_and_quoted_headers(self):
        table = read_csv_smart(io.BytesIO(b'0,1\n2,3\n'))
        self.assertEqual(table.columns.tolist(), ["col1", "col2"])
        self.assertEqual(len(table), 2)
        table = read_pasted_table('"X, axis",Y\n0,1\n2,3')
        self.assertEqual(table.columns.tolist(), ["X, axis", "Y"])

    def test_decimal_comma_tables(self):
        for separator in (";", "\t", " "):
            with self.subTest(separator=separator):
                table = read_pasted_table(f"x{separator}y\n1,5{separator}3,5\n2,5{separator}4,5")
                clean, _ = prepare_reference(table, ["x", "y"])
                np.testing.assert_allclose(clean.to_numpy(), [[1.5, 3.5], [2.5, 4.5]])

    def test_csv_spaces_and_duplicate_headers(self):
        table = read_pasted_table("x, x, x.1\n0, 1, 2")
        self.assertEqual(len(set(table.columns)), 3)
        self.assertEqual(table.shape, (1, 3))

    def test_ragged_table_reports_line(self):
        with self.assertRaisesRegex(ValueError, "Row 3"):
            read_pasted_table("x,y\n0,1\n2,3,4")

    def test_empty_tables(self):
        self.assertTrue(read_pasted_table(" \n\t ").empty)
        self.assertTrue(read_csv_smart(io.BytesIO(b'')).empty)

    def test_edge_empty_spreadsheet_cells_are_not_lost(self):
        table = read_pasted_table("x\ty\n\t1\n2\t")
        self.assertEqual(table.shape, (2, 2))
        clean, report = prepare_reference(table, ["x", "y"])
        self.assertTrue(clean.empty)
        self.assertEqual(report["invalid_rows"], 2)

    def test_query_separators_and_decimal_commas(self):
        np.testing.assert_allclose(parse_float_list("1,2,3"), [1, 2, 3])
        np.testing.assert_allclose(parse_float_list("1,2\n3,4"), [1, 2, 3, 4])
        np.testing.assert_allclose(parse_float_list("2,5\n"), [2, 5])
        np.testing.assert_allclose(parse_float_list("1,5\n2,5", decimal_comma=True), [1.5, 2.5])
        np.testing.assert_allclose(parse_float_list("1,5;2,5", decimal_comma=True), [1.5, 2.5])
        np.testing.assert_allclose(parse_float_list("2,5\n", decimal_comma=True), [2.5])
        np.testing.assert_allclose(parse_float_list("1,5 2,5", decimal_comma=True), [1.5, 2.5])
        np.testing.assert_allclose(parse_float_list("1 2\n3 4"), [1, 2, 3, 4])
        self.assertEqual(parse_float_list("").size, 0)

    def test_decimal_comma_mode_rejects_ambiguous_comma_lists(self):
        with self.assertRaisesRegex(ValueError, "decimal-comma mode"):
            parse_float_list("1,2,3", decimal_comma=True)

    def test_invalid_query_values_are_not_silently_lost(self):
        for text in ("1 oops 2", "1,inf,2", "nan", "1e999"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_float_list(text)


class CleaningTests(unittest.TestCase):
    def test_cleaning_counts_and_duplicate_means(self):
        frame = pd.DataFrame({"x": ["2", "1", "1", "bad", "inf"],
                              "y": ["8", "2,5", "3,5", "6", "7"]})
        clean, report = prepare_reference(frame, ["x", "y"])
        np.testing.assert_allclose(clean.values, [[1, 3], [2, 8]])
        self.assertEqual(report, {"input_rows": 5, "invalid_rows": 2, "duplicates_merged": 1})

    def test_column_roles_must_differ(self):
        with self.assertRaisesRegex(ValueError, "different column"):
            prepare_reference(pd.DataFrame({"x": [0, 1]}), ["x", "x"])


class ImportFormatTests(unittest.TestCase):
    def test_explicit_decimal_point_does_not_accept_decimal_comma(self):
        table = read_pasted_table("x;y\n1,5;2.5", delimiter=";", decimal=".")
        converted = numeric_columns(table, ["x", "y"])
        self.assertTrue(np.isnan(converted.loc[0, "x"]))
        self.assertEqual(converted.loc[0, "y"], 2.5)

    def test_explicit_decimal_comma_and_thousands_point(self):
        table = read_pasted_table("x;y\n1.234,56;2.345,67\n2.345,67;3.456,78",
                                  delimiter=";", decimal=",", thousands=".")
        converted = numeric_columns(table, ["x", "y"])
        np.testing.assert_allclose(converted.values, [[1234.56, 2345.67], [2345.67, 3456.78]])
        self.assertEqual(table.attrs["import_format"],
                         {"delimiter": ";", "decimal": ",", "thousands": ".",
                          "header": True, "warnings": []})

    def test_thousands_grouping_is_validated_before_removal(self):
        table = read_pasted_table(
            "x;y\n1,234.56;2\n1,23;3\n12,345,678.9;4\n1234,567;5",
            delimiter=";", decimal=".", thousands=",")
        converted = numeric_columns(table, ["x", "y"])
        np.testing.assert_allclose(converted["x"], [1234.56, np.nan, 12345678.9, np.nan])

    def test_space_and_apostrophe_grouping(self):
        for thousands in (" ", "'"):
            with self.subTest(thousands=thousands):
                table = read_pasted_table(f"x|y\n1{thousands}234,5|2,5",
                                          delimiter="|", decimal=",", thousands=thousands)
                np.testing.assert_allclose(numeric_columns(table, ["x", "y"]), [[1234.5, 2.5]])

    def test_scientific_notation_with_decimal_comma(self):
        table = read_pasted_table("x;y\n-1,5e+3;+2,5E-2", delimiter=";", decimal=",")
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]), [[-1500, .025]])

    def test_auto_never_removes_thousands_grouping(self):
        table = read_pasted_table("x;y\n1,234;2,345\n3,456;4,567")
        settings = table.attrs["import_format"]
        self.assertEqual(settings["decimal"], ",")
        self.assertIsNone(settings["thousands"])
        self.assertTrue(any("could use" in warning for warning in settings["warnings"]))
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]),
                                   [[1.234, 2.345], [3.456, 4.567]])

    def test_auto_mixed_decimal_marks_reports_choice_and_invalid_cells(self):
        table = read_pasted_table("x;y\n1.5;2,5\n3.5;4,5")
        settings = table.attrs["import_format"]
        self.assertEqual(settings["decimal"], ".")  # deterministic tie break
        self.assertTrue(any("Mixed decimal marks" in warning for warning in settings["warnings"]))
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]), [[1.5, np.nan], [3.5, np.nan]])

    def test_both_punctuation_marks_require_explicit_grouping(self):
        table = read_pasted_table("x;y\n1.234,56;2.345,67", delimiter=";")
        self.assertTrue(any("Thousands grouping is never inferred" in warning
                            for warning in table.attrs["import_format"]["warnings"]))
        self.assertTrue(numeric_columns(table, ["x", "y"]).isna().all().all())

    def test_delimiter_detection_respects_quoted_separator_characters(self):
        for quoted in ("Flow; inlet", "Flow\tinlet", "Flow|inlet"):
            with self.subTest(quoted=quoted):
                table = read_pasted_table(f'"{quoted}",Pressure\n1.5,2.5\n3.5,4.5')
                self.assertEqual(table.attrs["import_format"]["delimiter"], ",")
                self.assertEqual(table.columns.tolist(), [quoted, "Pressure"])

    def test_csv_quoted_comma_decimals_are_valid(self):
        table = read_pasted_table('x,y\n"1,5","2,5"', delimiter=",", decimal=",")
        np.testing.assert_allclose(numeric_columns(table, ["x", "y"]), [[1.5, 2.5]])

    def test_manual_header_options_and_grouped_headerless_numbers(self):
        table = read_pasted_table("10,20\n30,40", header=True)
        self.assertEqual(table.columns.tolist(), ["10", "20"])
        self.assertEqual(len(table), 1)
        table = read_pasted_table("x,y\n1,2", header=False)
        self.assertEqual(table.columns.tolist(), ["col1", "col2"])
        self.assertEqual(len(table), 2)
        table = read_pasted_table("1.234,56;2.345,67\n2.345,67;3.456,78",
                                  delimiter=";", decimal=",", thousands=".")
        self.assertFalse(table.attrs["import_format"]["header"])
        self.assertEqual(len(table), 2)

    def test_explicit_headers_do_not_influence_decimal_inference(self):
        table = read_pasted_table("1.5;2.5\n1,5;2,5", delimiter=";", header=True)
        self.assertEqual(table.attrs["import_format"]["decimal"], ",")
        np.testing.assert_allclose(numeric_columns(table, table.columns), [[1.5, 2.5]])

    def test_unparseable_numeric_punctuation_does_not_erase_first_data_row(self):
        table = read_pasted_table("1.234,50;2.345,60\n2.234,50;3.345,60", delimiter=";")
        self.assertEqual(table.columns.tolist(), ["col1", "col2"])
        self.assertEqual(len(table), 2)
        self.assertFalse(table.attrs["import_format"]["header"])
        self.assertTrue(numeric_columns(table, table.columns).isna().all().all())
        self.assertTrue(table.attrs["import_format"]["warnings"])

    def test_blank_lines_do_not_change_delimiter_detection(self):
        table = read_pasted_table(" \nx,y\n0,1\n \n2,3\n ")
        self.assertEqual(table.attrs["import_format"]["delimiter"], ",")
        self.assertEqual(table.shape, (2, 2))

    def test_conversion_preserves_row_index_order_and_source_strings(self):
        table = read_pasted_table("x;y\n3,5;bad\n1,5;2,5", delimiter=";", decimal=",")
        table.index = [7, 2]
        converted = numeric_columns(table, ["y", "x"])
        self.assertEqual(converted.index.tolist(), [7, 2])
        self.assertEqual(converted.columns.tolist(), ["y", "x"])
        self.assertEqual(table.loc[7, "x"], "3,5")
        np.testing.assert_allclose(converted.values, [[np.nan, 3.5], [2.5, 1.5]])

    def test_invalid_options_fail_before_conversion(self):
        for settings in ({"decimal": ",", "thousands": ","},
                         {"delimiter": "unknown"}, {"decimal": "unknown"},
                         {"thousands": "/"}, {"header": "yes"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                read_pasted_table("x;y\n1;2", **settings)

    def test_precleaned_locale_numeric_values_are_not_reinterpreted(self):
        table = read_pasted_table("x;y\n1,5;2,5\n2,5;3,5", delimiter=";", decimal=",", thousands=".")
        clean, _ = prepare_reference(table, ["x", "y"])
        converted = numeric_columns(clean, ["x", "y"])
        np.testing.assert_allclose(converted, [[1.5, 2.5], [2.5, 3.5]])
        twice, report = prepare_reference(clean, ["x", "y"])
        np.testing.assert_allclose(twice, clean)
        self.assertEqual(report["invalid_rows"], 0)

    def test_2d_interpolation_on_precleaned_locale_data(self):
        table = read_pasted_table(
            "x;y;z\n0,0;0,0;0,0\n0,0;1,5;3,0\n1,5;0,0;1,5\n1,5;1,5;4,5",
            delimiter=";", decimal=",", thousands=".")
        clean, _ = prepare_reference(table, ["x", "y", "z"])
        function, _ = build_forward_interpolator(clean, "x", "y", "z")
        np.testing.assert_allclose(function([.75], [.75]), [2.25])


class ExportFormatTests(unittest.TestCase):
    def test_csv_formats_roundtrip_with_matching_import_settings(self):
        original = pd.DataFrame({"X, position": [1.25, -2.5], "résultat": [3.75, 4.5]})
        for delimiter, decimal in ((",", "."), (";", ","), ("\t", "."), (",", ",")):
            with self.subTest(delimiter=delimiter, decimal=decimal):
                exported = result_csv(original, delimiter=delimiter, decimal=decimal)
                self.assertTrue(exported.startswith(b"\xef\xbb\xbf"))
                table = read_csv_smart(io.BytesIO(exported), delimiter=delimiter, decimal=decimal)
                self.assertEqual(table.columns.tolist(), original.columns.tolist())
                np.testing.assert_allclose(numeric_columns(table, table.columns), original)

    def test_same_comma_decimal_and_delimiter_are_quoted(self):
        exported = result_csv(pd.DataFrame({"x": [1.25], "y": [2.5]}), decimal=",")
        self.assertIn('"1,25","2,5"', exported.decode("utf-8-sig"))

    def test_invalid_export_options(self):
        for settings in ({"delimiter": "auto"}, {"decimal": "auto"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                result_csv(pd.DataFrame({"x": [1]}), **settings)


class CurveTests(unittest.TestCase):
    def test_linear_and_outside_behaviors(self):
        x, y, query = np.array([0, 1, 2]), np.array([0, 2, 6]), np.array([-1, .5, 3])
        np.testing.assert_allclose(interp_linear(x, y, query, "clamp"), [0, 1, 6])
        np.testing.assert_allclose(interp_linear(x, y, query, "linear"), [-2, 1, 10])
        np.testing.assert_allclose(interp_linear(x, y, query, "nan"), [np.nan, 1, np.nan])

    def test_nearest_tie_and_missing_outside(self):
        np.testing.assert_allclose(interp_nearest([0, 2], [1, 3], [-1, 1, 3]), [1, 1, 3])
        np.testing.assert_allclose(interp_nearest([0, 2], [1, 3], [-1, 1, 3], "nan"),
                                   [np.nan, 1, np.nan])

    def test_bad_curve_and_queries_have_friendly_errors(self):
        for x, y in (([1], [2]), ([1, 1], [2, 3]), ([1, 0], [2, 3])):
            with self.assertRaises(ValueError):
                interp_linear(x, y, [1])
        with self.assertRaises(ValueError):
            interp_linear([0, 1], [0, 1], [np.nan])


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.grid = pd.DataFrame({"x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [0, 2, 1, 3]})
        self.scattered = self.grid.iloc[[0, 1, 2]].copy()

    def test_regular_grid_auto_and_outside_nearest(self):
        function, metadata = build_forward_interpolator(self.grid, "x", "y", "z", extrap="nearest")
        self.assertEqual(metadata["type"], "regular")
        np.testing.assert_allclose(function([.5, 2], [.5, 1]), [1.5, 3])
        np.testing.assert_array_equal(metadata["inside_domain"]([.5, 2], [.5, 1]), [True, False])

    def test_every_surface_method_honors_missing_outside(self):
        for method in ("auto", "regular", "linear", "nearest", "rbf"):
            with self.subTest(method=method):
                function, _ = build_forward_interpolator(self.grid, "x", "y", "z", method=method)
                self.assertTrue(np.isnan(function([2], [1])[0]))
                self.assertTrue(np.isfinite(function([.5], [.5])[0]))

    def test_every_surface_method_honors_nearest_outside(self):
        for method in ("auto", "regular", "linear", "nearest", "rbf"):
            with self.subTest(method=method):
                function, _ = build_forward_interpolator(self.grid, "x", "y", "z", method=method,
                                                         extrap="nearest")
                np.testing.assert_allclose(function([2], [1]), [3])

    def test_scattered_domain_uses_hull_not_bounding_rectangle(self):
        function, metadata = build_forward_interpolator(self.scattered, "x", "y", "z")
        self.assertEqual(metadata["type"], "linear")
        np.testing.assert_allclose(function([.25, .8], [.25, .8]), [.75, np.nan])

    def test_invalid_grid_and_collinear_points(self):
        with self.assertRaisesRegex(ValueError, "every X/Y combination"):
            build_forward_interpolator(self.scattered, "x", "y", "z", method="regular")
        line = pd.DataFrame({"x": [0, 1, 2], "y": [0, 1, 2], "z": [0, 1, 2]})
        with self.assertRaisesRegex(ValueError, "line"):
            build_forward_interpolator(line, "x", "y", "z")

    def test_grid_detection_rejects_missing_and_duplicate_pairs(self):
        self.assertTrue(is_full_grid([0, 0, 1, 1], [0, 1, 0, 1]))
        self.assertFalse(is_full_grid([0, 0, 1, 1], [0, 0, 0, 1]))

    def test_query_shapes_and_empty_queries(self):
        function, _ = build_forward_interpolator(self.grid, "x", "y", "z")
        self.assertEqual(function([], []).shape, (0,))
        self.assertEqual(function([[.1, .2]], [[.3, .4]]).shape, (1, 2))
        with self.assertRaisesRegex(ValueError, "same shape"):
            function([0, 1], [0])


if __name__ == "__main__":
    unittest.main()
