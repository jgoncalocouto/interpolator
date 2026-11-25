"""Evaluate emitted formulas against an independent Excel-expression subset.

This is a deterministic formula contract check, not native Excel execution.
The evaluator intentionally models blank reference cells separately from empty
text and the value coercion which can occur when MAP/TOCOL read a reference.
"""

from dataclasses import dataclass
import re
import unittest

import numpy as np

from excel_formulas import build_linear_formula, parse_vector_reference


class ExcelError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<reference>(?:(?:'(?:[^']|'')+'|[\w.]+)!)?"
    r"\$?[A-Za-z]{1,3}\$?[1-9]\d*(?::\$?[A-Za-z]{1,3}\$?[1-9]\d*)?)"
    r'|(?P<string>"(?:[^"]|"")*")'
    r"|(?P<number>\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z_0-9.]*)"
    r"|(?P<symbol><>|<=|>=|[(),;+=*/^<>-]))"
)


class FormulaParser:
    """Parse the generated text, independently of the generator's structure."""

    def __init__(self, formula):
        text = formula.removeprefix("=")
        self.tokens = []
        position = 0
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None:
                raise AssertionError(f"Unexpected formula syntax at {text[position:position + 35]!r}")
            self.tokens.append((match.lastgroup, match.group(match.lastgroup)))
            position = match.end()
        self.index = 0

    def peek(self):
        return self.tokens[self.index][1] if self.index < len(self.tokens) else None

    def take(self):
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expect(self, symbol):
        actual = self.take()[1]
        if actual != symbol:
            raise AssertionError(f"Expected {symbol!r}, found {actual!r}")

    def parse(self):
        result = self.expression()
        if self.peek() is not None:
            raise AssertionError("Unconsumed formula tokens")
        return result

    def expression(self, minimum=0):
        kind, value = self.take()
        if value in ("+", "-"):
            left = ("unary", value, self.expression(4))
        elif value == "(":
            left = self.expression()
            self.expect(")")
        elif kind == "reference":
            left = ("reference", value)
        elif kind == "number":
            left = ("literal", float(value))
        elif kind == "string":
            left = ("literal", value[1:-1].replace('""', '"'))
        elif kind == "name":
            if self.peek() == "(":
                self.take()
                args = []
                if self.peek() != ")":
                    while True:
                        args.append(self.expression())
                        if self.peek() not in (",", ";"):
                            break
                        self.take()
                self.expect(")")
                left = ("call", value.upper(), args)
            else:
                left = ("name", value.upper())
        else:
            raise AssertionError(f"Unexpected token: {(kind, value)!r}")
        precedence = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
                      "+": 2, "-": 2, "*": 3, "/": 3, "^": 4}
        while self.peek() in precedence and precedence[self.peek()] >= minimum:
            operator = self.take()[1]
            right = self.expression(precedence[operator] + 1)
            left = ("binary", operator, left, right)
        return left


def _number(value):
    return isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_))


def _grid(value):
    result = np.asarray(value, dtype=object)
    return result.reshape(1, 1) if result.ndim == 0 else result


def _reference_key(reference):
    if "!" in reference:
        sheet, cells = reference.rsplit("!", 1)
        sheet = sheet.strip("'").replace("''", "'").casefold()
    else:
        sheet, cells = "", reference
    return sheet, cells.replace("$", "").upper()


@dataclass
class Closure:
    names: list
    body: tuple
    environment: dict


