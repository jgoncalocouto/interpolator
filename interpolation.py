"""Table parsing and interpolation independent of the Streamlit interface."""

from __future__ import annotations

import csv
import io
import re

import numpy as np
import pandas as pd
from scipy.interpolate import (
    LinearNDInterpolator,
    NearestNDInterpolator,
    RBFInterpolator,
    RegularGridInterpolator,
)
from scipy.spatial import Delaunay, QhullError


def _make_unique(names):
    used, result = set(), []
    for index, name in enumerate(names, start=1):
        base = str(name).strip() or f"col{index}"
        candidate, suffix = base, 1
        while candidate in used:
            candidate = f"{base}.{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


_DELIMITER_ALIASES = {
    "comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|",
    "space": "whitespace",
}
_DELIMITERS = ("\t", ";", ",", "|", "whitespace")
_THOUSANDS = (None, ",", ".", " ", "'")


def _parse_numeric(value, decimal=".", thousands=None):
    """Convert one value only when its numeric punctuation is well formed."""
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    token = str(value).strip()
    if not token:
        return np.nan
    # Keep nonfinite tokens numeric here; callers explicitly reject them when
    # validating rows. They must never be mistaken for a header.
    if token.lower() in ("nan", "+nan", "-nan", "inf", "+inf", "-inf",
                         "infinity", "+infinity", "-infinity"):
        return float(token)
    exponent_parts = re.split(r"[eE]", token)
    if len(exponent_parts) > 2:
        return np.nan
    mantissa = exponent_parts[0]
    exponent = exponent_parts[1] if len(exponent_parts) == 2 else None
    if exponent is not None and not re.fullmatch(r"[+-]?[0-9]+", exponent):
        return np.nan
    sign = ""
    if mantissa.startswith(("+", "-")):
        sign, mantissa = mantissa[0], mantissa[1:]
    if mantissa.count(decimal) > 1:
        return np.nan
    parts = mantissa.split(decimal)
    integer = parts[0]
    fraction = parts[1] if len(parts) == 2 else None
    if fraction is not None and fraction and not re.fullmatch(r"[0-9]+", fraction):
        return np.nan
    if thousands is not None and thousands in integer:
        groups = integer.split(thousands)
        if (not re.fullmatch(r"[0-9]{1,3}", groups[0])
                or any(not re.fullmatch(r"[0-9]{3}", group) for group in groups[1:])):
            return np.nan
        integer = "".join(groups)
    if integer and not re.fullmatch(r"[0-9]+", integer):
        return np.nan
    if not integer and not fraction:
        return np.nan
    normalized = sign + (integer or "0")
    if fraction is not None:
        normalized += "." + fraction
    if exponent is not None:
        normalized += "e" + exponent
    try:
        return float(normalized)
    except ValueError:
        return np.nan


def _looks_numeric(value):
    token = str(value).strip().lower()
    return (not np.isnan(_parse_numeric(value, "."))
            or not np.isnan(_parse_numeric(value, ","))
            or token in ("nan", "+nan", "-nan"))


def _validate_format(delimiter, decimal, thousands, header):
    delimiter = _DELIMITER_ALIASES.get(delimiter, delimiter)
    if delimiter not in ("auto", *_DELIMITERS):
        raise ValueError("Choose comma, semicolon, tab, pipe, or whitespace as the column separator.")
    if decimal not in ("auto", ".", ","):
        raise ValueError("Choose a decimal point or decimal comma.")
    if thousands not in _THOUSANDS:
        raise ValueError("Choose no thousands separator, comma, point, space, or apostrophe.")
    if decimal != "auto" and decimal == thousands:
        raise ValueError("Decimal and thousands separators must be different.")
    if header != "auto" and not isinstance(header, bool):
        raise ValueError("Choose automatic header detection, a header row, or no header row.")
    return delimiter


