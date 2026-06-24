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

import logging
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.models.schemas import BOMItem, BOMResponse, ErrorResponse
from app.models.database import (
    save_bom_data_for_project,
    get_bom_data_for_project,
    clear_project_data,
    clear_sub_project_data,
)
from app.services.converter import DWGConversionError, convert_all_dwg_in_directory
from app.services.extractor import BOMExtractor

logger = logging.getLogger("bom_api.bom")
router = APIRouter(prefix="/api", tags=["extraction"])


@router.post(
    "/extract",
    response_model=BOMResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Extract BOM data from a ZIP of DWG/DXF files",
)
async def extract_bom(
    project: str,
    file: UploadFile = File(
        ..., description="A .zip archive containing .dwg or .dxf files"
    ),
):
    """
    Receive a ZIP file containing `.dwg` and/or `.dxf` drawings.
    Converts any `.dwg` files to `.dxf` on the fly, then extracts
    BOM data from all drawings and returns the consolidated result.
    """
    # --- Validate upload ------------------------------------------------
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be a .zip archive.",
        )

    try:
        # --- Save ZIP to a debug directory in the workspace root -----------
        debug_dir = Path(__file__).parent.parent.parent / "debug_files"
        debug_dir.mkdir(exist_ok=True)

        # Clean up any existing files in debug_dir first
        for p in debug_dir.iterdir():
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
            except Exception:
                pass

        zip_path = debug_dir / file.filename
        logger.info("Saving uploaded file to %s", zip_path)

        with open(zip_path, "wb") as buf:
            content = await file.read()
            buf.write(content)

        # --- Extract the ZIP ---------------------------------------------
        extract_dir = debug_dir / "extracted"
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid ZIP archive.",
            )

        logger.info("ZIP extracted to %s", extract_dir)

        # --- Convert DWG → DXF (if any) ----------------------------------
        dwg_files = [p for p in extract_dir.rglob("*") if p.suffix.lower() == ".dwg"]
        if dwg_files:
            logger.info("Found %d DWG file(s) — converting to DXF...", len(dwg_files))
            try:
                converted = convert_all_dwg_in_directory(extract_dir)
                logger.info("Converted %d DWG file(s) to DXF.", len(converted))
            except DWGConversionError as e:
                raise HTTPException(status_code=500, detail=str(e))

        # --- Discover .dxf files (original + converted) ------------------
        dxf_files = [p for p in extract_dir.rglob("*") if p.suffix.lower() == ".dxf"]

        if not dxf_files:
            raise HTTPException(
                status_code=400,
                detail="No .dwg or .dxf files found inside the uploaded ZIP.",
            )

        logger.info("Found %d DXF file(s) to process.", len(dxf_files))

        # --- Process DXF files in parallel -------------------------------
        def process_single_dxf(dxf_path: Path) -> list[BOMItem]:
            drawing_name = dxf_path.stem.lstrip("_").strip()
            parent = dxf_path.parent
            if parent == extract_dir or parent.name == "extracted":
                parts = drawing_name.split("-")
                sub_project = parts[0].lstrip("_").strip() if parts else drawing_name
            else:
                sub_project = parent.name.lstrip("_").strip()

            logger.info(
                "Processing: sub_project=%s  drawing=%s", sub_project, drawing_name
            )
            try:
                extractor = BOMExtractor(dxf_path)
                rows = extractor.extract()
                if not rows:
                    logger.warning("No BOM data extracted from %s", dxf_path.name)
                return [
                    BOMItem(
                        sub_project=sub_project,
                        drawing=drawing_name,
                        **row,
                    )
                    for row in rows
                ]
            except Exception:
                logger.exception("Failed to parse DXF file: %s", dxf_path.name)
                return []

        all_items: list[BOMItem] = []
        with ThreadPoolExecutor() as executor:
            results = list(executor.map(process_single_dxf, sorted(dxf_files)))

        for items in results:
            all_items.extend(items)

        files_processed = len(dxf_files)

        # Sort items naturally: sub_project, drawing,
        # category priority, pno numeric order
        CATEGORY_ORDER = {
            "Pipe": 0,
            "Fitting": 1,
            "Gasket": 2,
            "Hardware": 3,
            "Other": 4,
        }

        def natural_sort_key(item: BOMItem):
            cat_weight = CATEGORY_ORDER.get(item.category, 5)
            # Split pno into numeric and non-numeric tokens for natural sorting
            pno_parts = []
            for part in re.split(r"([^0-9]+)", item.pno):
                if part.isdigit():
                    pno_parts.append((0, int(part)))
                else:
                    pno_parts.append((1, part.lower()))
            return (
                item.sub_project.lower(),
                item.drawing.lower(),
                cat_weight,
                pno_parts,
            )

        all_items.sort(key=natural_sort_key)

        # --- Save to SQLite database -------------------------------------
        try:
            dict_items = [item.model_dump() for item in all_items]
            save_bom_data_for_project(project, dict_items, files_processed)
            logger.info(
                "Successfully persisted BOM data in SQLite for project %s.", project
            )
        except Exception:
            logger.exception("Failed to save BOM data to SQLite.")

        # --- Return response ---------------------------------------------
        response = BOMResponse(
            status="success",
            total_files_processed=files_processed,
            data=all_items,
        )
        return response

    except HTTPException:
        raise  # re-raise validation errors as-is

    except Exception:
        logger.exception("Unexpected error during BOM extraction.")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                status="error",
                detail="An unexpected error occurred during processing.",
            ).model_dump(),
        )

    finally:
        # Keep files for debugging as per original code behavior
        logger.info("Retaining files in debug_dir for investigation.")


@router.get(
    "/bom",
    response_model=BOMResponse,
    responses={500: {"model": ErrorResponse, "description": "Database error"}},
    summary="Get currently stored BOM data from SQLite",
)
async def get_saved_bom(project: str):
    """Retrieve saved BOM data from database for a specific project."""
    try:
        items, total_files = get_bom_data_for_project(project)
        bom_items = [BOMItem(**row) for row in items]
        return BOMResponse(
            status="success",
            total_files_processed=total_files,
            data=bom_items,
        )
    except Exception as e:
        logger.exception("Failed to retrieve BOM data from SQLite.")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                status="error",
                detail=f"Database error: {str(e)}",
            ).model_dump(),
        )


@router.delete(
    "/bom",
    summary="Clear currently stored BOM data in SQLite",
)
async def delete_saved_bom(project: str, sub_project: str | None = None):
    """Clear saved BOM data from database for a specific project or sub-project."""
    try:
        if sub_project:
            clear_sub_project_data(project, sub_project)
            return {
                "status": "success",
                "detail": (
                    f"BOM data for sub-project"
                    f" '{sub_project}' in project"
                    f" '{project}' cleared."
                ),
            }
        else:
            clear_project_data(project)
            return {
                "status": "success",
                "detail": f"BOM data for project '{project}' cleared.",
            }
    except Exception as e:
        logger.exception("Failed to clear BOM data from SQLite.")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                status="error",
                detail=f"Database error: {str(e)}",
            ).model_dump(),
        )
