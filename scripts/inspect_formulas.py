import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ROOT = Path(__file__).resolve().parent.parent
XLSX = next(ROOT.glob("*.xlsx"))

z = zipfile.ZipFile(XLSX)
ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in ss.findall("m:si", NS)]

for sheet in ["sheet1", "sheet3", "sheet4"]:
    root = ET.fromstring(z.read(f"xl/worksheets/{sheet}.xml"))
    print("=====", sheet)
    for c in root.findall(".//m:c", NS):
        f = c.find("m:f", NS)
        if f is None:
            continue
        v = c.find("m:v", NS)
        print(c.attrib.get("r"), "=", f.text, "->", v.text if v is not None else None)