def _read_rows(text, delimiter):
    if delimiter == "whitespace":
        # Replace whitespace outside quoted fields; retain CSV escaping and
        # double-quoted column names containing spaces.
        lines = [re.sub(r'\s+(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', "\t", line.strip())
                 for line in text.splitlines() if line.strip()]
        text, delimiter = "\n".join(lines), "\t"
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter,
                               skipinitialspace=True, strict=True))
    except csv.Error as error:
        raise ValueError("The table has incomplete quotes. Check the CSV formatting.") from error
    return [[cell.strip() for cell in row] for row in rows
            if row and not (len(row) == 1 and not row[0].strip())]


def _detect_delimiter(text):
    candidates = []
    for delimiter in _DELIMITERS:
        try:
            rows = _read_rows(text, delimiter)
        except ValueError:
            continue
        widths = [len(row) for row in rows]
        if widths and max(widths) > 1:
            candidates.append((delimiter, rows, len(set(widths)) == 1))
    consistent = [candidate for candidate in candidates if candidate[2]]
    # Whitespace with decimal commas must not become three CSV columns.
    # Requiring complete numeric tokens avoids treating '1, 2' as decimals.
    whitespace = next((candidate for candidate in consistent
                       if candidate[0] == "whitespace"), None)
    if whitespace and not any(candidate[0] in ("\t", ";", "|") for candidate in consistent):
        if any(all(_looks_numeric(cell) and not cell.endswith(",") for cell in row)
               for row in whitespace[1]):
            return "whitespace"
    if consistent:
        return consistent[0][0]
    # A malformed table should still be parsed with its likely separator so
    # the row-length error is visible, rather than collapsing into one column.
    return candidates[0][0] if candidates else "whitespace"


def _infer_decimal(rows, thousands):
    candidates = [decimal for decimal in (".", ",") if decimal != thousands]
    counts = {decimal: 0 for decimal in candidates}
    ambiguous = []
    mixed_token = False
    for row in rows:
        for value in row:
            token = str(value).strip()
            for decimal in candidates:
                if decimal in token and not np.isnan(_parse_numeric(token, decimal, thousands)):
                    counts[decimal] += 1
            if thousands is None:
                if re.fullmatch(r"[+-]?[0-9]{1,3}[.,][0-9]{3}", token):
                    ambiguous.append(token)
                if re.fullmatch(r"[+-]?[0-9.,]+(?:[eE][+-]?[0-9]+)?", token) and "." in token and "," in token:
                    mixed_token = True
    chosen = max(candidates, key=lambda decimal: counts[decimal])
    warnings = []
    if all(counts.get(decimal, 0) for decimal in (".", ",")):
        name = "point" if chosen == "." else "comma"
        warnings.append(
            f"Mixed decimal marks found. Using decimal {name}; values using the other "
            "mark are invalid. Choose the decimal separator explicitly to correct this."
        )
    if ambiguous:
        example = ambiguous[0]
        name = "point" if chosen == "." else "comma"
        warnings.append(
            f"{example!r} could use a decimal mark or a thousands separator. "
            f"Assuming decimal {name} and no thousands grouping. Confirm the number format."
        )
    if mixed_token:
        warnings.append(
            "Some values contain both comma and point punctuation. Thousands grouping "
            "is never inferred; select decimal and thousands separators explicitly."
        )
    return chosen, warnings


def _parse_table(text, delimiter="auto", decimal="auto", thousands=None, header="auto"):
    delimiter = _validate_format(delimiter, decimal, thousands, header)
    # Keep edge tabs: they represent missing cells in spreadsheet pastes.
    text = text.lstrip("\ufeff").strip("\r\n")
    resolved = _detect_delimiter(text) if delimiter == "auto" else delimiter
    rows = _read_rows(text, resolved) if text.strip() else []
    if rows:
        width = len(rows[0])
        for index, row in enumerate(rows, start=1):
            if len(row) != width:
                raise ValueError(
                    f"Row {index} has {len(row)} columns; expected {width}. "
                    "Use the same separator on every row or choose the column separator explicitly."
                )
    # Number-looking first rows remain data even when their punctuation is
    # invalid. Header detection must not silently discard a malformed sample.
    def numeric_header_cell(cell):
        return _looks_numeric(cell) or bool(re.fullmatch(
            r"[+-]?(?=[0-9., '\u00a0]*[0-9])[0-9., '\u00a0]+(?:[eE][+-]?[0-9]+)?",
            cell.strip(),
        ))

    has_header = (
        bool(rows) and all(not numeric_header_cell(cell) for cell in rows[0])
    ) if header == "auto" else header
    data_rows = rows[1:] if has_header else rows
    inferred_decimal, warnings = (_infer_decimal(data_rows, thousands)
                                  if decimal == "auto" else (decimal, []))
    if rows:
        columns = (_make_unique(rows[0]) if has_header
                   else [f"col{index + 1}" for index in range(len(rows[0]))])
        frame = pd.DataFrame(data_rows, columns=columns)
    else:
        frame = pd.DataFrame()
    frame.attrs["import_format"] = {
        "delimiter": resolved,
        "decimal": inferred_decimal,
        "thousands": thousands,
        "header": bool(has_header),
        "warnings": warnings,
    }
    return frame


