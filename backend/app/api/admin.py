"""Admin endpoints — database reset for clean demo environment."""

import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/admin/reset")
async def reset_database():
    """
    Reset the database to clean seed state.
    This runs seed_db.py logic synchronously for quick demo resets.
    """
    try:
        backend_path = Path(__file__).resolve().parent.parent.parent.parent
        seed_path = backend_path / "seed_db.py"
        result = subprocess.run(
            [sys.executable, str(seed_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(backend_path),
        )
        return {
            "status": "SUCCESS",
            "message": "Database reset successfully",
            "stdout": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
        }
    except Exception as e:
        raise HTTPException(500, f"Reset failed: {str(e)}")