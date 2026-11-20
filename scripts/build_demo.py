"""Build the demo HTML and the portable single-file repository entry."""
import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
demo = root / "demo"
npm = shutil.which("npm")
if not npm:
    raise SystemExit("Install Node.js and npm to build the demo.")
subprocess.run([npm, "exec", "--", "vite", "build", "--mode", "standalone",
                "--outDir", str(demo), "--emptyOutDir"], cwd=root/"frontend", check=True)
index = demo / "index.html"
source = index.read_text(encoding="utf-8")

def asset(match):
    return (demo / match.group(1)).read_text(encoding="utf-8")

source, scripts = re.subn(r'<script type="module" crossorigin src="\./([^"]+)"></script>',
    lambda match: '<script type="module">' + asset(match).replace("</script", r"<\/script") + "</script>", source)
source, styles = re.subn(r'<link rel="stylesheet" crossorigin href="\./([^"]+)">',
    lambda match: "<style>" + asset(match) + "</style>", source)
if scripts != 1 or styles != 1:
    raise RuntimeError("Standalone HTML is missing the inlined application assets.")

mime_types = {
    ".csv": "text/csv", ".dxf": "application/dxf", ".fcstd": "application/octet-stream",
    ".json": "application/json", ".mp4": "video/mp4", ".pdf": "application/pdf",
    ".step": "application/step", ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
samples = {
    path.name: [mime_types[path.suffix.lower()], base64.b64encode(path.read_bytes()).decode("ascii")]
    for path in sorted((demo / "samples").iterdir())
    if path.is_file() and path.suffix.lower() in mime_types
}
portable = source.replace("</body>", '<script type="application/json" id="embedded-samples">'
                          + json.dumps(samples, separators=(",", ":")) + "</script></body>", 1)
if portable == source:
    raise RuntimeError("Standalone HTML has no closing body tag for the embedded files.")
index.write_text(source, encoding="utf-8")
(root / "index.html").write_text(portable, encoding="utf-8")
shutil.rmtree(demo / "assets")
