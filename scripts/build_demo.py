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
index.write_text(source, encoding="utf-8")
