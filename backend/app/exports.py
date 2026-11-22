"""Conversions shared by both drawing engines."""
import json
import struct
import subprocess
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def convert_svg(folder, extension):
    subprocess.run(
        ["inkscape", str(folder / "pegboard.svg"), f"--export-type={extension}",
         f"--export-filename={folder / ('pegboard.' + extension)}"],
        check=True, capture_output=True, timeout=45,
    )


def write_profile_dxf(path, edges, notes):
    data = [0,"SECTION",2,"HEADER",9,"$ACADVER",1,"AC1015",9,"$INSUNITS",70,4,
            0,"ENDSEC",0,"SECTION",2,"ENTITIES"]
    for (x,y),(xx,yy) in edges:
        data += [0,"LINE",100,"AcDbEntity",8,"CUT_PROFILE",100,"AcDbLine",
                 10,x,20,y,30,0,11,xx,21,yy,31,0]
    for index, sentence in enumerate(notes):
        sentence = sentence.replace("×","x").encode("ascii","replace").decode()
        data += [0,"TEXT",100,"AcDbEntity",8,"ANNOTATIONS",100,"AcDbText",
                 10,0,20,-8-index*6,30,0,40,3,1,sentence,100,"AcDbText"]
    path.write_text("\n".join(map(str,data+[0,"ENDSEC",0,"EOF",""])),encoding="ascii")


def validate_files(folder: Path, names):
    """Reject incomplete or mislabeled outputs before publishing them."""
    for name in names:
        path = folder / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing or empty export: {name}")
        suffix = path.suffix.lower()
        with path.open("rb") as file:
            header = file.read(64)
        if suffix in {".fcstd", ".sc"}:
            member = "Document.xml" if suffix == ".fcstd" else "document.json"
            with ZipFile(path) as archive:
                valid = member in archive.namelist() and archive.getinfo(member).file_size > 0
        elif suffix == ".glb":
            with path.open("rb") as file:
                header = file.read(20)
                if len(header) != 20:
                    raise ValueError(f"Incomplete GLB header: {name}")
                magic, version, length, manifest_size, chunk = struct.unpack("<4sIII4s", header)
                if (magic, version, length, chunk) != (b"glTF", 2, path.stat().st_size, b"JSON") or not 0 < manifest_size <= length - 20:
                    raise ValueError(f"Invalid GLB header: {name}")
                manifest = json.loads(file.read(manifest_size))
                valid = bool(manifest.get("meshes") and manifest.get("scenes"))
        elif suffix == ".stl":
            data = path.read_bytes()
            count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
            valid = (count > 0 and len(data) == 84 + 50 * count) or (
                data.startswith(b"solid") and b"facet normal" in data and
                data.rstrip().splitlines()[-1].startswith(b"endsolid"))
        elif suffix == ".svg":
            valid = ElementTree.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg"
        elif suffix == ".dxf":
            data = path.read_bytes()
            valid = b"$INSUNITS\n70\n4" in data.replace(b"\r\n", b"\n") and data.rstrip().endswith(b"EOF")
        else:
            signature = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n",
                         ".step": b"ISO-10303-21;"}.get(suffix)
            valid = signature is None or header.startswith(signature)
        if not valid:
            raise ValueError(f"Invalid export format: {name}")
