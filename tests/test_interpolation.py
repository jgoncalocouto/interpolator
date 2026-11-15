import io
import unittest

import numpy as np
import pandas as pd

from interpolation import (
    build_forward_interpolator,
    interp_linear,
    interp_nearest,
    is_full_grid,
    parse_float_list,
    prepare_reference,
    read_csv_smart,
    read_pasted_table,
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
