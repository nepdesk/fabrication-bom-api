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
Fabrication BOM API by NEPDESK
===============================

An open-source FastAPI microservice designed for heavy engineering, boiler,
and piping fabrication workflows. It processes uploaded ZIP archives containing
drawing files (.dwg, .dxf) in bulk, converts .dwg drawings to .dxf on the fly,
and extracts structured Bill of Materials (BOM) data.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routers import health, projects, bom
from app.models.database import init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("bom_api")

# ---------------------------------------------------------------------------
# FastAPI application initialization with NEPDESK branding
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Fabrication BOM API by NEPDESK",
    description=(
        "An open-source FastAPI microservice tailored for "
        "heavy engineering, boiler, and piping fabrication. "
        "This service accepts bulk .zip archive uploads "
        "containing AutoCAD drawing directories (with .dwg "
        "and .dxf formats), automatically converts drawings "
        "on the fly, and extracts structured Bill of "
        "Materials (BOM) data for downstream fabrication "
        "and inventory pipelines."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets (CSS, JS, HTML) located in the project root
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup_event():
    logger.info("Initializing database...")
    init_db()


# Serve UI from the root path
@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def root():
    """Serve the Fabrication BOM Extractor web UI dashboard."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Router inclusions
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(bom.router)