class FormulaEvaluator:
    """Small Excel semantics oracle sufficient to exercise this generated formula."""

    def __init__(self, references):
        self.references = {_reference_key(key): _grid(value)
                           for key, value in references.items()}

    def evaluate(self, formula):
        try:
            return self.node(FormulaParser(formula).parse(), {})
        except ExcelError as error:
            return error

    def node(self, expression, environment):
        kind = expression[0]
        if kind == "literal":
            return expression[1]
        if kind == "reference":
            return self.references[_reference_key(expression[1])].copy()
        if kind == "name":
            return environment[expression[1]]
        if kind == "unary":
            value = self.node(expression[2], environment)
            return value if expression[1] == "+" else -value
        if kind == "binary":
            left, right = (self.node(item, environment) for item in expression[2:])
            if isinstance(left, ExcelError):
                raise left
            if isinstance(right, ExcelError):
                raise right
            operator = expression[1]
            operations = {
                "+": lambda: left + right, "-": lambda: left - right,
                "*": lambda: left * right, "/": lambda: left / right,
                "^": lambda: left ** right, "=": lambda: left == right,
                "<>": lambda: left != right, "<": lambda: left < right,
                ">": lambda: left > right, "<=": lambda: left <= right,
                ">=": lambda: left >= right,
            }
            return operations[operator]()
        _, function, arguments = expression
        if function == "LET":
            local = environment.copy()
            for index in range(0, len(arguments) - 1, 2):
                self.assert_name(arguments[index])
                local[arguments[index][1]] = self.node(arguments[index + 1], local)
            return self.node(arguments[-1], local)
        if function == "LAMBDA":
            for argument in arguments[:-1]:
                self.assert_name(argument)
            return Closure([item[1] for item in arguments[:-1]], arguments[-1], environment.copy())
        if function == "IF":
            condition = self.node(arguments[0], environment)
            if isinstance(condition, ExcelError):
                raise condition
            return self.node(arguments[1] if condition else arguments[2], environment)
        if function in ("IFNA", "IFERROR"):
            try:
                value = self.node(arguments[0], environment)
                if isinstance(value, ExcelError):
                    raise value
                return value
            except ExcelError as error:
                if function == "IFNA" and error.code != "#N/A":
                    raise
                return self.node(arguments[1], environment)
        values = [self.node(argument, environment) for argument in arguments]
        if function == "NA":
            raise ExcelError("#N/A")
        if function in ("ISNUMBER", "ISBLANK"):
            predicate = _number if function == "ISNUMBER" else lambda value: value is None
            if isinstance(values[0], np.ndarray):
                return np.vectorize(predicate, otypes=[object])(values[0])
            return predicate(values[0])
        if function == "ROWS":
            return _grid(values[0]).shape[0]
        if function == "COLUMNS":
            return _grid(values[0]).shape[1]
        if function == "COUNT":
            return sum(_number(item) for value in values for item in _grid(value).flat)
        if function == "AND":
            return all(bool(item) for value in values for item in _grid(value).flat)
        if function == "OR":
            return any(bool(item) for value in values for item in _grid(value).flat)
        if function == "NOT":
            return not values[0]
        if function == "MIN":
            return min(item for value in values for item in _grid(value).flat)
        if function == "MAX":
            return max(item for value in values for item in _grid(value).flat)
        if function == "TOCOL":
            return np.asarray([0 if item is None else item for item in values[0].flat],
                              dtype=object).reshape(-1, 1)
        if function == "SORT":
            return np.asarray(sorted(values[0].flat), dtype=object).reshape(-1, 1)
        if function == "SORTBY":
            ordered = sorted(zip(values[1].flat, values[0].flat), key=lambda pair: pair[0])
            return np.asarray([item[1] for item in ordered], dtype=object).reshape(-1, 1)
        if function == "UNIQUE":
            unique = list(dict.fromkeys(values[0].flat))
            return np.asarray(unique, dtype=object).reshape(-1, 1)
        if function == "INDEX":
            row = int(values[1]) - 1
            column = int(values[2]) - 1 if len(values) > 2 else 0
            value = _grid(values[0])[row, column]
            return 0 if value is None else value
        if function == "XMATCH":
            point, items = values[0], list(values[1].flat)
            mode = int(values[2]) if len(values) > 2 else 0
            if point in items:
                return items.index(point) + 1
            if mode == -1:
                smaller = [item for item in items if item < point]
                if smaller:
                    return items.index(max(smaller)) + 1
            raise ExcelError("#N/A")
        if function == "MAP":
            arrays, closure = values[:-1], values[-1]
            shapes = {array.shape for array in arrays}
            if len(shapes) != 1 or len(arrays) != len(closure.names):
                raise AssertionError("MAP array or LAMBDA arity mismatch")
            result = np.empty(arrays[0].shape, dtype=object)
            for index in np.ndindex(result.shape):
                local = closure.environment.copy()
                # A referenced blank can be passed to MAP as zero. The generated
                # formula must retain its separate ISBLANK/ISNUMBER masks.
                local.update({name: (0 if array[index] is None else array[index])
                              for name, array in zip(closure.names, arrays)})
                try:
                    result[index] = self.node(closure.body, local)
                except ExcelError as error:
                    result[index] = error
            return result
        raise AssertionError(f"Unimplemented Excel function in emitted formula: {function}")

    @staticmethod
    def assert_name(expression):
        if expression[0] != "name":
            raise AssertionError(f"Invalid LET/LAMBDA variable: {expression}")


