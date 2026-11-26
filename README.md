# Spreadsheet to Drawing

The app builds a rectangular pegboard with vertical through-slots from seven millimetre dimensions. It produces an editable FreeCAD source document, a four-view engineering sheet, CAD exchange files, and measured acceptance evidence. [SOURCE_BRIEF.md](SOURCE_BRIEF.md) preserves the original requirements.

## Run the full local app

The tested configuration is Debian 13, FreeCAD 1.0.0 with its Python 3.13 bindings, Inkscape, Python 3.12 for the web API, and Node 22 or later for frontend development. The repository includes a prebuilt frontend. Node is needed to rebuild it.

1. Install Python 3.11+, Inkscape, and at least one CAD engine. FreeCAD 1.0 or a compatible release is the default. To use SolidCraft alone or as a fallback, follow the SolidCraft installation section below. On compatible Debian releases, install `freecad inkscape python3-venv` from your package manager.
2. From the extracted project directory, set up the API environment.

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r backend/requirements.txt
   ./scripts/start.sh
   ```

3. Once the terminal reports that Uvicorn is running, open http://127.0.0.1:8000 on the same computer. Keep that terminal open while using the full app. The worker status displays the detected FreeCAD version. http://127.0.0.1:8000/docs exposes the API schema.
4. To rebuild the UI, run `npm ci && npm run build` inside `frontend`.

### FreeCAD worker setup

On Debian the API detects `/usr/lib/freecad-python3/lib/FreeCAD.so` and starts `/usr/bin/python3` in a dedicated worker process. The API's virtual environment can use a different Python version. Set `FREECAD_PYTHON`, `FREECAD_LIB`, and `FREECAD_RESOURCES` for another compatible module installation. The worker preloads Draft, BIM or Arch, Part, and FreeCAD's bundled Python extensions from the resource tree. Add Inkscape to PATH for PDF generation.

For Windows, activate `.venv\Scripts\Activate.ps1`, set `$env:PYTHONPATH="backend"`, and start `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. On macOS, the same Uvicorn command works after `export PYTHONPATH=backend`. Set `FREECAD_EXECUTABLE` to the full executable path for the installed desktop build if detection fails. The fallback invokes a temporary FreeCAD macro and requires a working graphical session. On platforms where the GUI needs it, set `QT_QPA_PLATFORM` to the platform plugin such as `windows`, `cocoa`, or `xcb`. The Windows and macOS runners have setup paths in source and were not exercised here.

## CAD engine switching

The full app normalizes spreadsheet dimensions in millimetres and checks the pattern before starting either CAD engine. Its **CAD engine** control offers **Auto**, **FreeCAD only**, and **SolidCraft only**. The control shows both versions or availability, the last verified engine, and whether the recompute and drawing passed.

**Auto** tries FreeCAD first by default. If its availability check, CAD operation, geometry verification, drawing, or required export fails, the app tries SolidCraft once with the same validated parameters. SolidCraft must finish and pass verification before any output is published. Input validation errors stop before either engine runs. The original job files remain downloadable when a later recompute fails. When switching engines, the app rebuilds from the same spreadsheet values because FCStd and SC store different feature histories. Recomputes within the same engine reopen the prior native document.

Set these variables before starting the full app to change the defaults:

```sh
export CAD_ENGINE=auto
export CAD_PRIMARY=freecad
export CAD_FALLBACK=solidcraft
export CAD_FALLBACK_ENABLED=true
```

The API accepts an optional `engine` field on generate, recompute, drawing, and test requests. The health response lists both engines and the configured defaults. A completed job includes engine version, fallback reason, and ordered attempts in `evidence`. The server logs each attempt’s elapsed time and outcome.

### Install SolidCraft

