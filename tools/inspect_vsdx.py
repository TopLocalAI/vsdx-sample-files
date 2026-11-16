#!/usr/bin/env python3
"""Inspect the internal structure of Microsoft Visio .vsdx files.

Uses only the Python standard library (zipfile + xml.etree.ElementTree) to list:
  - pages and their XML part paths
  - 2D shape count and 1D connector count per page (and document totals)
  - all text labels extracted from shapes and connectors
  - masters defined in the package and masters referenced on each page

Usage:
  python3 tools/inspect_vsdx.py samples/01-basic-flowchart.vsdx
  python3 tools/inspect_vsdx.py --json samples/*.vsdx
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def local_name(tag: str) -> str:
    """Strip XML namespace URI from an ElementTree tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def resolve_part_path(base_part: str, target: str) -> str:
    """Resolve an OPC relationship Target relative to its source part."""
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = posixpath.dirname(base_part)
    return posixpath.normpath(posixpath.join(base_dir, target))


def rels_path_for(part_path: str) -> str:
    """Return the OPC _rels path corresponding to a package part."""
    folder, filename = posixpath.split(part_path)
    if folder:
        return f"{folder}/_rels/{filename}.rels"
    return f"_rels/{filename}.rels"


def parse_relationships(zf: zipfile.ZipFile, part_path: str) -> dict[str, dict[str, str]]:
    """Parse the .rels file for part_path into {rId: {'target': ..., 'type': ...}}."""
    rels_file = rels_path_for(part_path)
    if rels_file not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_file))
    mapping: dict[str, dict[str, str]] = {}
    for elem in root:
        if local_name(elem.tag) != "Relationship":
            continue
        rid = elem.attrib.get("Id", "")
        target = elem.attrib.get("Target", "")
        rel_type = elem.attrib.get("Type", "")
        if rid and target:
            mapping[rid] = {
                "target": resolve_part_path(part_path, target),
                "type": rel_type,
            }
    return mapping


def parse_masters(zf: zipfile.ZipFile, masters_part: str) -> dict[str, dict[str, str]]:
    """Return {master_id: {'id': ..., 'name': ..., 'name_u': ...}} from masters.xml."""
    if masters_part not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(masters_part))
    masters: dict[str, dict[str, str]] = {}
    for elem in root:
        if local_name(elem.tag) != "Master":
            continue
        mid = elem.attrib.get("ID", "")
        name_u = elem.attrib.get("NameU") or elem.attrib.get("Name") or f"Master.{mid}"
        name = elem.attrib.get("Name") or name_u
        if mid:
            masters[mid] = {"id": mid, "name": name, "name_u": name_u}
    return masters


def iter_shapes(shapes_container: ET.Element) -> list[ET.Element]:
    """Recursively collect all <Shape> elements inside a <Shapes> container."""
    result: list[ET.Element] = []
    for child in shapes_container:
        if local_name(child.tag) == "Shape":
            result.append(child)
            for sub in child:
                if local_name(sub.tag) == "Shapes":
                    result.extend(iter_shapes(sub))
    return result


def extract_shape_cells(shape_elem: ET.Element) -> dict[str, str]:
    """Read direct <Cell N='...' V='...'/> entries on a <Shape>."""
    cells: dict[str, str] = {}
    for child in shape_elem:
        if local_name(child.tag) == "Cell":
            cell_name = child.attrib.get("N")
            if cell_name:
                cells[cell_name] = child.attrib.get("V", "")
    return cells


def extract_shape_text(shape_elem: ET.Element) -> str:
    """Extract human-readable text from a <Shape>'s <Text> child."""
    for child in shape_elem:
        if local_name(child.tag) == "Text":
            raw = "".join(child.itertext())
            lines = [line.strip() for line in raw.splitlines()]
            cleaned = "\n".join(line for line in lines if line)
            return cleaned.strip()
    return ""


def is_connector_shape(
    shape_elem: ET.Element,
    cells: dict[str, str],
    from_sheets: set[str],
    masters: dict[str, dict[str, str]],
) -> bool:
    """Determine whether a <Shape> is a 1D connector rather than a 2D shape."""
    shape_id = shape_elem.attrib.get("ID", "")
    if "BeginX" in cells or "EndX" in cells:
        return True
    if cells.get("ObjType") == "2":
        return True
    if shape_id and shape_id in from_sheets:
        return True
    name_u = (shape_elem.attrib.get("NameU") or shape_elem.attrib.get("Name") or "").lower()
    if "connector" in name_u:
        return True
    master_id = shape_elem.attrib.get("Master", "")
    if master_id and master_id in masters:
        master_name = masters[master_id]["name_u"].lower()
        if "connector" in master_name:
            return True
    return False


