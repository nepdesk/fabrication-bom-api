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

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Path to the database in the project root
DB_PATH = Path(__file__).parent.parent.parent / "bom.db"


def get_db_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    with get_db_connection() as conn:
        # Create projects table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                total_files INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create bom_items table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bom_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                sub_project TEXT,
                drawing TEXT,
                category TEXT,
                pno TEXT,
                description TEXT,
                size TEXT,
                material TEXT,
                standard TEXT,
                qty REAL,
                qty_unit TEXT,
                weight REAL,
                weight_unit TEXT
            )
        """)
        
        # Schema migration check: ensure project_name column exists
        cursor = conn.execute("PRAGMA table_info(bom_items)")
        cols = [row["name"] for row in cursor.fetchall()]
        if "project_name" not in cols:
            conn.execute("ALTER TABLE bom_items ADD COLUMN project_name TEXT")
            
        # Create index for project filtering performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bom_items_project ON bom_items(project_name)")
        conn.commit()


def get_projects() -> List[Dict[str, Any]]:
    """Retrieve all projects sorted by name."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT name, total_files FROM projects ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]


def create_project(name: str) -> bool:
    """Create a new project. Return True if created, False if already exists."""
    name_clean = name.strip()
    if not name_clean:
        return False
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO projects (name) VALUES (?)", (name_clean,))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False


def save_bom_data_for_project(project_name: str, items: List[Dict[str, Any]], total_files_processed: int) -> None:
    """Save new BOM items for a project, overwriting only matching drawing entries and updating files count."""
    with get_db_connection() as conn:
        # Check if project exists, if not, create it
        conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (project_name,))
        
        # Clear items only for the drawings that are in the new upload (prevent duplicates while appending)
        drawings_to_overwrite = list(set(item.get("drawing") for item in items if item.get("drawing")))
        if drawings_to_overwrite:
            placeholders = ",".join("?" for _ in drawings_to_overwrite)
            conn.execute(
                f"DELETE FROM bom_items WHERE project_name = ? AND drawing IN ({placeholders})",
                [project_name] + drawings_to_overwrite
            )
        
        # Save new items
        for item in items:
            conn.execute("""
                INSERT INTO bom_items (
                    project_name, sub_project, drawing, category, pno, description, 
                    size, material, standard, qty, qty_unit, weight, weight_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_name,
                item.get("sub_project"),
                item.get("drawing"),
                item.get("category"),
                item.get("pno"),
                item.get("description"),
                item.get("size"),
                item.get("material"),
                item.get("standard"),
                item.get("qty"),
                item.get("qty_unit"),
                item.get("weight"),
                item.get("weight_unit")
            ))
            
        # Calculate new unique drawings count for this project
        cursor = conn.execute("SELECT COUNT(DISTINCT drawing) FROM bom_items WHERE project_name = ?", (project_name,))
        unique_drawings = cursor.fetchone()[0]
        
        # Update project total files
        conn.execute(
            "UPDATE projects SET total_files = ? WHERE name = ?",
            (unique_drawings, project_name)
        )
        conn.commit()


def get_bom_data_for_project(project_name: str) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieve all BOM items and files count for a specific project."""
    with get_db_connection() as conn:
        # Get items
        cursor = conn.execute("""
            SELECT sub_project, drawing, category, pno, description, 
                   size, material, standard, qty, qty_unit, weight, weight_unit 
            FROM bom_items
            WHERE project_name = ?
            ORDER BY id ASC
        """, (project_name,))
        items = [dict(row) for row in cursor.fetchall()]
        
        # Get files count
        cursor = conn.execute("SELECT total_files FROM projects WHERE name = ?", (project_name,))
        row = cursor.fetchone()
        total_files = row["total_files"] if row else 0
        
        return items, total_files


def clear_project_data(project_name: str) -> None:
    """Clear all BOM items for the project and reset file count to 0."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM bom_items WHERE project_name = ?", (project_name,))
        conn.execute("UPDATE projects SET total_files = 0 WHERE name = ?", (project_name,))
        conn.commit()


def clear_sub_project_data(project_name: str, sub_project: str) -> None:
    """Clear all BOM items for a specific sub-project and update files count."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM bom_items WHERE project_name = ? AND sub_project = ?", (project_name, sub_project))
        # Recalculate unique drawings count
        cursor = conn.execute("SELECT COUNT(DISTINCT drawing) FROM bom_items WHERE project_name = ?", (project_name,))
        unique_drawings = cursor.fetchone()[0]
        conn.execute("UPDATE projects SET total_files = ? WHERE name = ?", (unique_drawings, project_name))
        conn.commit()


def delete_project(project_name: str) -> None:
    """Delete a project and all its associated BOM items."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM bom_items WHERE project_name = ?", (project_name,))
        conn.execute("DELETE FROM projects WHERE name = ?", (project_name,))
        conn.commit()