def read_csv_smart(file, delimiter="auto", decimal="auto", thousands=None, header="auto"):
    """Read a file with explicit or reported inferred column/number formats.

    Returns string cells with the resolved settings in ``attrs['import_format']``.
    Thousands grouping is only accepted when the user selects it explicitly.
    """
    if hasattr(file, "getvalue"):
        contents = file.getvalue()
    elif hasattr(file, "read"):
        if hasattr(file, "seek"):
            file.seek(0)
        contents = file.read()
    else:
        raise ValueError("Choose a CSV file to load your data.")
    if isinstance(contents, bytes):
        try:
            contents = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            contents = contents.decode("cp1252")
    return _parse_table(contents, delimiter, decimal, thousands, header)


def read_pasted_table(text, delimiter="auto", decimal="auto", thousands=None, header="auto"):
    """Read a pasted table using explicit or reported inferred format settings.

    Numeric conversion is separate; call ``numeric_columns`` for a preview.
    Comma-delimited decimal-comma cells must be quoted, as in standard CSV.
    """
    return _parse_table(text or "", delimiter, decimal, thousands, header)


def numeric_columns(df, columns):
    """Convert selected columns using the table's resolved number format.

    Preserve row order/index and coerce invalid grouping or text to NaN.
    A programmatically-created DataFrame without import settings infers a
    decimal mark for backwards compatibility; its numeric cells stay numeric.
    """
    columns = list(columns)
    if any(column not in df.columns for column in columns):
        raise ValueError("A selected column is no longer available. Select the columns again.")
    settings = df.attrs.get("import_format", {})
    decimal = settings.get("decimal", "auto")
    thousands = settings.get("thousands")
    _validate_format("auto", decimal, thousands, "auto")
    if decimal == "auto":
        decimal, _ = _infer_decimal(df.loc[:, columns].to_numpy().tolist(), thousands)
    numeric = df.loc[:, columns].copy()
    for column in columns:
        numeric[column] = numeric[column].map(lambda value: _parse_numeric(value, decimal, thousands))
    return numeric


def result_csv(df, delimiter=",", decimal="."):
    """Export UTF-8 CSV with a BOM and proper quoting for the chosen format."""
    delimiter = _DELIMITER_ALIASES.get(delimiter, delimiter)
    if delimiter not in (",", ";", "\t", "|", " "):
        raise ValueError("Choose comma, semicolon, tab, pipe, or space for CSV export.")
    if decimal not in (".", ","):
        raise ValueError("Choose a decimal point or decimal comma for CSV export.")
    return df.to_csv(index=False, sep=delimiter, decimal=decimal).encode("utf-8-sig")


def parse_float_list(text: str, decimal_comma: bool = False) -> np.ndarray:
    """Read query values without silently dropping invalid entries.

    By default commas always separate values, including across multiple lines.
    In explicit decimal-comma mode, commas belong to numbers and values must
    be separated by whitespace, tabs, newlines, or semicolons.
    """
    text = (text or "").strip()
    if not text:
        return np.array([], dtype=float)
    separator = r"[;\s]+" if decimal_comma else r"[,;\s]+"
    parts = [part for part in re.split(separator, text) if part]
    values = []
    for index, part in enumerate(parts, start=1):
        try:
            value = float(part.replace(",", ".") if decimal_comma else part)
        except ValueError as error:
            hint = (" In decimal-comma mode, separate numbers with spaces, "
                    "newlines, tabs, or semicolons." if decimal_comma else "")
            raise ValueError(
                f"Value {index} ({part!r}) is not a number. Correct or remove it.{hint}"
            ) from error
        if not np.isfinite(value):
            raise ValueError(f"Value {index} must be a finite number; found {part!r}.")
        values.append(value)
    return np.asarray(values, dtype=float)


