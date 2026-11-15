# Interpolator

A Streamlit tool for estimating Y from X, or Z from X and Y. Upload a CSV,
paste spreadsheet cells, or try the built-in examples.

## Run locally

Use Python 3.10 or later. From the project directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run main.py
```

Open the local URL printed by Streamlit. On macOS/Linux, use
`.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

## Workflow

1. **Add known data.** Choose an example, upload a CSV, or paste a table.
   Check the detected format, map different columns to the input and output
   roles, and compare the original cells with the numeric preview.
2. **Choose what to estimate.** Enter query values or coordinate pairs, select a
   method and an outside-data policy, then select **Calculate values**.
3. **Inspect results.** Review the chart and status of every query. Choose a
   download format if needed, then export the results. Exports keep the original
   query order, duplicate queries, and full numeric precision
   (`xi, yi, status` or `xi, yi, zi, status`).

Results stay available across interactions. Changing calculation inputs marks
the previous results and disables their download until you calculate again.
Pasted text, column selections, uploaded files, and results are retained within
the active Streamlit session. A browser refresh or server restart can reset that
session; download results you want to keep. Use **Clear uploaded file** to remove
a retained upload from the current session.

## Importing tables

Pasted reference tables, reference CSV uploads, and 2D query tables each have
their own **Import settings**. Column separator, decimal separator, and header
presence start with **Auto detect**. The **Read as** summary shows the selected
interpretation, row count, and column count; override any setting that does not
match your file.

| Setting | Choices |
| --- | --- |
| Column separator | Auto detect, comma, semicolon, tab, whitespace, or pipe |
| Decimal separator | Auto detect, point (`1.25`), or comma (`1,25`) |
| First row contains column names | Auto detect, Yes, or No |
| Thousands separator | None, comma, point, space, or apostrophe |

Thousands separators are never guessed. Choose one only when your numbers use
it, and use a different character for the decimal separator. For example,
semicolon-separated cells containing `1.234,50` need **Decimal separator: Comma**
and **Thousands separator: Point** to read as `1234.5`.

**Check how your numbers are read** compares the first five original data rows
with the numbers used for calculation, before exclusions or duplicate averaging.
Numeric previews use decimal points. Check the scale of your values, not just
whether they appear numeric: `1,234` can mean different values in different
formats. Automatic detection is a convenience; the preview and explicit controls
let you verify its assumptions.

- Each row must have the same number of columns. CSV uploads support UTF-8
  (including BOM) and Windows-1252 text.
- For unquoted decimal commas, use tabs or semicolons between columns:
  `0,5;12,5`. Quoted decimal-comma values also work with comma-separated columns:
  `"0,5","12,5"`.
- Set **First row contains column names** explicitly when numeric column names
  or an unusual first data row make automatic header detection unsuitable.
- A 1D query list accepts newlines, commas, spaces, tabs, or semicolons.
  Commas separate values by default, so `1,2` means two queries.
  Enable **Use decimal commas** to interpret `1,2` as `1.2`; separate those
  values with whitespace or semicolons. These lists do not use the table import
  settings or support thousands grouping; enter ungrouped query values.
- Reference rows containing missing, nonnumeric, or infinite selected values are
  excluded with a visible count. Repeated reference X values (1D), or X/Y pairs
  (2D), are averaged and reported. Invalid query rows block the whole calculation
  so no query is silently discarded.
- 1D needs at least two distinct X values. 2D needs at least three distinct
  coordinate pairs forming an area; use 1D when the points lie on a line.

## Download format

Open **CSV download format** beside the results to choose comma, semicolon, tab,
or pipe columns, and either decimal points or decimal commas. A short text
preview shows exactly how the file will be written. The default is comma columns
with decimal points; semicolon columns with decimal commas suit many European
spreadsheet configurations. Values are quoted when needed, and no thousands
grouping is added.

Tab-separated downloads use a `.tsv` extension; the other choices use `.csv`.
Files use UTF-8 with a byte-order mark for spreadsheet compatibility. Changing
the download format preserves the calculated values and does not require a new
calculation. Changing imported numeric values marks previous results as stale.

## Methods and outside-data behavior

1D supports linear and nearest-sample interpolation. Outside the measured X
range, leave results blank, keep the boundary value, or extend end slopes
(linear interpolation only).

2D supports automatic, scattered linear, nearest sample, bilinear grid, and
smooth RBF interpolation. Automatic uses bilinear interpolation when every X/Y
combination is present and scattered linear otherwise. All 2D methods apply the
selected outside policy consistently: leave blank or use the nearest sample.
The known region is the convex hull of the reference coordinates, which may be
smaller than the rectangle defined by the individual axis ranges. Distances for
nearest samples use the supplied coordinate units; the RBF fit scales its axes.

Outside-data results have explicit statuses in the table and CSV. Blank is the
default because extending beyond known data requires an additional assumption.

## Verify changes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers imports, every interpolation method and outside-data policy,
number previews, result persistence and recovery, uploads, charts, downloads,
and the support widget. GitHub Actions is configured to run it on Linux and
Windows, with a 90% statement-and-branch coverage gate.

See [TESTING.md](TESTING.md) for the feature map, coverage commands, CI matrix,
and browser checks that remain manual.

See [UX_REVIEW.md](UX_REVIEW.md) for review findings, design decisions, and
remaining validation work.
