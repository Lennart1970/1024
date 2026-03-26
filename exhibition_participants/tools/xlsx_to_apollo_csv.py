from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}

DEFAULT_OUTPUT_COLUMNS = [
    "Company",
    "Company Domain",
    "Website",
    "LinkedIn",
    "City",
    "Country",
    "Industry",
    "Employees",
    "Source File",
]

HEADER_ALIASES = {
    "company": [
        "company",
        "company name",
        "name",
        "account name",
        "organization",
        "organisation",
        "business name",
    ],
    "website": [
        "website",
        "url",
        "company url",
        "company website",
        "domain",
        "web",
        "site",
    ],
    "linkedin": [
        "linkedin",
        "linkedin url",
        "company linkedin",
        "linkedin company",
    ],
    "city": ["city", "town"],
    "country": ["country", "country code", "nation"],
    "industry": ["industry", "branch", "sector", "vertical"],
    "employees": ["employees", "employee count", "headcount", "staff"],
}


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


class XlsxReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_sheet(self, preferred_sheet: str | None = None) -> list[list[str]]:
        with zipfile.ZipFile(self.path) as archive:
            shared_strings = self._read_shared_strings(archive)
            sheet_path, sheet_name = self._resolve_sheet_path(archive, preferred_sheet)
            xml_root = ET.fromstring(archive.read(sheet_path))
            rows = []
            for row in xml_root.findall(".//a:sheetData/a:row", NS):
                parsed = self._parse_row(row, shared_strings)
                if any(cell.strip() for cell in parsed):
                    rows.append(parsed)
            if not rows:
                raise ValueError(f"Sheet '{sheet_name}' in {self.path.name} is empty")
            return rows

    def _read_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        values: list[str] = []
        for item in root.findall(".//a:si", NS):
            values.append("".join(item.itertext()).strip())
        return values

    def _resolve_sheet_path(self, archive: zipfile.ZipFile, preferred_sheet: str | None) -> tuple[str, str]:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall(".//p:Relationship", NS)
        }
        sheets = workbook.findall(".//a:sheets/a:sheet", NS)
        if not sheets:
            raise ValueError(f"No sheets found in {self.path.name}")

        selected = None
        if preferred_sheet:
            for sheet in sheets:
                if sheet.attrib.get("name", "").lower() == preferred_sheet.lower():
                    selected = sheet
                    break
            if selected is None:
                available = ", ".join(sheet.attrib.get("name", "") for sheet in sheets)
                raise ValueError(f"Sheet '{preferred_sheet}' not found. Available sheets: {available}")
        else:
            selected = sheets[0]

        rel_id = selected.attrib[f"{{{REL_NS}}}id"]
        target = rel_map[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        return target, selected.attrib.get("name", "Sheet1")

    def _parse_row(self, row: ET.Element, shared_strings: list[str]) -> list[str]:
        values_by_index: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("a:c", NS):
            ref = cell.attrib.get("r", "")
            index = self._column_index_from_ref(ref)
            max_index = max(max_index, index)
            values_by_index[index] = self._cell_value(cell, shared_strings)
        if max_index < 0:
            return []
        return [values_by_index.get(idx, "") for idx in range(max_index + 1)]

    def _cell_value(self, cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            is_node = cell.find("a:is", NS)
            return "".join(is_node.itertext()).strip() if is_node is not None else ""
        value_node = cell.find("a:v", NS)
        if value_node is None or value_node.text is None:
            return ""
        value = value_node.text.strip()
        if cell_type == "s":
            try:
                return shared_strings[int(value)]
            except (ValueError, IndexError):
                return value
        return value

    def _column_index_from_ref(self, ref: str) -> int:
        letters = "".join(ch for ch in ref if ch.isalpha())
        index = 0
        for char in letters:
            index = index * 26 + (ord(char.upper()) - 64)
        return max(index - 1, 0)


class CsvReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_sheet(self, preferred_sheet: str | None = None) -> list[list[str]]:
        del preferred_sheet
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [list(row) for row in csv.reader(handle) if any((cell or "").strip() for cell in row)]


class ApolloConverter:
    def __init__(self, source_path: Path, rows: list[list[str]]) -> None:
        self.source_path = source_path
        self.rows = rows

    def convert(self) -> list[dict[str, str]]:
        if not self.rows:
            return []
        headers = self.rows[0]
        body = self.rows[1:]
        mapping = self._build_mapping(headers)
        if mapping["company"] is None:
            raise ValueError("Could not find a company-name column")

        converted = []
        for raw_row in body:
            row = self._row_dict(headers, raw_row)
            company = row.get(headers[mapping["company"]], "").strip()
            if not company:
                continue
            website = self._pick_value(row, headers, mapping["website"])
            linkedin = self._pick_value(row, headers, mapping["linkedin"])
            city = self._pick_value(row, headers, mapping["city"])
            country = self._pick_value(row, headers, mapping["country"])
            industry = self._pick_value(row, headers, mapping["industry"])
            employees = self._pick_value(row, headers, mapping["employees"])

            converted.append(
                {
                    "Company": company,
                    "Company Domain": self._normalized_domain(website),
                    "Website": website,
                    "LinkedIn": linkedin,
                    "City": city,
                    "Country": country,
                    "Industry": industry,
                    "Employees": employees,
                    "Source File": self.source_path.name,
                }
            )
        return self._dedupe(converted)

    def _build_mapping(self, headers: list[str]) -> dict[str, int | None]:
        normalized = [normalize_header(header) for header in headers]
        mapping: dict[str, int | None] = {key: None for key in HEADER_ALIASES}
        for field, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[field] = normalized.index(alias)
                    break
        return mapping

    def _row_dict(self, headers: list[str], raw_row: list[str]) -> dict[str, str]:
        padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
        return {headers[idx]: (padded[idx] or "").strip() for idx in range(len(headers))}

    def _pick_value(self, row: dict[str, str], headers: list[str], index: int | None) -> str:
        if index is None:
            return ""
        if index >= len(headers):
            return ""
        return row.get(headers[index], "").strip()

    def _normalized_domain(self, website: str) -> str:
        if not website:
            return ""
        parsed = urlparse(website if "://" in website else f"https://{website}")
        host = parsed.netloc.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host

    def _dedupe(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        by_key: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (
                row["Company Domain"].lower() if row["Company Domain"] else "",
                re.sub(r"\s+", " ", row["Company"].strip().lower()),
            )
            existing = by_key.get(key)
            if existing is None or self._row_score(row) > self._row_score(existing):
                by_key[key] = row
        return sorted(by_key.values(), key=lambda item: item["Company"].lower())

    def _row_score(self, row: dict[str, str]) -> int:
        score = 0
        for key in ["Company Domain", "Website", "LinkedIn", "City", "Country", "Industry", "Employees"]:
            if row.get(key):
                score += 1
        return score


def load_rows(path: Path, sheet: str | None) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return XlsxReader(path).read_sheet(sheet)
    if suffix == ".csv":
        return CsvReader(path).read_sheet(sheet)
    raise ValueError("Only .xlsx and .csv inputs are supported right now")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEFAULT_OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in DEFAULT_OUTPUT_COLUMNS})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert XLSX/CSV company lists into Apollo-friendly CSV")
    parser.add_argument("input", help="Path to .xlsx or .csv input")
    parser.add_argument("--sheet", help="Optional sheet name for .xlsx inputs")
    parser.add_argument("--output", help="Output CSV path (default: alongside input, *_apollo.csv)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        parser.error(f"Input file does not exist: {input_path}")

    output_path = Path(args.output).expanduser().resolve() if args.output else input_path.with_name(f"{input_path.stem}_apollo.csv")

    try:
        rows = load_rows(input_path, args.sheet)
        converted = ApolloConverter(input_path, rows).convert()
        if not converted:
            raise ValueError("No usable company rows found")
        write_csv(output_path, converted)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {len(converted)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