def prepare_reference(df: pd.DataFrame, columns):
    """Convert finite numeric rows and average duplicate input coordinates.

    The last selected column is the output; all preceding columns are inputs.
    Return the clean data and counts for honest feedback in the interface.
    """
    columns = list(columns)
    if len(columns) not in (2, 3):
        raise ValueError("Select two columns for 1-D or three columns for 2-D interpolation.")
    if len(set(columns)) != len(columns):
        raise ValueError("Choose a different column for each input and output.")
    if any(column not in df.columns for column in columns):
        raise ValueError("A selected column is no longer available. Select the columns again.")
    numeric = numeric_columns(df, columns)
    valid = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    numeric = numeric.loc[valid]
    clean = numeric.groupby(columns[:-1], as_index=False, sort=True)[columns[-1]].mean()
    report = {
        "input_rows": len(df),
        "invalid_rows": int((~valid).sum()),
        "duplicates_merged": len(numeric) - len(clean),
    }
    return clean.reset_index(drop=True), report


def prepare_xy(df, x_col, y_col):
    return prepare_reference(df, [x_col, y_col])[0]


def dedupe_xy_mean(df, xcol, ycol, zcol):
    return prepare_reference(df, [xcol, ycol, zcol])[0]


def _queries(*arrays):
    converted = [np.asarray(array, dtype=float) for array in arrays]
    if any(not np.isfinite(array).all() for array in converted):
        raise ValueError("Query points must contain only finite numbers.")
    if any(array.shape != converted[0].shape for array in converted[1:]):
        raise ValueError("X and Y queries must have the same shape.")
    return converted


def _validate_curve(x, y):
    x, y = _queries(x, y)
    if x.ndim != 1 or y.ndim != 1 or len(x) < 2:
        raise ValueError("Provide at least two distinct X values with matching Y values.")
    if np.any(np.diff(x) <= 0):
        raise ValueError("Reference X values must be unique and sorted from lowest to highest.")
    return x, y


def interp_linear(x, y, xi, extrap="clamp"):
    x, y = _validate_curve(x, y)
    (xi,) = _queries(xi)
    if extrap not in ("clamp", "linear", "nan"):
        raise ValueError("Choose a supported outside-range behavior.")
    flat = xi.ravel()
    result = np.interp(flat, x, y, left=np.nan, right=np.nan)
    left, right = flat < x[0], flat > x[-1]
    if extrap == "clamp":
        result[left], result[right] = y[0], y[-1]
    elif extrap == "linear":
        result[left] = y[0] + (y[1] - y[0]) / (x[1] - x[0]) * (flat[left] - x[0])
        result[right] = y[-1] + (y[-1] - y[-2]) / (x[-1] - x[-2]) * (flat[right] - x[-1])
    return result.reshape(xi.shape)


def interp_nearest(x, y, xi, extrap="clamp"):
    x, y = _validate_curve(x, y)
    (xi,) = _queries(xi)
    if extrap not in ("clamp", "linear", "nan"):
        raise ValueError("Choose a supported outside-range behavior.")
    indices = np.searchsorted(x, xi)
    left = np.clip(indices - 1, 0, len(x) - 1)
    right = np.clip(indices, 0, len(x) - 1)
    nearest = np.where(np.abs(xi - x[right]) < np.abs(xi - x[left]), right, left)
    result = np.asarray(y[nearest], dtype=float)
    if extrap == "nan":
        result = np.where((xi < x[0]) | (xi > x[-1]), np.nan, result)
    return result


