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
Pydantic response models for the BOM Extractor API.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BOMItem(BaseModel):
    """A single Bill of Materials row."""

    sub_project: str = Field(..., description="Folder name directly above the DXF file")
    drawing: str = Field(..., description="DXF filename without extension")
    category: str = Field(
        default="Other",
        description="BOM item category: Pipe, Fitting, Gasket, Hardware, Other",
    )
    pno: str = Field(default="", description="Part / item / serial number")
    description: str = Field(default="", description="Part description")
    size: str = Field(default="", description="Size or specification")
    material: str = Field(default="", description="Material grade")
    standard: str = Field(
        default="", description="Dimensional standard (e.g. ASME B36.10)"
    )
    qty: float | None = Field(default=None, description="Quantity value")
    qty_unit: str = Field(default="", description="Unit for quantity (e.g. M, Nos)")
    weight: float | None = Field(default=None, description="Weight value")
    weight_unit: str = Field(default="", description="Unit for weight (e.g. kgs, lbs)")


class BOMResponse(BaseModel):
    """Top-level response wrapper."""

    status: str = Field(default="success")
    total_files_processed: int = Field(default=0)
    data: list[BOMItem] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Returned on unrecoverable errors."""

    status: str = Field(default="error")
    detail: str = Field(default="")


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., description="Name of the project")
