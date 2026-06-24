# Copyright (C) 2026 NEPDESK.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
DXF BOM Extractor Module (v7).

Provides the BOMExtractor class that parses AutoCAD .dxf files to extract
Bill of Materials data. Designed specifically for piping isometric drawings
(Riser and Downcomer formats) with dynamic column structures, handling duplicate
serial numbers, UOM absence, and quantity multipliers.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import ezdxf

logger = logging.getLogger("bom_extractor")

# ---------------------------------------------------------------------------
# Header keyword matching (Normalized)
# ---------------------------------------------------------------------------
# Key represents canonical field, values are uppercase alphanumeric-only patterns.
HEADER_PATTERNS_NORM: dict[str, list[str]] = {
    "pno": ["PNO", "SRNO", "SLNO", "SNO", "ITEMNO", "ITEM", "NO"],
    "description": ["DESCRIPTION", "DESC", "COMPONENT", "PARTDESCRIPTION", "PARTDESC", "NAME", "DISCRIPTION"],
    "size": ["SIZE", "SPEC", "SPECIFICATION", "DIMENSION", "DIM", "NB", "NOMINALSIZE"],
    "material": ["MATERIAL", "MATL", "MAT", "GRADE", "MATERIALGRADE"],
    "standard": ["DIMSTANDARD", "DIMENSIONALSTANDARD", "STANDARD", "STD"],
    "qty": ["QTYLENGTH", "QTY", "QTYNOS", "QTYNO", "QUANTITY", "LENGTH", "NOS", "COUNT"],
    "weight": ["WEIGHTKGS", "WEIGHTKG", "WEIGHT", "WT", "UNITWEIGHT", "UNITWT", "TOTALWEIGHT", "TOTALWT", "MASS"],
}

# Flat tag map for block attribute matching (Strategy 1)
TAG_MAP: dict[str, str] = {
    "PNO": "pno", "PART_NO": "pno", "PARTNO": "pno", "SRNO": "pno",
    "PART_NUMBER": "pno", "ITEM": "pno", "ITEM_NO": "pno",
    "DESC": "description", "DESCRIPTION": "description",
    "SIZE": "size", "SPEC": "size",
    "MATL": "material", "MATERIAL": "material", "MAT": "material",
    "GRADE": "material", "MATERIAL_GRADE": "material",
    "QTY": "qty", "QUANTITY": "qty", "NOS": "qty", "COUNT": "qty",
    "WEIGHT": "weight", "WT": "weight", "MASS": "weight",
    "STANDARD": "standard", "STD": "standard",
}

# Patterns marking the END of the BOM table
_END_MARKERS = re.compile(
    r"TOTAL\s*(PIPE\s*LENGTH|WEIGHT|WT)|"
    r"%%U(NOTES|HOLD|REF)|"
    r"^\*?\s*NOTE",
    re.IGNORECASE,
)

# Patterns to match sub-headers/groups
GROUP_HEADER_PATTERNS = [
    re.compile(r"RISER\s+NO\s*.*", re.IGNORECASE),
    re.compile(r"MAIN\s+DOWNCOMER\s*.*", re.IGNORECASE),
    re.compile(r"DOWNCOMER\s+PIPE\s*.*", re.IGNORECASE),
]


def clean_dxf_text(text: str) -> str:
    """Strip AutoCAD formatting codes from MTEXT/TEXT."""
    if not text:
        return ""
    # Remove braces
    t = text.replace("{", "").replace("}", "")
    # Remove control codes starting with backslash (e.g. \A1;, \P, \fArial; etc.)
    t = re.sub(r"\\[A-Za-z0-9_.-]+(;|\s|)", "", t)
    t = re.sub(r"\\P", " ", t)  # \P is newline in MTEXT
    t = re.sub(r"\\[A-Za-z][0-9]*", "", t)
    # Replace %%D with degree, %%U with underline (remove)
    t = re.sub(r"%%[A-Za-z]", "", t)
    return t.strip()


