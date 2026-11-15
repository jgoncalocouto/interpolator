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


def _looks_numeric(value):
    try:
        float(str(value).strip().replace(",", "."))
        return True
    except (TypeError, ValueError):
        return False


def _parse_table(text: str) -> pd.DataFrame:
    # Keep edge tabs: they represent missing cells in spreadsheet pastes.
    text = text.lstrip("\ufeff").strip("\r\n")
    if not text.strip():
        return pd.DataFrame()
    lines = [line for line in text.splitlines() if line.strip()]
    if any("\t" in line for line in lines):
        delimiter = "\t"
    elif any(";" in line for line in lines):
        delimiter = ";"
    elif any("," in line for line in lines):
        # A whitespace table can contain decimal commas. A comma CSV can also
        # have spaces after commas; those tokens are not themselves numbers.
        numeric_whitespace_rows = [
            re.split(r"\s+", line.strip()) for line in lines
            if len(re.split(r"\s+", line.strip())) > 1
        ]
        whitespace_decimals = any(
            all(_looks_numeric(token) and not token.endswith(",")
                for token in row)
            for row in numeric_whitespace_rows
        )
        delimiter = None if whitespace_decimals else ","
    else:
        delimiter = None
    try:
        if delimiter is None:
            rows = [re.split(r"\s+", line.strip()) for line in lines]
        else:
            rows = list(csv.reader(io.StringIO("\n".join(lines)),
                                   delimiter=delimiter, skipinitialspace=True,
                                   strict=True))
    except csv.Error as error:
        raise ValueError("The table has incomplete quotes. Check the CSV formatting.") from error
    rows = [[cell.strip() for cell in row] for row in rows]
    width = len(rows[0])
    for index, row in enumerate(rows, start=1):
        if len(row) != width:
            raise ValueError(
                f"Row {index} has {len(row)} columns; expected {width}. "
                "Use the same separator on every row."
            )
    has_header = all(not _looks_numeric(cell) for cell in rows[0])
    columns = (_make_unique(rows[0]) if has_header
               else [f"col{index + 1}" for index in range(width)])
    return pd.DataFrame(rows[1:] if has_header else rows, columns=columns)


def read_csv_smart(file) -> pd.DataFrame:
    """Read UTF-8 or Windows CSV with optional headers and common separators."""
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
    return _parse_table(contents)


def read_pasted_table(text: str) -> pd.DataFrame:
    """Read comma, semicolon, tab, or whitespace tables; headers are optional.

    Decimal commas are accepted in semicolon, tab, and whitespace tables.
    A comma-only table treats commas as column separators.
    """
    return _parse_table(text or "")


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
    numeric = df.loc[:, columns].copy()
    for column in columns:
        numeric[column] = pd.to_numeric(
            numeric[column].astype(str).str.strip().str.replace(",", ".", regex=False),
            errors="coerce",
        )
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
