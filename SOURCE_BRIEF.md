# Build a Spreadsheet-to-Drawing Parametric CAD Application

## Role

Act as a senior Python developer, FreeCAD automation engineer, parametric CAD specialist, and full-stack application architect.

Develop a complete, working, locally executable application named "Spreadsheet to Drawing".

The application must convert spreadsheet-driven dimensional parameters into editable FreeCAD 3D models, automatically generated 2D technical drawings, CAD exports, and engineering validation reports.

Use Python, FreeCAD, and a suitable web-based interface.

Claude is an optional design and requirements assistant. Codex is responsible for implementing, executing, testing, and documenting the application.

## 1. Main objective

Create a spreadsheet-driven parametric pegboard with rectangular, vertically oriented through-slots.

The user must be able to:

1. Enter board dimensions and slot parameters.
2. Upload an Excel or CSV parameter file.
3. Edit the parameters through a graphical interface.
4. Generate a FreeCAD model.
5. Automatically create slot rows and columns.
6. Regenerate geometry when spreadsheet values change.
7. View the model in 2D and 3D.
8. Generate dimensioned manufacturing drawings.
9. Export FCStd, STEP, DXF, SVG, and PDF files.
10. Run engineering validation tests.
11. Download a three-row test log.

Do not create a static drawing generator. Build a genuine parametric CAD workflow with retained spreadsheet dependencies.

## 2. Technology stack

Backend:
- Python 3.11 or a version supported by the installed FreeCAD release.
- FreeCAD Python API.
- FastAPI.
- Pydantic for parameter validation.
- openpyxl for Excel files.
- CSV for portable parameter exchange.
- pytest for non-CAD unit tests.

Frontend:
- React with TypeScript and Vite.
- A clean engineering dashboard.
- Spreadsheet-style parameter editing.
- SVG-based 2D previews.
- Three.js or another appropriate library for optional interactive 3D previews.

CAD features:
- FreeCAD Spreadsheet Workbench.
- Part Design or an appropriate robust FreeCAD feature-based workflow.
- Sketcher for the master slot profile.
- TechDraw for engineering drawings.
- Native FreeCAD document saving.

Run FreeCAD code in a compatible FreeCAD Python environment or through FreeCAD's executable.

Do not assume the system Python interpreter directly supports importing FreeCAD.

Detect FreeCAD's installation and version. Explain platform-specific setup requirements.

## 3. Parameter spreadsheet

Create a FreeCAD spreadsheet object named Parameters.

Create stable spreadsheet aliases for:

- boardWidth
- boardHeight
- boardThickness
- edgeMargin
- slotWidth
- slotLength
- slotSpacing
- minBoardWidth
- minBoardHeight

Default values in millimeters:

boardWidth = 300
boardHeight = 200
boardThickness = 6
edgeMargin = 12
slotWidth = 6
slotLength = 25
slotSpacing = 12

Derive the minimum valid board dimensions:

minBoardWidth = 2 * edgeMargin + slotWidth
minBoardHeight = 2 * edgeMargin + slotLength

The spreadsheet must also include calculated values:

- pitchX
- pitchY
- availableWidth
- availableHeight
- columnCount
- rowCount
- totalSlots
- rightClearance
- topClearance

Use millimeter-aware spreadsheet values and valid FreeCAD expressions.

Do not hardcode calculated slot counts.

## 4. Parametric geometry

Create a rectangular pegboard located in the XY plane.

Board origin:
X = 0
Y = 0
Z = 0

Board dimensions:
X direction = boardWidth
Y direction = boardHeight
Z direction = boardThickness

Create one rectangular master slot.

Slot dimensions:
X direction = slotWidth
Y direction = slotLength

Master slot bottom-left position:
X = edgeMargin
Y = edgeMargin

Use a master sketch named MasterSlot.

Fully constrain the slot sketch using appropriate dimensional and positional constraints.

Drive the slot geometry through expressions referencing the Parameters spreadsheet aliases.

Create a through-all cut using the slot sketch.

Pattern the cut across the board in rows and columns.

Prefer native parametric FreeCAD pattern features if they remain stable when occurrence counts change. Otherwise, implement a dedicated parametric pattern object whose dimensions, placement, and counts are derived directly from the spreadsheet.

Avoid references to unstable generated edges and faces.

## 5. Automatic slot pattern calculation

Define slotSpacing as the minimum material gap between neighboring slot bounding boxes.

Use:

pitchX = slotWidth + slotSpacing
pitchY = slotLength + slotSpacing

Compute:

availableWidth = boardWidth - 2 * edgeMargin

availableHeight = boardHeight - 2 * edgeMargin

columnCount = floor((availableWidth - slotWidth) / pitchX) + 1

rowCount = floor((availableHeight - slotLength) / pitchY) + 1

totalSlots = rowCount * columnCount

Use these equations only after confirming valid dimensions and pitches.

Position each slot using zero-based column and row indices:

x = edgeMargin + columnIndex * pitchX

y = edgeMargin + rowIndex * pitchY

Maintain slot geometry and boundary clearances when occurrence counts increase or decrease.