class GeneratedLinearFormulaTests(unittest.TestCase):
    def calculate(self, x, y, queries, *, outside="nan", separator=",", horizontal=False,
                  x_reference="$A$2:$A$7", y_reference="$B$2:$B$7",
                  query_reference="D2:D11"):
        formula = build_linear_formula(x_reference, y_reference, query_reference,
                                       separator=separator, outside=outside)
        query_values = [queries] if horizontal else [[value] for value in queries]
        values = {x_reference: x, y_reference: y, query_reference: query_values}
        return FormulaEvaluator(values).evaluate(formula)

    def assert_cells(self, actual, expected):
        self.assertIsInstance(actual, np.ndarray, actual)
        self.assertEqual(actual.size, len(expected))
        for index, (result, value) in enumerate(zip(actual.flat, expected)):
            with self.subTest(cell=index):
                if value == "#N/A":
                    self.assertIsInstance(result, ExcelError)
                    self.assertEqual(result.code, value)
                elif value == "":
                    self.assertEqual(result, "")
                else:
                    self.assertAlmostEqual(result, value, places=12)

    def test_unsorted_pairs_exact_samples_endpoints_duplicates_and_outside_policies(self):
        x = [[6], [0], [10], [4], [2], [8]]
        y = [[35], [18], [42], [28], [22], [39]]
        queries = [0, 1, 2, 3, 4, 7, 10, 12, -2, 3]
        for separator in (",", ";"):
            for policy, endpoints in (("nan", ["", ""]), ("clamp", [42, 18]),
                                      ("linear", [45, 14])):
                with self.subTest(separator=separator, policy=policy):
                    actual = self.calculate(x, y, queries, separator=separator, outside=policy)
                    self.assert_cells(actual, [18, 20, 22, 25, 28, 37, 42, *endpoints, 25])

    def test_uses_adjacent_segment_instead_of_all_sample_regression(self):
        actual = self.calculate([[0], [1], [4]], [[0], [10], [2]], [2],
                                x_reference="A2:A4", y_reference="B2:B4", query_reference="D2")
        self.assert_cells(actual, [22 / 3])

    def test_exact_knots_do_not_lose_small_measurement_to_cancellation(self):
        measured = [1e16, 1e-12, -1e12]
        actual = self.calculate([[0.1], [0.3], [0.9]], [[value] for value in measured],
                                [0.1, 0.3, 0.9], x_reference="A2:A4",
                                y_reference="B2:B4", query_reference="D2:D4")
        self.assertEqual(list(actual.flat), measured)

    def test_horizontal_sources_and_query_orientation_are_preserved(self):
        actual = self.calculate([[0, 2, 4]], [[10], [20], [60]], [1, 3, 1, 4],
                                horizontal=True, x_reference="A2:C2", y_reference="A4:A6",
                                query_reference="E2:H2")
        self.assertEqual(actual.shape, (1, 4))
        self.assert_cells(actual, [15, 40, 15, 60])

    def test_queries_keep_actual_blanks_but_reject_text_boolean_and_cell_errors(self):
        queries = [None, "", "1", False, ExcelError("#VALUE!"), 1.5, 0]
        actual = self.calculate([[0], [1], [2]], [[0], [10], [30]], queries,
                                x_reference="A2:A4", y_reference="B2:B4", query_reference="D2:D8")
        self.assert_cells(actual, ["", "#N/A", "#N/A", "#N/A", "#N/A", 20, 0])

    def test_bad_source_cells_return_na_without_silently_cleaning_or_coercing(self):
        for invalid in (None, "", "2", True, ExcelError("#VALUE!")):
            for role in ("x", "y"):
                with self.subTest(role=role, value=invalid):
                    x, y = [[0], [1], [2]], [[0], [10], [30]]
                    (x if role == "x" else y)[1][0] = invalid
                    actual = self.calculate(x, y, [1], x_reference="A2:A4",
                                            y_reference="B2:B4", query_reference="D2")
                    self.assertIsInstance(actual, ExcelError)
                    self.assertEqual(actual.code, "#N/A")

    def test_duplicate_x_is_rejected_even_when_its_y_values_match(self):
        actual = self.calculate([[0], [1], [1]], [[0], [10], [10]], [0.5],
                                x_reference="A2:A4", y_reference="B2:B4", query_reference="D2")
        self.assertIsInstance(actual, ExcelError)
        self.assertEqual(actual.code, "#N/A")

    def test_locale_separator_does_not_modify_quoted_sheet_punctuation(self):
        actual = self.calculate([[0], [2], [4]], [[10], [20], [60]], [1, 3],
                                separator=";", x_reference="'Sensor, O''Brien'!$A$2:$A$4",
                                y_reference="'Sensor, O''Brien'!$B$2:$B$4",
                                query_reference="'Queries; input'!D2:D3")
        self.assert_cells(actual, [15, 40])


