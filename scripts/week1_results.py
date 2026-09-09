"""Print Week 1 Results row column-by-column."""
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
ROOT = Path(__file__).resolve().parent.parent
XLSX = next(ROOT.glob("*.xlsx"))
z = zipfile.ZipFile(XLSX)
wb = ET.fromstring(z.read("xl/workbook.xml"))
rels = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in ss.findall("m:si", NS)]

def col_row(ref):
    col, row = "", ""
    for ch in ref:
        if ch.isalpha(): col += ch
        else: row += ch
    n = 0
    for ch in col: n = n * 26 + (ord(ch) - 64)
    return n, int(row)

target = None
for s in wb.findall("m:sheets/m:sheet", NS):
    if s.attrib["name"] == "Week 1":
        target = rels[s.attrib[REL]]
        break
root = ET.fromstring(z.read("xl/" + target))
rows = defaultdict(dict)
for c in root.findall(".//m:c", NS):
    ref = c.attrib.get("r"); t = c.attrib.get("t"); v = c.find("m:v", NS)
    if v is None or ref is None: continue
    val = strings[int(v.text)] if t == "s" else v.text
    col, row = col_row(ref)
    rows[row][col] = val
headers = rows[1]
print("HEADERS:")
for c in sorted(headers):
    print(f"  col {c}: {headers[c]!r}")
print("RESULTS row:")
for c in sorted(rows[14]):
    print(f"  col {c}: {rows[14][c]!r}")