Do not silently clamp invalid boards to the minimum size.

## 6. Critical behavior when board dimensions change

Implement automatic regeneration when users edit boardWidth or boardHeight.

If boardWidth increases enough to fit another column with the defined spacing, add a column automatically.

If boardWidth decreases below an occurrence threshold, remove the corresponding column.

Apply the same behavior to boardHeight for slot rows.

The pattern must change discretely when the available span crosses an exact pitch threshold.

For the nth column to fit, the required board width is:

2 * edgeMargin + slotWidth + (n - 1) * pitchX

For the nth row to fit, the required board height is:

2 * edgeMargin + slotLength + (n - 1) * pitchY

Implement these thresholds consistently, including exact equality and floating-point tolerance handling.

Display an explanation in the UI describing why a row or column was added or removed.

No geometry editing should be required after spreadsheet modifications.

## 7. Minimum-size validation

Reject parameters when:

- boardWidth is smaller than minBoardWidth.
- boardHeight is smaller than minBoardHeight.
- boardThickness is not positive.
- slotWidth is not positive.
- slotLength is not positive.
- slotSpacing is negative.
- edgeMargin is negative.
- a parameter is NaN or infinite.
- the pattern produces invalid or out-of-bounds geometry.

Return a clear validation message.

When a parameter change is invalid, preserve the last valid model.

Do not export invalid geometry.

The application should support a minimum valid board with one slot.

## 8. Drawing generation

Automatically create dimensioned 2D engineering drawings from the CAD geometry.

Required views:

- Top view.
- Front view.
- Right-side view.
- Isometric view.

Include:

- Overall board width.
- Overall board height.
- Thickness.
- Slot width.
- Slot length.
- Edge margin.
- Horizontal slot pitch.
- Vertical slot pitch.
- Number of slot rows.
- Number of slot columns.
- Total number of slots.

Use readable dimension placement.

Generate a drawing title block with:

- Drawing title.
- Part number.
- Revision.
- Units.
- Date.
- Scale.
- Material field.
- Generated-by field.

Use TechDraw for FreeCAD-generated drawings.

For patterned features, use clear manufacturing notation such as slot dimensions, quantities, and equal-spacing notes. Avoid unnecessary overlapping individual slot dimensions.

Support PDF, SVG, and DXF output.

If a selected format requires a separate export implementation, preserve dimensions and document any format limitations.

## 9. User interface

Create an engineering dashboard with four primary sections.

Section A: Parameters

Display editable parameter fields with units, descriptions, and validation.

Provide buttons:

- Load Spreadsheet
- Download Template
- Apply Parameters
- Reset Defaults

Section B: Preview

Display:

- Top-view pegboard layout.
- Optional interactive 3D model.
- Live dimension annotations.
- Slot positions.
- Board outline.

Section C: Calculations

Display:

- Rows.
- Columns.
- Total slots.
- Horizontal pitch.
- Vertical pitch.
- Right-edge clearance.
- Top-edge clearance.
- Model validity.
- Recompute status.

Section D: Drawings and Exports

Provide actions:

- Generate CAD Model
- Generate 2D Drawing
- Run Three-Case Tests
- Export FCStd
- Export STEP
- Export DXF
- Export SVG
- Export PDF
- Download Test Log

Show meaningful progress and error states.

Ensure the preview and generated FreeCAD geometry use the same validated parameter and placement logic.

## 10. Three-case engineering test

Automatically recompute and validate three board configurations.

Test 1: Smallest valid board

boardWidth = 30 mm
boardHeight = 49 mm

Expected:
- 1 column.
- 1 row.
- 1 slot.

Test 2: Nominal board

boardWidth = 300 mm
boardHeight = 200 mm

Expected:
- 16 columns.
- 5 rows.
- 80 slots.

Test 3: Wider board

boardWidth = 360 mm
boardHeight = 200 mm

Expected:
- 19 columns.
- 5 rows.
- 95 slots.

For each case:

1. Edit only the spreadsheet parameter cells.
2. Trigger FreeCAD document recomputation.
3. Verify all spreadsheet expressions.
4. Verify sketch constraints.
5. Verify the feature history.
6. Verify the final geometry.
7. Verify actual slot count.
8. Verify all slot coordinates.
9. Measure all four outer edge clearances.
10. Check for broken references.
11. Check for invalid or null shapes.
12. Save the case.
13. Record the result.

Do not manually recreate the model between test cases.

Verify actual geometry rather than relying only on expected spreadsheet formulas.

Where a single parametric feature contains many cutouts, inspect the final shape or an equivalent independent geometric representation to confirm the number and positions of through-slots.

## 11. Additional row-transition tests

Test behavior when the board height crosses a row-count threshold.

For the default slot parameters:

- A board height of 85.999 mm should fit one row.
- A board height of 86 mm should fit two rows.
- A board height of 86.001 mm should also fit two rows.

Use appropriate numerical tolerances and dimensional precision.

Verify that:

