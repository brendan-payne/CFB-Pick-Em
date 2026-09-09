"""Dump all sheets from the Core 10 xlsx by name."""
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
rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
rid_to_target = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in ss.findall("m:si", NS)]


def col_row(ref: str):
    col, row = "", ""
    for ch in ref:
        if ch.isalpha():
            col += ch
        else:
            row += ch
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n, int(row)


def load(path: str):
    root = ET.fromstring(z.read("xl/" + path))
    rows = defaultdict(dict)
    for c in root.findall(".//m:c", NS):
        ref = c.attrib.get("r")
        t = c.attrib.get("t")
        v = c.find("m:v", NS)
        if v is None or ref is None:
            continue
        val = v.text
        if t == "s":
            val = strings[int(val)]
        col, row = col_row(ref)
        rows[row][col] = val
    return rows


for s in wb.findall("m:sheets/m:sheet", NS):
    name = s.attrib["name"]
    target = rid_to_target[s.attrib[REL]]
    rows = load(target)
    print(f"\n==== {name} ({target}) rows={len(rows)}")
    for r in sorted(rows):
        cols = rows[r]
        line = " | ".join(str(cols.get(c, "")) for c in range(1, max(cols) + 1))
        print(r, line[:600])
