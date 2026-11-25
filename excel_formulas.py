"""Generate compact and guarded piecewise-linear Excel formulas.

References are bounded A1 vectors in the current workbook. Workbook data is
never read here; only the guarded formula validates its cell contents in Excel.
"""

from dataclasses import dataclass
import re


_REFERENCE = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_\u0080-\uffff][\w.]*)!)?"
    r"(?P<first>\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6})"
    r"(?::(?P<last>\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}))?"
)
_CELL = re.compile(r"(?P<column>\$?[A-Za-z]{1,3})(?P<row>\$?[0-9]+)")


@dataclass(frozen=True)
class VectorReference:
    reference: str
    length: int
    horizontal: bool = False


def parse_vector_reference(value, label="Range"):
    """Accept a cell or one row/column, preserving sheet names and $ anchors."""
    value = value.strip()
    if not value:
        raise ValueError(f"Enter the {label} reference, for example $A$2:$A$7.")
    match = _REFERENCE.fullmatch(value)
    if match is None:
        raise ValueError(
            f"{label}: use a cell or A1 range, such as D2, $A$2:$A$7, or 'My data'!A2:A7."
        )
    sheet = match["sheet"]
    if sheet:
        name = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
        if len(name) > 31 or any(character in name for character in "[]:*?/\\\r\n"):
            raise ValueError(f"{label}: use a valid sheet name in the current workbook.")
    cells, positions = [], []
    for token in (match["first"], match["last"] or match["first"]):
        cell = _CELL.fullmatch(token)
        column = cell["column"].replace("$", "").upper()
        column_number = 0
        for character in column:
            column_number = column_number * 26 + ord(character) - ord("A") + 1
        row = int(cell["row"].replace("$", ""))
        if column_number > 16384 or row > 1048576:
            raise ValueError(f"{label}: Excel references end at column XFD and row 1048576.")
        positions.append((column_number, row))
        cells.append(token.upper())
    (first_column, first_row), (last_column, last_row) = positions
    if last_column < first_column or last_row < first_row:
        raise ValueError(f"{label}: put the top-left cell first, for example A2:A7.")
    if first_column != last_column and first_row != last_row:
        raise ValueError(f"{label}: choose one row or one column, rather than a rectangular block.")
    length = max(last_column - first_column, last_row - first_row) + 1
    reference = (f"{sheet}!" if sheet else "") + cells[0]
    if match["last"]:
        reference += ":" + cells[1]
    return VectorReference(reference, length, first_row == last_row)


def _formula_references(x_reference, y_reference, query_reference, separator):
    if separator not in (",", ";"):
        raise ValueError("Choose a comma or semicolon between Excel function arguments.")
    x = parse_vector_reference(x_reference, "X range")
    y = parse_vector_reference(y_reference, "Y range")
    query = parse_vector_reference(query_reference, "Xi cell or range")
    if x.length < 2 or y.length < 2:
        raise ValueError("X and Y each need at least two cells containing known points.")
    if x.length != y.length:
        raise ValueError(f"X has {x.length} cells and Y has {y.length}. Choose ranges of equal length.")
    return x, y, query


def build_compact_formula(x_reference, y_reference, query_reference, *, separator=","):
    """Use the native-Excel-tested core; valid numeric, unique-X data is assumed.

    XLOOKUP's next-smaller/larger matches work with unsorted data. Queries
    outside the sample range retain #N/A; workbook contents are not validated.
    """
    x, y, query = _formula_references(x_reference, y_reference, query_reference, separator)

    def function(name, *arguments):
        return f"{name}({separator.join(arguments)})"

    y_values = function("TRANSPOSE", y.reference) if x.horizontal != y.horizontal else y.reference
    return "=" + function(
        "LET", "x", x.reference, "y", y_values, "q", query.reference,
        "a", function("XLOOKUP", "q", "x", "x", "NA()", "-1"),
        "b", function("XLOOKUP", "q", "x", "x", "NA()", "1"),
        "u", function("XLOOKUP", "q", "x", "y", "NA()", "-1"),
        "v", function("XLOOKUP", "q", "x", "y", "NA()", "1"),
        function("IF", "a=b", "u", "u+(q-a)/(b-a)*(v-u)"),
    )


def build_linear_formula(x_reference, y_reference, query_reference, *, separator=",", outside="nan"):
    """Return the guarded version with sorting, validation, and outside policies."""
    if outside not in ("nan", "clamp", "linear"):
        raise ValueError("Choose leave blank, keep boundary value, or extend end slopes.")
    x, y, query = _formula_references(x_reference, y_reference, query_reference, separator)

    def function(name, *arguments):
        return f"{name}({separator.join(arguments)})"

    def index(name, position):
        return function("INDEX", name, position)

    def size(reference):
        return f"{function('ROWS', reference)}*{function('COLUMNS', reference)}"

    first_x = index("sortedX", "1")
    last_x = index("sortedX", "sampleCount")
    evaluation_point = (function("MAX", first_x, function("MIN", "point", last_x))
                        if outside == "clamp" else "point")
    segment_value = function(
        "IF", "evaluationPoint=xLow", "yLow",
        function("IF", "evaluationPoint=xHigh", "yHigh",
                 "yLow+(evaluationPoint-xLow)/(xHigh-xLow)*(yHigh-yLow)"),
    )
    interpolate = function(
        "LET", "evaluationPoint", evaluation_point,
        "lowerIndex", function("MAX", "1", function(
            "MIN", "sampleCount-1", function("IFNA", function(
                "XMATCH", "evaluationPoint", "sortedX", "-1", "2"), "1"))),
        "xLow", index("sortedX", "lowerIndex"),
        "xHigh", index("sortedX", "lowerIndex+1"),
        "yLow", index("sortedY", "lowerIndex"),
        "yHigh", index("sortedY", "lowerIndex+1"), segment_value,
    )
    if outside == "nan":
        interpolate = function("IF", function("OR", f"point<{first_x}", f"point>{last_x}"),
                               '""', interpolate)
    per_query = function("IF", "blankPoint", '""',
                         function("IF", "numericPoint", interpolate, function("NA")))
    mapped = function("MAP", query.reference, function("ISNUMBER", query.reference),
                      function("ISBLANK", query.reference),
                      function("LAMBDA", "point", "numericPoint", "blankPoint", per_query))
    prepared = function(
        "LET", "vectorX", function("TOCOL", x.reference),
        "sortedX", function("SORT", "vectorX"),
        "sortedY", function("SORTBY", function("TOCOL", y.reference), "vectorX"),
        "sampleCount", function("ROWS", "sortedX"),
        function("IF", f"{function('ROWS', function('UNIQUE', 'sortedX'))}=sampleCount",
                 mapped, function("NA")),
    )
    # Count the original references before TOCOL, whose blank cells become 0.
    valid = function("AND", f"{function('COUNT', x.reference)}={size(x.reference)}",
                     f"{function('COUNT', y.reference)}={size(y.reference)}",
                     f"{size(x.reference)}={size(y.reference)}", f"{size(x.reference)}>=2")
    return "=" + function("IF", valid, prepared, function("NA"))