- A row is added at the threshold.
- A row is removed below the threshold.
- The model remains valid.
- Slot widths and lengths do not change.
- Required edge clearance is preserved.
- No broken feature references occur.

Include analogous column-transition tests and invalid-input tests.

These additional tests should appear in the automated test suite, separate from the mandatory three-row acceptance log.

## 12. Edge-clearance verification

For every generated slot, compute:

left = slotX
right = boardWidth - (slotX + slotWidth)
bottom = slotY
top = boardHeight - (slotY + slotLength)

Verify:

left >= edgeMargin

right >= edgeMargin

bottom >= edgeMargin

top >= edgeMargin

Use an explicitly documented numerical tolerance appropriate for millimeter CAD geometry.

Calculate the minimum actual clearance.

Return a failure if any slot violates the requirement beyond that tolerance.

## 13. Test log

Generate a file named:

pegboard_test_log.csv

It must contain exactly three data rows for the required acceptance cases.

Required columns:

- Test Case
- Board Width
- Board Height
- Board Thickness
- Expected Rows
- Actual Rows
- Expected Columns
- Actual Columns
- Expected Slots
- Actual Slots
- Minimum Edge Clearance
- Shape Valid
- Broken References
- Recompute Successful
- Result

Use PASS or FAIL based on actual test results.

Never report PASS for a test that did not run.

Generate a separate detailed JSON test report containing any relevant errors and evidence.

## 14. Project organization

Use this proposed folder structure:

spreadsheet-to-drawing/
  backend/
    app/
      main.py
      api/
      schemas/
      services/
        spreadsheet_service.py
        parameter_service.py
        cad_service.py
        pattern_service.py
        drawing_service.py
        export_service.py
        validation_service.py
      freecad/
        build_model.py
        recompute_model.py
        generate_drawing.py
        validate_geometry.py
    tests/
      test_parameters.py
      test_pattern_math.py
      test_row_transitions.py
      test_geometry.py
      test_exports.py
    requirements.txt
  frontend/
    src/
      components/
      pages/
      services/
      types/
    package.json
  templates/
    pegboard_parameters.xlsx
  outputs/
  scripts/
  README.md

Adjust the structure only for clear implementation reasons.

## 15. API requirements

Implement endpoints equivalent to:

GET /api/health

GET /api/parameters/defaults

POST /api/parameters/validate

POST /api/spreadsheet/upload

POST /api/model/generate

POST /api/model/recompute

GET /api/model/preview

POST /api/drawing/generate

POST /api/tests/run

GET /api/exports/{file_id}

Use defined request and response schemas.

Ensure file handling is safe and exports are restricted to the designated output directory.

## 16. Reliability requirements

The application must:

- Preserve the parametric model.
- Preserve spreadsheet aliases.
- Rebuild after spreadsheet-only edits.
- Handle varying row and column counts.
- Avoid unstable references where practical.
- Reject invalid input.
- Prevent incomplete files being reported as successful exports.
- Produce reproducible slot positions.
- Report FreeCAD recomputation errors.
- Save editable native FreeCAD files.
- Recover cleanly from a failed recomputation.

Use a temporary working document or equivalent transaction approach so failed builds do not overwrite a valid model.

## 17. Deliverables

Produce:

1. Complete application source code.
2. Working backend API.
3. Working frontend.
4. Sample Excel input template.
5. Native parametric FreeCAD file.
6. Three recomputed FreeCAD test models.
7. Generated technical drawing PDF.
8. Generated DXF and SVG drawings.
9. STEP export.
10. Three-row CSV test log.
11. Detailed JSON validation report.
12. README with installation, execution, usage, and testing instructions.

## 18. Definition of done

The application is complete only when:

- Spreadsheet parameters control the board and slot geometry.
- One master slot drives the repeating pattern.
- Rows and columns update automatically.
- A minimum valid board is enforced.
- All three mandatory board configurations rebuild from spreadsheet edits alone.
- Slot counts match independent geometric verification.
- Every slot satisfies the required edge clearance.
- No broken references remain.
- Drawings correspond to the final CAD geometry.
- Files are saved successfully.
- All three mandatory test cases pass.

Do not fabricate test evidence or claim success without execution.

If FreeCAD is unavailable in the development environment, still implement the complete application, run the independent Python tests, and clearly identify the CAD integration tests requiring execution in FreeCAD.

## 19. Implementation workflow

Implement in this sequence:

Phase 1: Inspect the repository and environment. Detect installed dependencies and FreeCAD capabilities.

Phase 2: Build the parameter data model and independent pattern mathematics.

Phase 3: Create the FreeCAD spreadsheet, master sketch, board solid, and slot pattern.

Phase 4: Build the recompute and validation engine.

Phase 5: Implement technical drawing generation and exports.

Phase 6: Implement the frontend and backend integration.

Phase 7: Implement all unit, integration, transition, and acceptance tests.

Phase 8: Execute available tests, produce deliverables, and report actual results.

Prioritize a working end-to-end application over mock interfaces.

Make reasonable implementation decisions without requesting confirmation for every detail.

Start by inspecting the current development environment, then create the project and implement the application.