def inspect_page(
    zf: zipfile.ZipFile,
    page_index: int,
    page_elem: ET.Element,
    page_rels: dict[str, dict[str, str]],
    masters: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Inspect a single Visio page and its XML contents."""
    page_id = page_elem.attrib.get("ID", str(page_index - 1))
    page_name = page_elem.attrib.get("Name") or page_elem.attrib.get("NameU") or f"Page-{page_index}"
    page_name_u = page_elem.attrib.get("NameU") or page_name

    part_path = f"visio/pages/page{page_index}.xml"
    for child in page_elem:
        if local_name(child.tag) == "Rel":
            rid = child.attrib.get(OFFICE_REL_ATTR) or child.attrib.get("id") or ""
            if rid in page_rels:
                part_path = page_rels[rid]["target"]

    if part_path not in zf.namelist():
        return {
            "index": page_index,
            "id": page_id,
            "name": page_name,
            "name_u": page_name_u,
            "part": part_path,
            "shapes": 0,
            "connectors": 0,
            "glued_endpoints": 0,
            "embedded_media": 0,
            "masters_used": [],
            "texts": [],
        }

    root = ET.fromstring(zf.read(part_path))

    from_sheets: set[str] = set()
    glued_endpoints = 0
    for child in root:
        if local_name(child.tag) == "Connects":
            for conn in child:
                if local_name(conn.tag) == "Connect":
                    glued_endpoints += 1
                    fs = conn.attrib.get("FromSheet")
                    if fs:
                        from_sheets.add(fs)

    all_shapes: list[ET.Element] = []
    for child in root:
        if local_name(child.tag) == "Shapes":
            all_shapes.extend(iter_shapes(child))

    shape_count = 0
    connector_count = 0
    embedded_media = 0
    texts: list[str] = []
    master_usage_counts: dict[str, int] = {}

    for shape_elem in all_shapes:
        cells = extract_shape_cells(shape_elem)
        if is_connector_shape(shape_elem, cells, from_sheets, masters):
            connector_count += 1
        else:
            shape_count += 1

        for sub in shape_elem:
            if local_name(sub.tag) == "ForeignData":
                embedded_media += 1

        master_id = shape_elem.attrib.get("Master")
        if master_id:
            master_usage_counts[master_id] = master_usage_counts.get(master_id, 0) + 1

        text_val = extract_shape_text(shape_elem)
        if text_val:
            texts.append(text_val)

    masters_used = []
    for mid, count in sorted(master_usage_counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
        info = masters.get(mid, {"id": mid, "name": f"Master.{mid}", "name_u": f"Master.{mid}"})
        masters_used.append(
            {
                "id": mid,
                "name": info["name"],
                "name_u": info["name_u"],
                "count": count,
            }
        )

    return {
        "index": page_index,
        "id": page_id,
        "name": page_name,
        "name_u": page_name_u,
        "part": part_path,
        "shapes": shape_count,
        "connectors": connector_count,
        "glued_endpoints": glued_endpoints,
        "embedded_media": embedded_media,
        "masters_used": masters_used,
        "texts": texts,
    }


def inspect_vsdx(path: Path) -> dict[str, Any]:
    """Inspect a .vsdx file and return a structured summary dictionary."""
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    header = path.read_bytes()[:8]
    if header == OLE2_MAGIC:
        raise ValueError(
            f"{path} is a legacy binary Visio (.vsd) Compound File (OLE2), not an Open Packaging (.vsdx) ZIP archive."
        )

    if not zipfile.is_zipfile(path):
        raise ValueError(f"{path} is not a valid ZIP / .vsdx archive.")

    with zipfile.ZipFile(path, "r") as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]

        # Locate main document via root _rels/.rels if present
        doc_part = "visio/document.xml"
        if "_rels/.rels" in zf.namelist():
            root_rels = ET.fromstring(zf.read("_rels/.rels"))
            for rel in root_rels:
                if local_name(rel.tag) == "Relationship" and rel.attrib.get("Type", "").endswith("/document"):
                    target = rel.attrib.get("Target", "")
                    if target:
                        doc_part = target.lstrip("/")

        doc_rels = parse_relationships(zf, doc_part)
        pages_part = "visio/pages/pages.xml"
        masters_part = "visio/masters/masters.xml"
        for rel in doc_rels.values():
            if rel["type"].endswith("/pages"):
                pages_part = rel["target"]
            elif rel["type"].endswith("/masters"):
                masters_part = rel["target"]

        masters = parse_masters(zf, masters_part)
        page_rels = parse_relationships(zf, pages_part)

        pages_summary: list[dict[str, Any]] = []
        if pages_part in zf.namelist():
            pages_root = ET.fromstring(zf.read(pages_part))
            page_elems = [el for el in pages_root if local_name(el.tag) == "Page"]
            for idx, page_elem in enumerate(page_elems, start=1):
                pages_summary.append(inspect_page(zf, idx, page_elem, page_rels, masters))

        total_shapes = sum(p["shapes"] for p in pages_summary)
        total_connectors = sum(p["connectors"] for p in pages_summary)
        all_texts = [t for p in pages_summary for t in p["texts"]]

        agg_masters: dict[str, dict[str, Any]] = {}
        for p in pages_summary:
            for m in p["masters_used"]:
                mid = m["id"]
                if mid not in agg_masters:
                    agg_masters[mid] = {
                        "id": mid,
                        "name": m["name"],
                        "name_u": m["name_u"],
                        "count": 0,
                    }
                agg_masters[mid]["count"] += m["count"]

        media_parts = sorted(n for n in names if n.startswith("visio/media/"))

        return {
            "file": str(path),
            "package_parts_count": len(names),
            "media_parts": media_parts,
            "page_count": len(pages_summary),
            "total_shapes": total_shapes,
            "total_connectors": total_connectors,
            "masters_defined": list(masters.values()),
            "masters_used": list(agg_masters.values()),
            "all_texts": all_texts,
            "pages": pages_summary,
        }


def format_human(report: dict[str, Any]) -> str:
    """Format an inspection dictionary for readable terminal output."""
    lines: list[str] = []
    lines.append(f"File: {report['file']}")
    lines.append(
        f"Summary: {report['page_count']} page(s), "
        f"{report['total_shapes']} shape(s), "
        f"{report['total_connectors']} connector(s), "
        f"{report['package_parts_count']} OPC part(s)"
    )

    if report["masters_defined"]:
        defined_str = ", ".join(
            f"{m['name']} (ID={m['id']})" for m in report["masters_defined"]
        )
        lines.append(f"Masters defined: {defined_str}")
    else:
        lines.append("Masters defined: (none)")

    if report["masters_used"]:
        used_str = ", ".join(
            f"{m['name']} (ID={m['id']}, x{m['count']})" for m in report["masters_used"]
        )
        lines.append(f"Masters used:    {used_str}")
    else:
        lines.append("Masters used:    (none)")

    if report["media_parts"]:
        lines.append(f"Embedded media:  {', '.join(report['media_parts'])}")

    for page in report["pages"]:
        lines.append(
            f"  [Page {page['index']}] {page['name']} ({page['part']}): "
            f"{page['shapes']} shapes, {page['connectors']} connectors "
            f"({page['glued_endpoints']} glued endpoints)"
        )
        if page["masters_used"]:
            pm = ", ".join(f"{m['name']} x{m['count']}" for m in page["masters_used"])
            lines.append(f"    Masters: {pm}")
        else:
            lines.append("    Masters: (none)")

        if page["texts"]:
            preview_texts = [t.replace("\n", " / ") for t in page["texts"]]
            lines.append(f"    Texts ({len(preview_texts)}): " + " | ".join(preview_texts))
        else:
            lines.append("    Texts (0): (none)")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect pages, shapes, connectors, text labels, and masters inside .vsdx files."
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="One or more .vsdx files to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output inspection results as JSON",
    )
    args = parser.parse_args(argv)

    reports: list[dict[str, Any]] = []
    try:
        for file_path in args.files:
            reports.append(inspect_vsdx(file_path))
    except (FileNotFoundError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        payload: Any = reports[0] if len(reports) == 1 else reports
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(format_human(r) for r in reports))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
