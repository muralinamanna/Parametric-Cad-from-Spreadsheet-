"""Shared CAD acceptance cases and CSV schema."""

CASES = [("Smallest valid board",30,49,1,1), ("Nominal board",300,200,5,16), ("Wider board",360,200,5,19)]
HEADERS = ["Test Case","Board Width","Board Height","Board Thickness","Expected Rows","Actual Rows",
           "Expected Columns","Actual Columns","Expected Slots","Actual Slots","Minimum Edge Clearance",
           "Shape Valid","Broken References","Recompute Successful","Result"]
