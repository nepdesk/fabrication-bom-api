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
DWG → DXF Converter Module.

Provides utilities to convert AutoCAD .dwg files to .dxf format using
available system tools:
  1. LibreDWG's `dwg2dxf` command (preferred — install via `brew install libredwg`)
  2. ODA File Converter (`ODAFileConverter`)
  3. ezdxf's odafc addon (wraps ODA File Converter)

The converter preserves the original folder structure, placing .dxf files
alongside (or in place of) their .dwg counterparts.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("dwg_converter")


class DWGConversionError(Exception):
    """Raised when no converter is available or conversion fails."""


def _find_converter() -> str | None:
    """
    Detect which DWG→DXF converter is available on the system.

    Returns one of: 'dwg2dxf', 'odafc', or None.
    """
    # 1. Check for LibreDWG's dwg2dxf
    if shutil.which("dwg2dxf"):
        return "dwg2dxf"

    # 2. Check for ODA File Converter
    if shutil.which("ODAFileConverter"):
        return "odafc_cli"

    # 3. Check if ezdxf's odafc addon is functional
    try:
        from ezdxf.addons import odafc
        if odafc.is_available():
            return "odafc"
    except (ImportError, Exception):
        pass

    return None


def convert_dwg_to_dxf(dwg_path: Path, output_dir: Path | None = None) -> Path:
    """
    Convert a single .dwg file to .dxf format.

    Parameters
    ----------
    dwg_path : Path
        Path to the input .dwg file.
    output_dir : Path, optional
        Directory for the output .dxf file.  Defaults to the same
        directory as the input file.

    Returns
    -------
    Path
        Path to the converted .dxf file.

    Raises
    ------
    DWGConversionError
        If no converter is available or the conversion fails.
    """
    if not dwg_path.exists():
        raise DWGConversionError(f"DWG file not found: {dwg_path}")

    if output_dir is None:
        output_dir = dwg_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    dxf_path = output_dir / (dwg_path.stem + ".dxf")
    converter = _find_converter()

    if converter is None:
        raise DWGConversionError(
            "No DWG→DXF converter found. Install one of:\n"
            "  • LibreDWG:           brew install libredwg\n"
            "  • ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter"
        )

    logger.info("Converting %s → %s  (using %s)", dwg_path.name, dxf_path.name, converter)

    if converter == "dwg2dxf":
        _convert_with_dwg2dxf(dwg_path, dxf_path)
    elif converter == "odafc_cli":
        _convert_with_oda_cli(dwg_path, dxf_path)
    elif converter == "odafc":
        _convert_with_ezdxf_odafc(dwg_path, dxf_path)

    if not dxf_path.exists():
        raise DWGConversionError(
            f"Conversion produced no output for {dwg_path.name}"
        )

    logger.info("Converted successfully: %s (%d bytes)", dxf_path.name, dxf_path.stat().st_size)
    return dxf_path


def convert_all_dwg_in_directory(root_dir: Path) -> list[Path]:
    """
    Recursively find all .dwg files under root_dir and convert each
    to .dxf in the same directory (preserving folder structure).

    Returns a list of paths to the newly created .dxf files.
    """
    dwg_files = list(root_dir.rglob("*.dwg"))
    # Also match case-insensitive
    dwg_files.extend(
        p for p in root_dir.rglob("*")
        if p.suffix.lower() == ".dwg" and p not in dwg_files
    )

    if not dwg_files:
        return []

    # Check converter availability once before looping
    converter = _find_converter()
    if converter is None:
        raise DWGConversionError(
            "No DWG→DXF converter found. Install one of:\n"
            "  • LibreDWG:           brew install libredwg\n"
            "  • ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter"
        )

    logger.info("Found %d DWG file(s) to convert (converter: %s)", len(dwg_files), converter)

    from concurrent.futures import ThreadPoolExecutor

    def safe_convert(dwg_path: Path) -> Path | None:
        try:
            return convert_dwg_to_dxf(dwg_path)
        except Exception:
            logger.exception("Failed to convert: %s", dwg_path.name)
            return None

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(safe_convert, sorted(dwg_files)))

    return [p for p in results if p is not None]


# ---------------------------------------------------------------------------
# Backend converters
# ---------------------------------------------------------------------------

def _convert_with_dwg2dxf(dwg_path: Path, dxf_path: Path) -> None:
    """Convert using LibreDWG's dwg2dxf command-line tool."""
    cmd = ["dwg2dxf", "-o", str(dxf_path), str(dwg_path)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        logger.error("dwg2dxf stderr: %s", result.stderr)
        raise DWGConversionError(
            f"dwg2dxf failed for {dwg_path.name}: {result.stderr.strip()}"
        )


def _convert_with_oda_cli(dwg_path: Path, dxf_path: Path) -> None:
    """
    Convert using ODA File Converter CLI.

    ODAFileConverter expects:
      ODAFileConverter <input_dir> <output_dir> <output_version> <output_type>
    """
    input_dir = str(dwg_path.parent)
    output_dir = str(dxf_path.parent)

    cmd = [
        "ODAFileConverter",
        input_dir,
        output_dir,
        "ACAD2018",   # output DXF version
        "DXF",        # output type
        "0",          # recurse: 0 = no
        "1",          # audit: 1 = yes
        f"*.{dwg_path.suffix.lstrip('.')}",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        logger.error("ODAFileConverter stderr: %s", result.stderr)
        raise DWGConversionError(
            f"ODAFileConverter failed for {dwg_path.name}: {result.stderr.strip()}"
        )


def _convert_with_ezdxf_odafc(dwg_path: Path, dxf_path: Path) -> None:
    """Convert using ezdxf's odafc addon (wraps ODA File Converter)."""
    try:
        from ezdxf.addons import odafc
        odafc.convert(str(dwg_path), str(dxf_path))
    except Exception as e:
        raise DWGConversionError(
            f"ezdxf odafc conversion failed for {dwg_path.name}: {e}"
        ) from e