def normalize_for_match(text: str) -> str:
    """Normalize a string to uppercase alphanumeric-only for pattern matching."""
    cleaned = clean_dxf_text(text).upper()
    return re.sub(r"[^A-Z0-9]", "", cleaned)


def _safe_float(value: str | Any) -> float | None:
    """Parse a numeric value from a string; return None on failure."""
    if value is None:
        return None
    # Clean up prefixes like EACH or units
    text = str(value).strip()
    text = re.sub(r"^\s*EACH\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+EACH\s*$", "", text, flags=re.IGNORECASE)
    if text in ("", "-", "--", "—", "~"):
        return None
    match = re.search(r"([0-9]*\.?[0-9]+)", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _extract_unit(value: str | Any, fallback: str = "") -> str:
    """Extract a unit suffix from a value string, e.g. '1.2 M' → 'M'."""
    if value is None:
        return fallback
    text = str(value).strip()
    text = re.sub(r"^\s*EACH\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+EACH\s*$", "", text, flags=re.IGNORECASE)
    match = re.search(r"\d+(?:\.\d+)?\s*([A-Za-z/²³\s][A-Za-z./²³\s]*)", text)
    if match:
        return match.group(1).strip()
    return fallback


def get_group_multiplier(group_name: str) -> int:
    """Determine quantity multiplier from group name (e.g. '9 & 10' -> 2)."""
    name_upper = group_name.upper()
    if "&" in name_upper or "AND" in name_upper or "," in name_upper:
        return 2
    return 1


def extract_riser_prefix(group_name: str) -> str | None:
    """Extract riser prefix (e.g. 'RISER NO 4' -> '4')."""
    match = re.search(r"RISER\s+NO\.?\s*-?\s*([0-9\s&]+)", group_name, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def classify_category(description: str) -> str:
    """Classify a BOM item based on description keywords."""
    desc = description.upper()
    if any(kw in desc for kw in ("PIPE", "TUBE")):
        return "Pipe"
    if any(kw in desc for kw in ("ELBOW", "ELB", "TEE", "REDUCER", "RED", "RDC", "RDUC", "CAP", "COUPLING", "CPLG", "UNION", "OLET", "BEND", "CROSS", "FLANGE", "FLG", "NIPPLE", "NIP", "WELDOLET", "SOCKOLET", "THREADOLET", "VALVE", "VLV")):
        return "Fitting"
    if any(kw in desc for kw in ("GASKET", "SEAL", "O-RING", "GSKT")):
        return "Gasket"
    if any(kw in desc for kw in ("BOLT", "BLT", "NUT", "STUD", "WASHER", "FASTENER", "BRACKET", "SUPPORT", "HANGER", "CLAMP", "U-BOLT", "ANCHOR")):
        return "Hardware"
    return "Other"


class BOMExtractor:
    """
    Extracts BOM rows from a single .dxf file.
    Supports Riser and Downcomer table formats.
    """

    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)
        self.rows: list[dict[str, Any]] = []

    def extract(self) -> list[dict[str, Any]]:
        """Run extraction and return a list of normalised BOM row dicts."""
        doc = ezdxf.readfile(str(self.filepath))
        msp = doc.modelspace()

        rows = self._extract_from_blocks(msp)
        if not rows:
            logger.info(
                "No block attributes in %s — trying TEXT/MTEXT table detection.",
                self.filepath.name,
            )
            rows = self._extract_from_text_table(msp)

        self.rows = [self._normalize_row(r) for r in rows]
        return self.rows

    # ==================================================================
    # Strategy 1: Block Attributes
    # ==================================================================

    def _extract_from_blocks(self, msp) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for insert in msp.query("INSERT"):
            if not insert.attribs:
                continue
            row: dict[str, str] = {}
            for attrib in insert.attribs:
                tag = attrib.dxf.tag.strip().upper()
                canonical = TAG_MAP.get(tag)
                if canonical:
                    row[canonical] = attrib.dxf.text
            # Require ≥ 3 recognised fields
            if len(row) >= 3:
                results.append(row)
        return results

    # ==================================================================
    # Strategy 2: Smart TEXT/MTEXT Table Detection
    # ==================================================================

    def _extract_from_text_table(self, msp) -> list[dict[str, str]]:
        """
        Identify the BOM tables among all TEXT/MTEXT entities, find all
        header rows, map columns, and extract data rows for all tables.
        """
        # --- Step 1: Collect all text entities ---------------------------
        texts = self._collect_texts(msp)
        if not texts:
            return []

        # --- Step 2: Find all Header Rows globally ------------------------
        headers = self._find_all_headers_globally(texts)
        if not headers:
            logger.warning("Could not identify BOM header rows in %s", self.filepath.name)
            return []

        all_table_rows: list[dict[str, str]] = []

        # --- Step 3: Extract from each detected table ---------------------
        for i, (header_y, header_cells) in enumerate(headers):
            logger.info("Processing table %d at Y=%.2f: %s", i + 1, header_y, [c["text"] for c in header_cells])

            # Determine X range based on this table's header
            header_xs = [c["x"] for c in header_cells]
            min_table_x = min(header_xs) - 150.0
            max_table_x = max(header_xs) + 150.0
            
            # The next header below this one defines the lower Y boundary for bounds check
            next_header_y = headers[i + 1][0] if i + 1 < len(headers) else None
            
            min_header_y = min(c["y"] for c in header_cells)
            
            # Filter texts that belong to this table's bounding box
            table_texts = [
                t for t in texts
                if t["y"] < min_header_y - 15.0
                and (next_header_y is None or t["y"] > next_header_y + 15.0)
                and min_table_x <= t["x"] <= max_table_x
            ]

            if not table_texts:
                logger.warning("No table text entities found below header at Y=%.2f", header_y)
                continue

            # 1. Compute Y-tolerance based on the initial table texts bounding box
            y_tol = self._compute_y_tolerance_for_table(table_texts)
            initial_rows = self._cluster_by_y(table_texts, y_tol)
            initial_keys = sorted(initial_rows.keys(), reverse=True)

            final_table_texts = []
            prev_y = None
            for y_key in initial_keys:
                cells = initial_rows[y_key]
                row_text = " ".join(c["text"] for c in cells)

                # Stop collecting if we hit the table end marker
                if _END_MARKERS.search(row_text):
                    logger.info("Stopping table text collection due to end marker: %s", row_text)
                    break

                if prev_y is not None:
                    # Stop if there is a huge vertical gap (e.g. > 350.0 units)
                    if prev_y - y_key > 350.0:
                        logger.info("Stopping table text collection due to vertical gap: %.2f", prev_y - y_key)
                        break
                    
                    # Stop if we hit another table header
                    if self._score_header_cells(cells) >= 3:
                        logger.info("Stopping table text collection due to new header: %s", [c["text"] for c in cells])
                        break

                final_table_texts.extend(cells)
                prev_y = y_key

            if not final_table_texts:
                continue

            # Cluster column centers using data table texts + header cells
            col_centers = self._cluster_x_coordinates(final_table_texts + header_cells, min_count=3)
            col_mapping = self._build_column_mapping(header_cells, col_centers)

            rows_by_y = self._cluster_by_y(final_table_texts, y_tol)
            sorted_keys = sorted(rows_by_y.keys(), reverse=True)

            table_rows = self._extract_data_rows_with_mapping(
                rows_by_y, sorted_keys, -1, col_centers, col_mapping
            )
            logger.info("Extracted %d rows from table at Y=%.2f", len(table_rows), header_y)
            all_table_rows.extend(table_rows)

        logger.info(
            "Extracted a total of %d BOM rows from all tables in %s",
            len(all_table_rows),
            self.filepath.name,
        )
        return all_table_rows

    @staticmethod
    def _collect_texts(msp) -> list[dict[str, Any]]:
        """Gather all TEXT and MTEXT entities with position & content."""
        texts: list[dict[str, Any]] = []
        for entity in msp.query("TEXT MTEXT"):
            try:
                if entity.dxftype() == "MTEXT":
                    x, y = entity.dxf.insert.x, entity.dxf.insert.y
                    content = entity.text
                else:
                    x, y = entity.dxf.insert.x, entity.dxf.insert.y
                    content = entity.dxf.text
            except AttributeError:
                continue

            content = clean_dxf_text(content)
            if len(content) == 0:
                continue

            texts.append({"x": round(x, 2), "y": round(y, 2), "text": content})

        return texts

    @staticmethod
    def _find_all_headers_globally(texts: list[dict]) -> list[tuple[float, list[dict]]]:
        """
        Find all Y coordinates containing header cells, returning a list of (header_y, header_cells)
        sorted by Y descending (top to bottom).
        """
        # Find all cells matching any header pattern exactly when normalized
        header_candidates = []
        for t in texts:
            normalized = normalize_for_match(t["text"])
            for field, patterns in HEADER_PATTERNS_NORM.items():
                if any(pat == normalized for pat in patterns):
                    header_candidates.append(t)
                    break

        if not header_candidates:
            return []

        # Cluster these candidates by Y coordinate using a tolerance of 100.0
        clusters: dict[float, list[dict]] = {}
        for t in sorted(header_candidates, key=lambda x: -x["y"]):
            placed = False
            for key in clusters:
                if abs(t["y"] - key) <= 25.0:
                    clusters[key].append(t)
                    placed = True
                    break
            if not placed:
                clusters[t["y"]] = [t]

        # Score each cluster by how many distinct fields it matches
        valid_headers = []
        for key_y, cells in clusters.items():
            score = BOMExtractor._score_header_cells(cells)
            if score >= 3:
                avg_y = sum(c["y"] for c in cells) / len(cells)
                valid_headers.append((avg_y, cells))

        return sorted(valid_headers, key=lambda x: -x[0])

    @staticmethod
    def _score_header_cells(cells: list[dict]) -> int:
        matched_fields: set[str] = set()
        for cell in cells:
            normalized = normalize_for_match(cell["text"])
            for field, patterns in HEADER_PATTERNS_NORM.items():
                if field in matched_fields:
                    continue
                for pat in patterns:
                    if normalized == pat:
                        matched_fields.add(field)
                        break
        return len(matched_fields)

    @staticmethod
    def _cluster_x_coordinates(texts: list[dict], min_count: int = 5) -> list[float]:
        """Group X-coordinates that align vertically using greedy max-width to prevent chaining."""
        xs = sorted(t["x"] for t in texts)
        if not xs:
            return []
        
        clusters = []
        current_cluster = [xs[0]]
        for x in xs[1:]:
            if x - current_cluster[0] <= 5.0:
                current_cluster.append(x)
            else:
                clusters.append(current_cluster)
                current_cluster = [x]
        clusters.append(current_cluster)
        
        valid_centers = []
        for cluster in clusters:
            if len(cluster) >= min_count:
                valid_centers.append(sum(cluster) / len(cluster))
        
        return sorted(valid_centers)

    @staticmethod
    def _build_column_mapping(header_cells: list[dict], col_centers: list[float]) -> dict[int, str]:
        col_mapping: dict[int, str] = {}
        for cell in header_cells:
            normalized = normalize_for_match(cell["text"])
            matched_field = None
            for field, patterns in HEADER_PATTERNS_NORM.items():
                for pat in patterns:
                    if normalized == pat:
                        matched_field = field
                        break
                if matched_field:
                    break

            if matched_field:
                # Find closest column center
                best_idx = None
                best_dist = float("inf")
                for idx, center in enumerate(col_centers):
                    dist = abs(cell["x"] - center)
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
                if best_idx is not None:
                    col_mapping[best_idx] = matched_field

        # Find the description column index
        desc_idx = None
        for idx, field in col_mapping.items():
            if field == "description":
                desc_idx = idx
                break

        if desc_idx is not None:
            # Map unmapped columns to the left of the description column to serial numbers
            pno_indices = [idx for idx in range(desc_idx) if idx not in col_mapping]
            if len(pno_indices) == 1:
                col_mapping[pno_indices[0]] = "pno_sub"
            elif len(pno_indices) >= 2:
                pno_indices = sorted(pno_indices)
                col_mapping[pno_indices[0]] = "pno_main"
                col_mapping[pno_indices[-1]] = "pno_sub"

        return col_mapping

    @staticmethod
    def _compute_y_tolerance_for_table(table_texts: list[dict]) -> float:
        """Compute Y-tolerance based only on table elements."""
        ys = sorted({t["y"] for t in table_texts})
        if len(ys) < 2:
            return 3.0
        gaps = sorted([ys[i + 1] - ys[i] for i in range(len(ys) - 1)])
        gaps_filtered = [g for g in gaps if g > 2.0]
        if not gaps_filtered:
            return 3.0
        idx = max(0, len(gaps_filtered) // 4)
        computed_tol = gaps_filtered[idx] * 0.6
        return max(computed_tol, 3.0)

    @staticmethod
    def _cluster_by_y(
        texts: list[dict], tolerance: float
    ) -> dict[float, list[dict]]:
        """Group text entries whose Y-coords are within tolerance."""
        clusters: dict[float, list[dict]] = {}
        for t in sorted(texts, key=lambda x: -x["y"]):
            placed = False
            for key in clusters:
                if abs(t["y"] - key) <= tolerance:
                    clusters[key].append(t)
                    placed = True
                    break
            if not placed:
                clusters[t["y"]] = [t]
        return clusters

    def _extract_data_rows_with_mapping(
        self,
        rows_by_y: dict[float, list[dict]],
        sorted_keys: list[float],
        header_key_idx: int,
        col_centers: list[float],
        col_mapping: dict[int, str],
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        current_group = ""
        current_multiplier = 1
        current_main_pno = ""

        # Start scanning data rows below the header row index
        for idx in range(header_key_idx + 1, len(sorted_keys)):
            y_key = sorted_keys[idx]
            cells = rows_by_y[y_key]
            row_text = " ".join(c["text"] for c in cells)

            # Check for end-of-table
            if _END_MARKERS.search(row_text):
                break

            # Check for group/section headers
            is_group = False
            for pat in GROUP_HEADER_PATTERNS:
                if pat.search(row_text):
                    current_group = row_text.strip()
                    current_multiplier = get_group_multiplier(current_group)
                    
                    # Extract riser prefix if it's a riser group
                    prefix = extract_riser_prefix(current_group)
                    if prefix:
                        current_main_pno = prefix
                        logger.info("Setting riser prefix: '%s'", current_main_pno)
                        
                    logger.info("Found group: '%s' (multiplier=%d)", current_group, current_multiplier)
                    is_group = True
                    break
            if is_group:
                continue

            # Map cell values to detected columns
            row_vals: dict[str, list[str]] = defaultdict(list)
            for cell in cells:
                # Assign to closest column center
                best_idx = None
                best_dist = float("inf")
                for c_idx, center in enumerate(col_centers):
                    dist = abs(cell["x"] - center)
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = c_idx
                
                if best_idx is not None and best_dist <= 20.0 and best_idx in col_mapping:
                    field = col_mapping[best_idx]
                    row_vals[field].append(cell["text"])

            # Flatten lists to strings
            row_flat = {k: " ".join(v).strip() for k, v in row_vals.items()}

            # A valid BOM row must have at least one of description, size, or material populated
            if not any(row_flat.get(f, "").strip() for f in ("description", "size", "material")):
                continue

            # Process serial numbers (pno)
            col0 = row_flat.get("pno_main", "").strip()
            col1 = row_flat.get("pno_sub", "").strip()
            flat_pno = row_flat.get("pno", "").strip()

            if col0:
                current_main_pno = col0
            elif flat_pno:
                current_main_pno = flat_pno

            # If the serial number itself indicates a combined riser, update multiplier
            if current_main_pno and ("&" in current_main_pno or "AND" in current_main_pno or "," in current_main_pno):
                current_multiplier = 2

            # Determine final serial number
            pno_val = ""
            if col0 and col1 and "/" in col0 and "/" in col1:
                # Parallel serial numbers (e.g. Downcomer: 1/1, 2/1)
                pno_val = f"{col0}, {col1}"
                if current_multiplier == 1:
                    current_multiplier = 2
            elif col1:
                if col1.startswith("/"):
                    pno_val = f"{current_main_pno}{col1}"
                else:
                    pno_val = f"{current_main_pno}/{col1}" if current_main_pno else col1
            else:
                pno_val = current_main_pno

            # Create data dictionary
            row_data = {
                "pno": pno_val,
                "description": row_flat.get("description", ""),
                "size": row_flat.get("size", ""),
                "material": row_flat.get("material", ""),
                "standard": row_flat.get("standard", ""),
                "qty": row_flat.get("qty", ""),
                "weight": row_flat.get("weight", ""),
                "multiplier": str(current_multiplier),
            }

            results.append(row_data)

        return results

    # ------------------------------------------------------------------
    # Row normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_row(raw: dict[str, str]) -> dict[str, Any]:
        """Convert raw extracted dict into the output schema, applying multiplier."""
        qty_raw = raw.get("qty", "")
        weight_raw = raw.get("weight", "")
        multiplier = int(raw.get("multiplier", "1"))

        base_qty = _safe_float(qty_raw)
        final_qty = base_qty * multiplier if base_qty is not None else None

        base_weight = _safe_float(weight_raw)
        final_weight = base_weight * multiplier if base_weight is not None else None

        pno_raw = raw.get("pno", "").strip()
        desc = raw.get("description", "").strip()
        size_raw = raw.get("size", "").strip()

        # Repair: split merged serial number and description if one is empty
        if pno_raw and not desc:
            # Check if pno_raw has alphabetic text and spaces indicating it's merged
            has_letters = any(c.isalpha() for c in pno_raw)
            if len(pno_raw) > 4 and has_letters and " " in pno_raw:
                # 1. Starts with digit: "6 SW RDC. CPLG." -> "6", "SW RDC. CPLG."
                match_start = re.match(r"^(\d+)\s+(.+)$", pno_raw)
                if match_start:
                    pno_raw = match_start.group(1).strip()
                    desc = match_start.group(2).strip()
                else:
                    # 2. Ends with digit: "SW EQ TEE 7" -> "7", "SW EQ TEE"
                    match_end = re.match(r"^(.+?)\s+(\d+)$", pno_raw)
                    if match_end:
                        pno_raw = match_end.group(2).strip()
                        desc = match_end.group(1).strip()
                    else:
                        # 3. Pure description in serial column: "BW LR 90 ELBOW (*NOTE)"
                        desc = pno_raw
                        pno_raw = ""

        # Repair: handle cases where the description (like "NUTS") is mistakenly placed in the size column
        if not desc and size_raw:
            if size_raw.upper() in ("NUTS", "NUT", "BOLTS", "BOLT", "GASKET", "GASKETS", "ELBOW", "TEE", "FLANGE", "PIPE"):
                desc = size_raw
                size_raw = ""

        category = classify_category(desc)

        return {
            "pno": pno_raw,
            "category": category,
            "description": desc,
            "size": size_raw,
            "material": raw.get("material", "").strip(),
            "standard": raw.get("standard", "").strip(),
            "qty": final_qty,
            "qty_unit": _extract_unit(qty_raw),
            "weight": final_weight,
            "weight_unit": _extract_unit(weight_raw, fallback="kgs"),
        }