def is_full_grid(x, y):
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != y.shape or x.size == 0:
        return False
    points = np.column_stack([x.ravel(), y.ravel()])
    return (len(np.unique(points, axis=0)) == len(points)
            and x.size == np.unique(x).size * np.unique(y).size)


def build_forward_interpolator(df, xcol, ycol, zcol, method="auto", extrap="nan"):
    if method == "linearnd":
        method = "linear"
    if method not in ("auto", "regular", "linear", "nearest", "rbf"):
        raise ValueError("Choose a supported interpolation method.")
    if extrap not in ("nan", "nearest"):
        raise ValueError("Choose a supported outside-domain behavior.")
    data, _ = prepare_reference(df, [xcol, ycol, zcol])
    if len(data) < 3:
        raise ValueError("2-D interpolation needs at least three distinct points forming an area.")
    x, y, z = (data[column].to_numpy(dtype=float) for column in (xcol, ycol, zcol))
    points = np.column_stack([x, y])
    # Normalize the geometry for numerical stability when axis units differ.
    origin = points.min(axis=0)
    scale = np.ptp(points, axis=0)
    if np.any(scale == 0):
        raise ValueError("2-D points must vary in both X and Y. Use 1-D for a line of points.")
    normalized = (points - origin) / scale
    if np.linalg.matrix_rank(normalized - normalized[0]) < 2:
        raise ValueError("The points lie on a line. Add points forming an area, or use 1-D interpolation.")
    try:
        hull = Delaunay(normalized)
    except QhullError as error:
        raise ValueError("The points do not form a usable 2-D area. Check the X and Y columns.") from error
    grid = is_full_grid(x, y)
    actual = ("regular" if grid else "linear") if method == "auto" else method
    if actual == "regular" and not grid:
        raise ValueError("Grid interpolation needs every X/Y combination. Choose Automatic for scattered points.")

    nearest = NearestNDInterpolator(points, z)
    if actual == "regular":
        unique_x, unique_y = np.unique(x), np.unique(y)
        surface = data.pivot(index=xcol, columns=ycol, values=zcol).reindex(
            index=unique_x, columns=unique_y).to_numpy(dtype=float)
        interpolator = RegularGridInterpolator(
            (unique_x, unique_y), surface, method="linear", bounds_error=False,
            fill_value=np.nan,
        )
        evaluator = lambda query: interpolator(query)
    elif actual == "linear":
        # Preserve the input coordinate metric when triangulating samples.
        # Scaling axes can change which diagonal a scattered mesh chooses.
        try:
            interpolator = LinearNDInterpolator(points, z, fill_value=np.nan)
        except QhullError as error:
            raise ValueError(
                "The coordinate scales are too different to interpolate reliably. "
                "Express X and Y in comparable units, or choose Nearest point."
            ) from error
        evaluator = lambda query: interpolator(query)
    elif actual == "nearest":
        evaluator = lambda query: nearest(query)
    else:
        try:
            interpolator = RBFInterpolator(normalized, z, kernel="thin_plate_spline")
        except (ValueError, np.linalg.LinAlgError) as error:
            raise ValueError("A smooth surface could not be fitted. Try Automatic or Nearest point.") from error
        evaluator = lambda query: interpolator((query - origin) / scale)

    def inside_domain(xq, yq):
        xq, yq = _queries(xq, yq)
        query = np.column_stack([xq.ravel(), yq.ravel()])
        return (hull.find_simplex((query - origin) / scale, tol=1e-10) >= 0).reshape(xq.shape)

    def evaluate(xq, yq):
        xq, yq = _queries(xq, yq)
        if xq.size == 0:
            return np.empty(xq.shape, dtype=float)
        query = np.column_stack([xq.ravel(), yq.ravel()])
        output = np.asarray(evaluator(query), dtype=float).reshape(-1)
        outside = ~inside_domain(xq, yq).ravel()
        if extrap == "nearest":
            replace = outside | ~np.isfinite(output)
            if replace.any():
                output[replace] = nearest(query[replace])
        else:
            output[outside] = np.nan
        return output.reshape(xq.shape)

    return evaluate, {"type": actual, "clean_data": data, "inside_domain": inside_domain}