class VectorReferenceValidationTests(unittest.TestCase):
    def test_finite_cells_vectors_and_sheet_names_preserve_original_anchors(self):
        cases = [
            (" d2 ", "D2", 1),
            ("$a$2:$a$7", "$A$2:$A$7", 6),
            ("A$2:$D2", "A$2:$D2", 4),
            ("Sheet1!A2:A7", "Sheet1!A2:A7", 6),
            ("'Data, O''Brien!'!$A$2:A7", "'Data, O''Brien!'!$A$2:A7", 6),
            ("'Énergie totale'!B2:D2", "'Énergie totale'!B2:D2", 3),
            ("XFD1048576", "XFD1048576", 1),
        ]
        for supplied, normalized, size in cases:
            with self.subTest(reference=supplied):
                result = parse_vector_reference(supplied)
                self.assertEqual(result.reference, normalized)
                self.assertEqual(result.length, size)

    def test_invalid_blocks_bounds_reversed_refs_and_expressions_are_rejected(self):
        references = [
            "", "A0:A3", "A1:B3", "A7:A2", "D2:A2", "A1:XFE1",
            "A1:A1048577", "A:A", "2:7", "A2#", "Table1[Value]", "Known_X",
            "=A2:A7", "A2:A7+1", "A2,A7", "Data set!A2:A7",
            "'[other.xlsx]Data'!A2:A7", "'Bad/name'!A2:A7",
            "'" + "a" * 32 + "'!A2:A7", "'Data\nset'!A2:A7",
        ]
        for reference in references:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                parse_vector_reference(reference)

    def test_formula_generator_rejects_insufficient_or_mismatched_source_ranges(self):
        for x, y in (("A2", "B2"), ("A2:A7", "B2:B6"), ("A2:C2", "B2:B3")):
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                build_linear_formula(x, y, "D2")

    def test_formula_generator_rejects_unsupported_separator_and_outside_policy(self):
        for setting in ({"separator": "|"}, {"outside": "nearest"}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                build_linear_formula("A2:A7", "B2:B7", "D2", **setting)


if __name__ == "__main__":
    unittest.main()
