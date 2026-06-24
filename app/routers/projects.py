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
from fastapi import APIRouter, HTTPException
from app.models.schemas import ProjectCreate
from app.models.database import get_projects, create_project, delete_project

logger = logging.getLogger("bom_api.projects")
router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects():
    """List all projects in the database."""
    try:
        return get_projects()
    except Exception as e:
        logger.exception("Failed to list projects.")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("")
async def add_project(project: ProjectCreate):
    """Create a new project."""
    name_clean = project.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    try:
        success = create_project(name_clean)
        if not success:
            raise HTTPException(status_code=400, detail="Project already exists.")
        return {"status": "success", "detail": f"Project '{name_clean}' created."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create project.")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.delete("")
async def delete_existing_project(project: str):
    """Delete a project and all its BOM data."""
    try:
        delete_project(project)
        return {"status": "success", "detail": f"Project '{project}' and all its BOM data deleted."}
    except Exception as e:
        logger.exception("Failed to delete project.")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
