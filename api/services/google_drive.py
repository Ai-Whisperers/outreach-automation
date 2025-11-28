"""
Google Drive Service

Uploads files to Google Drive and manages folder structure.
"""

import io
import json
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from ..config import get_settings
from ..exceptions import CampaignGeneratorError
from ..logging_config import get_logger

logger = get_logger("google_drive")


# =============================================================================
# Custom Exceptions
# =============================================================================

class GoogleDriveError(CampaignGeneratorError):
    """Raised when Google Drive operations fail."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            error_code="GOOGLE_DRIVE_ERROR",
            details=details or {}
        )


# =============================================================================
# Google Drive Service
# =============================================================================

class GoogleDriveService:
    """
    Service for uploading files to Google Drive.
    """

    # MIME types for Google Drive
    MIME_TYPES = {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".md": "text/markdown",
        ".json": "application/json",
        ".txt": "text/plain"
    }

    FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self):
        self.settings = get_settings()
        self.service = None
        self._initialize_service()

    def _initialize_service(self):
        """Initialize Google Drive API service."""
        try:
            # Load credentials from service account file or environment
            credentials_path = getattr(self.settings, 'google_credentials_path', None)
            credentials_json = getattr(self.settings, 'google_credentials_json', None)

            if credentials_path and Path(credentials_path).exists():
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/drive.file']
                )
            elif credentials_json:
                credentials_info = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=['https://www.googleapis.com/auth/drive.file']
                )
            else:
                logger.warning("Google Drive credentials not configured")
                return

            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Google Drive: {e}")
            self.service = None

    def is_available(self) -> bool:
        """Check if Google Drive service is available."""
        return self.service is not None

    async def create_folder(
        self,
        name: str,
        parent_id: str = None
    ) -> str:
        """
        Create a folder in Google Drive.

        Args:
            name: Folder name
            parent_id: Parent folder ID (None for root)

        Returns:
            Created folder ID
        """
        if not self.is_available():
            raise GoogleDriveError("Google Drive service not initialized")

        try:
            file_metadata = {
                'name': name,
                'mimeType': self.FOLDER_MIME
            }

            if parent_id:
                file_metadata['parents'] = [parent_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Created Google Drive folder: {name} ({folder_id})")

            return folder_id

        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            raise GoogleDriveError(f"Failed to create folder: {e}")

    async def upload_file(
        self,
        file_path: str | Path,
        folder_id: str = None,
        file_name: str = None
    ) -> dict[str, str]:
        """
        Upload a file to Google Drive.

        Args:
            file_path: Local file path
            folder_id: Target folder ID (None for root)
            file_name: Custom file name (None uses original)

        Returns:
            Dict with file_id and web_link
        """
        if not self.is_available():
            raise GoogleDriveError("Google Drive service not initialized")

        try:
            file_path = Path(file_path)

            if not file_path.exists():
                raise GoogleDriveError(f"File not found: {file_path}")

            # Determine MIME type
            mime_type = self.MIME_TYPES.get(
                file_path.suffix.lower(),
                "application/octet-stream"
            )

            # File metadata
            file_metadata = {
                'name': file_name or file_path.name
            }

            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Upload file
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            result = {
                'file_id': file.get('id'),
                'web_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink')
            }

            logger.info(f"Uploaded to Google Drive: {file_metadata['name']} ({result['file_id']})")

            return result

        except GoogleDriveError:
            raise
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise GoogleDriveError(f"Failed to upload file: {e}")

    async def upload_bytes(
        self,
        content: bytes,
        file_name: str,
        folder_id: str = None,
        mime_type: str = None
    ) -> dict[str, str]:
        """
        Upload bytes content to Google Drive.

        Args:
            content: File content as bytes
            file_name: File name
            folder_id: Target folder ID
            mime_type: MIME type (auto-detected from extension if None)

        Returns:
            Dict with file_id and web_link
        """
        if not self.is_available():
            raise GoogleDriveError("Google Drive service not initialized")

        try:
            # Determine MIME type from filename
            if not mime_type:
                ext = Path(file_name).suffix.lower()
                mime_type = self.MIME_TYPES.get(ext, "application/octet-stream")

            # File metadata
            file_metadata = {
                'name': file_name
            }

            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Upload from bytes
            media = MediaIoBaseUpload(
                io.BytesIO(content),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            result = {
                'file_id': file.get('id'),
                'web_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink')
            }

            logger.info(f"Uploaded to Google Drive: {file_name} ({result['file_id']})")

            return result

        except GoogleDriveError:
            raise
        except Exception as e:
            logger.error(f"Failed to upload bytes: {e}")
            raise GoogleDriveError(f"Failed to upload bytes: {e}")

    async def create_project_folder(
        self,
        project_id: str,
        project_name: str,
        parent_id: str = None
    ) -> str:
        """
        Create a folder structure for a project.

        Args:
            project_id: Project identifier
            project_name: Human-readable name
            parent_id: Parent folder for all campaigns

        Returns:
            Project folder ID
        """
        folder_name = f"{project_name} ({project_id})"
        return await self.create_folder(folder_name, parent_id)

    async def share_folder(
        self,
        folder_id: str,
        email: str,
        role: str = "reader"
    ):
        """
        Share a folder with a user.

        Args:
            folder_id: Folder to share
            email: User email
            role: Permission role (reader, writer, commenter)
        """
        if not self.is_available():
            raise GoogleDriveError("Google Drive service not initialized")

        try:
            permission = {
                'type': 'user',
                'role': role,
                'emailAddress': email
            }

            self.service.permissions().create(
                fileId=folder_id,
                body=permission,
                sendNotificationEmail=True
            ).execute()

            logger.info(f"Shared folder {folder_id} with {email} ({role})")

        except Exception as e:
            logger.error(f"Failed to share folder: {e}")
            raise GoogleDriveError(f"Failed to share folder: {e}")

    async def get_file_link(self, file_id: str) -> str:
        """
        Get the web view link for a file.

        Args:
            file_id: File ID

        Returns:
            Web view URL
        """
        if not self.is_available():
            raise GoogleDriveError("Google Drive service not initialized")

        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='webViewLink'
            ).execute()

            return file.get('webViewLink')

        except Exception as e:
            logger.error(f"Failed to get file link: {e}")
            raise GoogleDriveError(f"Failed to get file link: {e}")


# =============================================================================
# Singleton Access
# =============================================================================

_drive_service: GoogleDriveService | None = None


def get_google_drive_service() -> GoogleDriveService:
    """Get singleton Google Drive service."""
    global _drive_service
    if _drive_service is None:
        _drive_service = GoogleDriveService()
    return _drive_service
