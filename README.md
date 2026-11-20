# Spreadsheet to Drawing

The app builds a rectangular pegboard with vertical through-slots from seven millimetre dimensions. It produces an editable FreeCAD source document, a four-view engineering sheet, CAD exchange files, and measured acceptance evidence. [SOURCE_BRIEF.md](SOURCE_BRIEF.md) preserves the original requirements.

## Run the full local app

The tested configuration is Debian 13, FreeCAD 1.0.0 with its Python 3.13 bindings, Inkscape, Python 3.12 for the web API, and Node 22 or later for frontend development. The repository includes a prebuilt frontend. Node is needed to rebuild it.

1. Install FreeCAD 1.0 or a compatible release, Python 3.11+, and Inkscape. On compatible Debian releases, install `freecad inkscape python3-venv` from your package manager.
2. From the extracted project directory, set up the API environment.

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r backend/requirements.txt
   ./scripts/start.sh
   ```

3. Open http://127.0.0.1:8000. The worker status displays the detected FreeCAD version. http://127.0.0.1:8000/docs exposes the API schema.
4. To rebuild the UI, run `npm ci && npm run build` inside `frontend`.

### FreeCAD worker setup

On Debian the API detects `/usr/lib/freecad-python3/lib/FreeCAD.so` and starts `/usr/bin/python3` in a dedicated worker process. The API's virtual environment can use a different Python version. Set `FREECAD_PYTHON`, `FREECAD_LIB`, and `FREECAD_RESOURCES` for another compatible module installation. The worker preloads Draft, BIM or Arch, Part, and FreeCAD's bundled Python extensions from the resource tree. Add Inkscape to PATH for PDF generation.

For Windows, activate `.venv\Scripts\Activate.ps1`, set `$env:PYTHONPATH="backend"`, and start `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. On macOS, the same Uvicorn command works after `export PYTHONPATH=backend`. Set `FREECAD_EXECUTABLE` to the full executable path for the installed desktop build if detection fails. The fallback invokes a temporary FreeCAD macro and requires a working graphical session. On platforms where the GUI needs it, set `QT_QPA_PLATFORM` to the platform plugin such as `windows`, `cocoa`, or `xcb`. The Windows and macOS runners have setup paths in source and were not exercised here.

## Demo and video

Use the **Interactive demo** link in the app or open the repository’s root `index.html` after cloning or extracting the GitHub ZIP. Keep the `demo/samples` directory beside it for video and downloads. The demo also has its own entry point at `demo/index.html`. The standalone demo can be opened directly after extraction. If your browser restricts local HTML, run `python -m http.server 8080` in the demo directory and open http://127.0.0.1:8080. It supports editable parameters, CSV import, case presets, live calculations, 2D and WebGL previews, and sample downloads. **Demo video** opens the captioned walkthrough in either workspace. Demo downloads and test outcomes are recorded nominal samples. [Download the walkthrough video](demo/samples/walkthrough.mp4) or [view the acceptance log](outputs/acceptance/pegboard_test_log.csv). Start the local workspace to execute FreeCAD with edited dimensions and to import XLSX.

## Use the engineering workflow

1. Load `templates/pegboard_parameters.xlsx` or its CSV equivalent. Column A contains exact aliases and column B contains values in millimetres. Excel formula cells require cached numeric values. An import applies a valid set immediately. Edits in the form apply with **Apply parameters**.
2. Inspect the slot positions in **2D Top** or rotate the solid preview in **3D Orbit**. The browser 3D view builds a lightweight visual extrusion from validated coordinates. The actual CAD artifact comes from FreeCAD.
3. Select **Generate CAD model**. Subsequent generations from the same page reopen the previous native file and edit only the seven parameter cells. Validation failures leave the last successful artifact and preview available. Select **Generate 2D drawing** to produce the drawing sheet and its exports.
4. Run **Run three-case tests** to regenerate all three variants in one FreeCAD document and download the CSV log, JSON report and native case files.

### Source document and equations

Open an FCStd file in FreeCAD 1.0 or newer. Double-click **Parameters** and edit B2:B8 using values with the `mm` suffix. Recompute with F5 if FreeCAD delays updates. Calculated cells B9:B19 keep their formulas and stable aliases.

