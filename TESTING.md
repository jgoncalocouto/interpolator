# Tests and feature coverage

The suite combines numerical expectations, parser and export contracts,
Streamlit interaction tests, and checks of the generated chart and support-link
content. Tests use small in-memory datasets; they do not contact payment services
or need a running browser or Streamlit server.

## Run the suite

From the project directory, after creating the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Measure coverage and enforce the configured minimum:

```powershell
.\.venv\Scripts\python.exe -m coverage run -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m coverage html
```

Open `htmlcov/index.html` for the source report. Coverage includes statements
and branches in `main.py`, `interpolation.py`, and `coffee_widget.py`, with a
90% minimum. Generated reports are ignored by Git. Coverage is a regression
guard; the numerical assertions and workflow checks establish the behavior.

On macOS/Linux, use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe`.

## Feature map

| Feature | Automated checks | Tests |
| --- | --- | --- |
| CSV uploads and pasted tables | Optional headers, duplicate names, quoted separators, consistent row widths, empty cells, encodings, and file streams | `test_interpolation.py`, `test_core_features.py` |
| Import formats | Automatic and explicit column/decimal separators, valid and invalid thousands grouping, scientific notation, header overrides, and ambiguous-format feedback | `test_interpolation.py`, `test_core_features.py`, `test_app.py`, `test_app_features.py` |
| Data preparation | Finite values, excluded-row counts, sorting, duplicate X/X-Y means, retained original strings, and repeated numeric conversion | `test_interpolation.py`, `test_core_features.py`, `test_app.py` |
| Number previews | Original versus parsed values, first five rows before cleaning, query order, and independent source settings | `test_app.py`, `test_app_features.py` |
| 1D calculations | Linear and nearest methods, exact samples, nearest ties, boundaries, scalar/array shapes, and every outside-range policy | `test_interpolation.py`, `test_core_features.py`, `test_app_features.py` |
| 2D calculations | Automatic/grid/scattered/nearest/RBF methods, analytical results, non-affine bilinear values, sample recovery, hull boundaries, and invalid geometry | `test_interpolation.py`, `test_core_features.py`, `test_app_features.py` |
| Query validation and mapping | Whole-batch rejection, nonfinite values, distinct source columns, additional query columns, order, and duplicate queries | `test_interpolation.py`, `test_app.py`, `test_app_features.py` |
| Result state | Independent workflows, persistence, changed-input warnings, disabled stale downloads, recalculation, and error recovery | `test_app.py`, `test_app_features.py` |
| Upload retention | Uploaded file objects, retained bytes, source switching, replacement, and explicit clearing | `test_presentation.py`, `test_app.py`, `test_app_features.py` |
| Charts and statuses | Nearest steps, reference/query coordinates, known-region blanks, outside-result labels, and table preservation if plotting fails | `test_presentation.py`, `test_app.py`, `test_app_features.py` |
| Example data | Usable example workflows and downloadable example contents | `test_app.py`, `test_app_features.py` |
| CSV/TSV downloads | Every offered separator/decimal combination, quoting, Unicode/BOM, precision, missing values, statuses, filenames, MIME types, and unchanged numerical results when export settings change | `test_interpolation.py`, `test_core_features.py`, `test_app.py`, `test_app_features.py` |
| Coffee support widget | Default/custom link and title, escaped attribute content, and safe new-tab attributes | `test_presentation.py` |

All test paths above are under `tests/`. `app_test_support.py` contains common
fixtures and assertions without test methods, so sharing setup does not run
existing tests a second time.

## Continuous integration

`.github/workflows/tests.yml` runs the complete suite and coverage gate on
pushes, pull requests, and manual workflow runs. Its matrix covers Python 3.10
and 3.13 on Linux, plus Python 3.13 on Windows. Coverage XML and HTML reports
are uploaded as workflow artifacts, including on failures when reports can be
generated. The workflow will run after it is published to GitHub.

## Browser checks still required

AppTest exercises Streamlit state and controls without rendering browser
pixels. Upload tests use real uploaded-file objects at the handler boundary,
cached records for portable workflow coverage, and direct file-widget input
when the installed Streamlit testing API supports it. Only that API-specific
check is skipped on older versions. Tests do not operate an operating-system
file chooser.

Before a release, manually check:

1. Both workflows on desktop and narrow screens, keyboard navigation, visible
   labels, and whether the floating coffee button obscures any controls.
2. A real CSV upload, replacement and clearing, then a browser download opened
   in the target spreadsheet application with point and comma decimal settings.
3. Chart hover/zoom behavior and the appearance of outside-data or blank results.

No automated coverage percentage establishes accessibility, screen-reader
behavior, responsive layout, or compatibility with every spreadsheet locale.
