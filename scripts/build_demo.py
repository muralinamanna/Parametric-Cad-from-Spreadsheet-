"""Build the standalone browser demo, inlining code for file:// usage."""
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
demo = root / "demo"
subprocess.run(["npx", "vite", "build", "--mode", "standalone", "--outDir", str(demo), "--emptyOutDir"],
               cwd=root/"frontend", check=True, shell=False)
index = demo / "index.html"
source = index.read_text(encoding="utf-8")

def asset(match):
    return (demo / match.group(1)).read_text(encoding="utf-8")

source = re.sub(r'<script type="module" crossorigin src="\./([^"]+)"></script>',
                lambda m: '<script type="module">' + asset(m).replace("</script", r"<\/script") + "</script>", source)
source = re.sub(r'<link rel="stylesheet" crossorigin href="\./([^"]+)">',
                lambda m: "<style>" + asset(m) + "</style>", source)
if '<script type="module">' not in source or "<style>" not in source:
    raise RuntimeError("Standalone HTML is missing the inlined application assets.")

index.write_text(source, encoding="utf-8")
# The repository entry uses the same app and the samples installed beside the demo.
(root / "index.html").write_text(
    source.replace('<html lang="en">', '<html lang="en" data-sample-path="./demo/samples/">', 1),
    encoding="utf-8",
)