- `BoardBlank` is a Part box at the XY origin. Volume is `width × height × thickness`.
- `MasterSlot` is fully constrained at the sketch origin and placed at `(edgeMargin, edgeMargin, -1 mm)`. `ThroughCutter` extends through the blank using `thickness + 2 mm`.
- FreeCAD's bundled Draft orthogonal array repeats the cutter. `Pegboard` is the Part subtraction of this array from the blank. The model uses property and sketch constraints throughout, avoiding generated-face references.
- Each pitch is the corresponding slot dimension plus the material spacing. On either axis the minimum board span is twice the margin plus the slot dimension. Occurrence count is `floor((board span − minimum span + tolerance) / pitch) + 1`. To fit occurrence `n`, the span must reach `minimum span + (n−1) × pitch`.
- Locations use `x = margin + columnIndex × pitchX` and `y = margin + rowIndex × pitchY`. The required edge margin is measured from the board boundary to the nearest edge of each opening.
- The CAD and spreadsheet use a tolerance of **0.0000001 mm** for occurrence boundaries and geometry verification. The API enforces board minima with a separate tolerance for binary round-off. A zero perimeter web opens a slot to the edge, and zero spacing joins adjacent openings. The app rejects either when distinct enclosed openings would be lost. Zero spacing is valid for a one-slot board. Limits are 2,000 slots and 1,000,000 mm per input.
- Use the web workspace for validated edits and export transactions. For direct edits inside the FreeCAD GUI, check the computed worksheet and geometry before saving. Drawing annotations and scale are generated snapshots. Regenerate the drawing after changing parameters.

### Drawing and export formats

- **FCStd** retains the Parameters spreadsheet, master sketch, cutter, array and cut. Drawing jobs add a TechDraw page with top, front, right and isometric views connected to the cut. The dimension lines, repeated-feature notes, and title block are embedded in the page template.
- **STEP** is the verified final solid for interchange. The parametric construction remains in FCStd.
- **SVG and PDF** contain a four-view A4 sheet built from TechDraw's visible edge projections of the final solid. The sheet lists thickness, slot size, margin, pitch and quantity. Inkscape renders the vector PDF from the SVG.
- **DXF** is a 1:1 millimetre top profile. Geometry uses `CUT_PROFILE` and manufacturing notes use `ANNOTATIONS`. Each straight segment is a LINE entity. For machining, import only the cut layer and use the PDF for drawing context.
- Fill in the material field before producing a drawing for release. The sample preserves the field for engineering review.

## Testing and evidence

```sh
PYTHONPATH=backend python -m pytest -q backend/tests
PYTHONPATH=backend RUN_CAD_TESTS=1 python -m pytest -q backend/tests
```

On Windows PowerShell, use `$env:PYTHONPATH="backend"` and `$env:RUN_CAD_TESTS="1"` before running pytest.

The geometric verifier checks FreeCAD expressions and sketch constraints, feature links, recompute state, validity and bounds of the solid, removed volume, slot loops and locations on both faces, and the measured clearances on all four edges. The acceptance log contains exactly three cases. The separate JSON includes geometry evidence and threshold runs on both axes. The default row boundary is 86 mm and the default column boundary is 48 mm. The actual integration suite also verifies reopening and recomputing from a saved FCStd, invalid edit rejection and export formats.

Included acceptance artifacts were produced by FreeCAD 1.0.0. The case outputs have 1, 80 and 95 through-slots. `outputs/nominal` contains the nominal FCStd, STEP, DXF, SVG, and PDF. `outputs/acceptance` contains the case models and test reports. Subsequent runs are stored under `outputs/jobs`, with a new job ID for each successful operation. The app serves these outputs only through the allowlisted export route.

## Implementation map

- `backend/app/parameters.py` defines the common server-side millimetre model.
- `backend/app/cad.py` builds and independently verifies FreeCAD features and runs acceptance tests.
- `backend/app/drawing.py` projects the checked solid and builds the native drawing page and exports.
- `backend/app/main.py` handles spreadsheet exchange and transactional worker jobs.
- `frontend/src` contains the React/TypeScript workspace, lightweight 3D preview and standalone demo calculation path.