Download the package for your platform from the official [SolidCraft v0.45.0 release](https://github.com/tangency-labs/solidcraft/releases/tag/v0.45.0), verify the release checksum, and put the bundled `solidcraft-cli` on PATH or set `SOLIDCRAFT_CLI` to its full executable path. On PowerShell use `$env:SOLIDCRAFT_CLI="C:\path\to\solidcraft-cli.exe"`. Check `solidcraft-cli --version` or the CAD engine panel before running a job. This adapter pins **0.45.0** because it relies on that CLI’s drawing commands and result schema. The Linux x86-64 release was tested. Windows and macOS setup paths depend on the platform’s package and have not been exercised here.

| Output | FreeCAD | SolidCraft 0.45.0 |
| --- | --- | --- |
| Native editable model | FCStd with Parameters cells and Draft array | SC with editable parameters, master cut, and feature pattern |
| STEP | Native solid export | Native CLI solid export |
| Browser 3D view | STL tessellation of the generated solid | Native GLB export with materials |
| SVG drawing | TechDraw projections and A4 sheet | Native A3 sheet, with views and associative board dimensions |
| PNG drawing | Inkscape from SVG | Native PNG export |
| PDF drawing | Inkscape from SVG | Inkscape from SVG |
| DXF cut profile | 1:1 mm top projection | 1:1 mm profile from verified model edges |

Install Inkscape on PATH for the complete drawing job. Since PDF is a required output, an Inkscape failure can affect drawing jobs in both engines. DXF is a manufacturing profile with notes. SVG, PNG and PDF contain the four-view drawing.

SolidCraft geometry is built and recomputed through the official JSON command CLI. The application reopens the saved native model and checks its closed shell, expected volume, every through-slot edge on both faces, and the minimum edge clearances. Drawings must contain four drawn views, three measured board dimensions and the slot, pitch, and datum callouts. The pinned CLI exposes `parameters.change` for recomputation, `model.edges` and `inspect.measure` for verification, and `drawing.view.standard`, `drawing.dimension.add` and `drawing.export` for native drawings. The STEP export is reopened and checked for a closed body with the native volume. SolidCraft also offers a [headless MCP server](https://github.com/tangency-labs/solidcraft/blob/v0.45.0/docs/mcp.md). This application runs the [JSON command CLI](https://github.com/tangency-labs/solidcraft/blob/v0.45.0/docs/scripts.md) in isolated subprocesses.

The adapter invokes a separately installed third-party program by Tangency Labs. SolidCraft code offers [MIT](https://github.com/tangency-labs/solidcraft/blob/v0.45.0/LICENSE-MIT) or [Apache-2.0](https://github.com/tangency-labs/solidcraft/blob/v0.45.0/LICENSE-APACHE) terms. Its branding and interface assets have [separate terms](https://github.com/tangency-labs/solidcraft/blob/v0.45.0/LICENSE-BRAND). The project ships its own web interface and does not redistribute SolidCraft binaries, branding, or UI assets.

## Detailed product design

The detailed editor is optional. The existing FreeCAD and SolidCraft workflow remains available without the CADRS worker.

1. Install Rust 1.100 or later and build the worker from the repository root.

   ```sh
   cargo +stable build --release --locked --manifest-path backend/cadrs-worker/Cargo.toml
   ```

   The app discovers `backend/cadrs-worker/target/release/spreadsheet-cadrs-worker` automatically. For a different build directory, set `CADRS_WORKER` to the executable path. Keep the usual FreeCAD or SolidCraft setup for generating the original model.

2. Load [the mounting-plate spreadsheet](templates/detailed_mounting_plate.csv), apply the parameters, and generate CAD. Choose **Create Detailed Product Design**. The source panel displays the XLSX cell, CSV row and column, or manually entered field for each dimension. All supported spreadsheet and editor dimensions are in millimetres.
3. Add a **Rectangular hole pattern** with two rows and two columns. Use an 8 mm X and Y centre, 4 mm diameter, and bind X and Y pitch to **Mounting hole pitch**. Add a **Rectangular pocket** at X 20 mm and Y 50 mm with a 15 × 8 mm footprint and 2 mm depth. Add a 1 mm **Edge chamfer** on the top front edge. Select **Rebuild** to apply the list from top to bottom. Move, suppress, or delete a feature before rebuilding to change the sequence.
4. To try a spreadsheet refresh, change `boardWidth` to 140 and `holeSpacing` to 65 in a copy of the CSV. Use **Refresh from spreadsheet** in the editor. It lists the changed values and attempts a rebuild. The optional `holeSpacing` field drives detailed mounting holes independently of the original `slotSpacing`. If it is removed from the refreshed sheet, any binding to it is flagged for repair.
5. Select **Save variant** after a successful build. **Saved detailed designs** reopens its source link, current spreadsheet snapshot, feature settings and bindings. The history is stored in `outputs/jobs` alongside STEP and STL for the verified revision. A failed rebuild highlights its feature and keeps the last successful preview and files available.

The Python API reuses the spreadsheet parser, parameter validation and exact slot coordinates. It rebuilds the original plate profile with its original through-slots in the isolated Rust worker. [CADRS `cadrs_kernel`](https://github.com/rvdende/cadrs/tree/07e7730daa7a717e22057bd65ea393b10fffbf66/crates/cadrs_kernel) is pinned to revision `07e7730daa7a717e22057bd65ea393b10fffbf66`. It performs solid extrusion, booleans, edge fillets and chamfers, and STEP export. Its tessellation supplies the standard STL viewer. Lengths cross the boundary in millimetres; the kernel uses radians for tessellation settings. The editor does not expose angle inputs.

Supported features are circular through-holes, rectangular through-hole patterns, blind rectangular pockets, and equal-distance chamfers and constant-radius fillets on selectable outside top edges. The worker resolves an edge each time from the plate datum and current dimensions. If an earlier feature removes or splits the edge, select an intact edge or reorder the operations. Arbitrary face or edge picking and intersecting openings are outside the current feature set. The standalone HTML has a **Detailed design demo** with embedded models for the spreadsheet plate, the detailed CADRS result, a refreshed spreadsheet, and a rejected pocket edit. It runs offline and includes the sample CSV, STL and STEP files. Live detailed editing requires the backend worker.

CADRS is by rvdende and contributors under MIT or Apache-2.0. Its license texts are in [the worker's license directory](backend/cadrs-worker/licenses). The repository links to the pinned upstream source through Cargo and does not include a CADRS executable.

To run the mounting-plate acceptance test with CADRS and the Linux FreeCAD Python module installed:

```sh
PYTHONPATH=backend RUN_CADRS_TESTS=1 python -m pytest -q backend/tests/test_detailed_design.py
```

## Demo and video

[Download the standalone HTML](https://raw.githubusercontent.com/muralinamanna/Parametric-Cad-from-Spreadsheet-/feature/solidcraft-fallback/index.html) using the browser’s **Save link as** command, then open the saved file. The root HTML includes the demo, walkthrough video, and sample downloads in one file. You can also open `demo/index.html` alongside its `demo/samples` directory or use **Interactive demo** inside the running full app. If your browser restricts local HTML, run `python -m http.server 8080` in the repository directory and open http://127.0.0.1:8080.

The interactive demo supports parameter edits, CSV upload, and 2D and 3D previews. **View in browser** opens an embedded nominal SolidCraft GLB generated from the 80-slot sample. Its downloadable files and test results are recorded FreeCAD samples. Run the full app for Excel input, custom CAD generation, and live FreeCAD tests. [Walkthrough video](demo/samples/walkthrough.mp4) · [Acceptance log](outputs/acceptance/pegboard_test_log.csv)

## Use the engineering workflow

1. Load `templates/pegboard_parameters.xlsx` or its CSV equivalent. Column A contains exact aliases and column B contains values in millimetres. Excel formula cells require cached numeric values. An import applies a valid set immediately. Edits in the form apply with **Apply parameters**.
2. Inspect the slot positions in **2D Top** or rotate the solid preview in **3D Orbit**. The browser 3D view builds a lightweight visual extrusion from validated coordinates. The actual CAD artifact comes from FreeCAD.
3. Select **Generate CAD model**, then **View in browser** to orbit and zoom the mesh exported by the engine that completed the job. The three-pane review shows the interactive mesh, six orthographic views plus an isometric view, and product dimensions and definitions. The projections use the same exported mesh. The icon toolbar provides standard views, zoom, rotate, pan, fit, and reset. Toggle the model, wireframe, XY grid, or XYZ axes from the display group. Hover over an icon to see its name. Explode is unavailable for the single-solid pegboard. When a 2D drawing is available, the second pane opens the printable SVG offered for download; use **Projected views** to see the seven line views of the mesh. Subsequent generations from the same page reopen the previous native file and edit only the seven parameter cells. Validation failures leave the last successful artifact and preview available. Select **Generate 2D drawing** to produce the drawing sheet and its exports. The vertical tool rail scrolls when needed. In the drawing pane, zoom and turn on pan to inspect details. The GD&T and Tolerances buttons toggle SVG elements explicitly marked `data-annotation="gdt"` or `data-annotation="tolerance"`. The current pegboard drawings do not specify manufacturing tolerances or separate GD&T layers. Preview toggles leave downloaded drawings unchanged.
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
PYTHONPATH=backend RUN_CAD_TESTS=1 RUN_SOLIDCRAFT_TESTS=1 python -m pytest -q backend/tests
```

The environment flags enable real integrations. Set either flag individually to run only the installed engine’s tests. On Windows PowerShell set these variables through `$env:PYTHONPATH="backend"`, `$env:RUN_CAD_TESTS="1"` and `$env:RUN_SOLIDCRAFT_TESTS="1"` as appropriate.

The geometric verifier checks FreeCAD expressions and sketch constraints, feature links, recompute state, validity and bounds of the solid, removed volume, slot loops and locations on both faces, and the measured clearances on all four edges. The acceptance log contains exactly three cases. The separate JSON includes geometry evidence and threshold runs on both axes. The default row boundary is 86 mm and the default column boundary is 48 mm. The actual integration suite also verifies reopening and recomputing from a saved FCStd, invalid edit rejection and export formats.

Included acceptance artifacts were produced by FreeCAD 1.0.0. The case outputs have 1, 80 and 95 through-slots. `outputs/nominal` contains the nominal FCStd, STEP, DXF, SVG, and PDF. `outputs/acceptance` contains the case models and test reports. Subsequent runs are stored under `outputs/jobs`, with a new job ID for each successful operation. The app serves these outputs only through the allowlisted export route.

## Implementation map

- `backend/app/parameters.py` defines the common server-side millimetre model.
- `backend/app/engines.py` selects the CAD adapter, records each attempt and verifies the requested exports.
- `backend/app/solidcraft.py` builds and checks the SolidCraft model and drawing through the version-pinned CLI.
- `backend/app/cad.py` builds and independently verifies FreeCAD features and runs acceptance tests.
- `backend/app/drawing.py` projects the checked solid and builds the native drawing page and exports.
- `backend/app/main.py` handles spreadsheet exchange and transactional worker jobs.
- `frontend/src` contains the React/TypeScript workspace, lightweight 3D preview and standalone demo calculation path.
