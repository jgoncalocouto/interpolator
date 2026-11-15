# UX review and improvements

This was a heuristic review of the existing code, followed by implementation
and automated workflow checks. It is not a study with representative users.
The framework is [Nielsen's usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).

| Finding | Implemented change | Principle |
| --- | --- | --- |
| The opening screen required a file before demonstrating the tool. | Built-in reference data and query examples are ready to calculate. | Recognition over recall |
| Four open accordions and long method explanations buried the task. | Three numbered steps; inputs and results sit together; technical help is collapsed. | Minimalist design and progressive disclosure |
| A 1D `st.stop()` could prevent the 2D interface from rendering. | Both workflows render independently and return locally when data is missing. | User control and consistency |
| Results disappeared on the next interaction. | Results persist in session state, with a signature of the calculation inputs. | Visibility of system status |
| Old results could be mistaken for current results. | Changed inputs show a warning and disable CSV export until recalculation. | Error prevention |
| Query conversion silently discarded invalid values. | Queries are validated as a whole; errors identify the value or data row to fix. | Error recovery |
| Reference cleaning and averaging happened without useful accounting. | Visible excluded-row and duplicate counts, with original and prepared previews. | Visibility of system status |
| Selecting the same column for multiple roles could fail. | Each role offers distinct columns; source-specific selections are remembered. | Error prevention |
| Uploaded query columns were used by position without mapping controls. | Uploaded and wider query tables offer X/Y column selectors. | User control |
| Internal labels such as `nan`, `regular`, and `xi` added effort. | Plain method names and outside-data policies; table headings include selected source names. | Match with the user's language |
| Outside policies were ignored or failed for some 2D methods. | Consistent region checks for every method and per-query statuses in the table and CSV. | Consistency and trust |
| Decimal commas were ambiguous and could change meaning with line count. | An explicit 1D decimal-comma checkbox; ordinary commas consistently separate queries. | Error prevention |
| Source changes discarded pasted values, uploads, and mappings. | Text and settings survive hidden widgets; uploaded bytes are retained with an explicit clear control. | User control and recovery |
| The nearest-sample chart appeared to interpolate between values. | A step curve uses actual nearest-sample boundaries. | Accurate system feedback |

## Validation and limits

- Numerical tests cover parsing, cleaning, duplicate means, invalid geometry,
  known interpolation values, and outside policies for every 2D method.
- Streamlit AppTest checks independent workflows, result persistence, stale
  downloads, invalid queries, mapping, decimal modes, and source switching.
- Upload tests seed cached file records; browser file chooser interaction is
  not covered by AppTest.
- Visual browser inspection was attempted but the computer-use tool stopped
  because it could not verify Chrome's current URL. Desktop/mobile layout,
  keyboard navigation, screen-reader behavior, and browser downloads still
  need a manual check.
- A useful next validation is to watch a few representative users import their
  own data, identify an outside-data query, and export a result without assistance.
