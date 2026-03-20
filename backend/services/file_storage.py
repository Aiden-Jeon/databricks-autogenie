"""File storage service using local file system.

Unified file storage for both Lamp and Enhancer workflows.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import BinaryIO, List, Union

from fastapi import UploadFile

logger = logging.getLogger(__name__)


class LocalFileStorageService:
    """Manages file uploads using local file system.

    Supports both Lamp (PDF/markdown requirements) and Enhancer (benchmark JSON) uploads.
    """

    def __init__(self, base_path: str = "storage/uploads"):
        """Initialize file storage service with local file system.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using local file storage: {self.base_path}")

    async def save_uploads(self, files: List[UploadFile], session_id: str) -> List[str]:
        """Save uploaded files to session-specific directory.

        Args:
            files: List of uploaded files
            session_id: Session identifier

        Returns:
            List of saved file paths
        """
        session_dir = self.base_path / session_id
        session_dir.mkdir(exist_ok=True)

        file_paths = []
        for file in files:
            path = session_dir / file.filename
            content = await file.read()
            with open(path, 'wb') as f:
                f.write(content)
            file_paths.append(str(path))

        return file_paths

    def save_file(
        self,
        session_id: str,
        filename: str,
        file: Union[BinaryIO, bytes]
    ) -> str:
        """Save a single file.

        Args:
            session_id: Session identifier
            filename: Original filename
            file: File object or bytes to save

        Returns:
            Relative path to saved file
        """
        session_dir = self.base_path / session_id
        session_dir.mkdir(exist_ok=True)

        file_path = session_dir / filename
        with open(file_path, "wb") as f:
            if isinstance(file, bytes):
                f.write(file)
            else:
                shutil.copyfileobj(file, f)

        # Return path relative to storage directory
        return str(file_path.relative_to(self.base_path.parent))

    def get_session_dir(self, session_id: str) -> str:
        """Get the directory path for a session."""
        return str(self.base_path / session_id)

    def create_session_dir(self, session_id: str) -> str:
        """Create and return session directory."""
        session_dir = self.base_path / session_id
        session_dir.mkdir(exist_ok=True)
        return str(session_dir)

    def get_file_path(self, relative_path: str) -> Path:
        """Get absolute path for a stored file.

        Args:
            relative_path: Relative path from save_file

        Returns:
            Absolute path to file
        """
        return self.base_path.parent / relative_path

    def list_session_files(self, session_id: str) -> List[str]:
        """List all files for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of filenames
        """
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return []

        return [f.name for f in session_dir.iterdir() if f.is_file()]

    def delete_session_files(self, session_id: str) -> None:
        """Delete all files for a session.

        Args:
            session_id: Session identifier
        """
        session_dir = self.base_path / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def file_exists(self, session_id: str, filename: str) -> bool:
        """Check if a file exists in session directory."""
        file_path = self.base_path / session_id / filename
        return file_path.exists()

    def read_file(self, session_id: str, filename: str) -> bytes:
        """Read file content from session directory.

        Args:
            session_id: Session identifier
            filename: File name

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_path = self.base_path / session_id / filename
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            return f.read()
