"""Magic-byte content verification module for TrustLayers (T²).

Enforces RULES R-UP-01 and R-UP-02:
- File type is determined strictly from content header magic bytes.
- Unsupported file types or corrupt content are rejected with stable error codes.
"""

from typing import Tuple, Optional
from models.schemas import ModalityType
from core.config import (
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_VIDEO_TYPES,
    SUPPORTED_AUDIO_TYPES,
    SUPPORTED_TEXT_TYPES,
    SUPPORTED_DOCUMENT_TYPES,
    ALL_SUPPORTED_MIME_TYPES,
)


class IngestValidationError(Exception):
    """Exception raised when an uploaded file fails validation."""
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def map_mime_to_modality(mime_type: str) -> ModalityType:
    """Map MIME type to canonical artifact modality string."""
    if mime_type in SUPPORTED_IMAGE_TYPES:
        return "image"
    elif mime_type in SUPPORTED_VIDEO_TYPES:
        return "video"
    elif mime_type in SUPPORTED_AUDIO_TYPES:
        return "audio"
    elif mime_type in SUPPORTED_TEXT_TYPES:
        return "text"
    elif mime_type in SUPPORTED_DOCUMENT_TYPES:
        return "document"
    else:
        raise IngestValidationError("UNSUPPORTED_TYPE", f"Unsupported MIME type: {mime_type}")


def detect_content_type(file_bytes: bytes, filename: Optional[str] = None) -> Tuple[str, ModalityType]:
    """Detect MIME type and modality strictly from magic bytes (R-UP-01).

    Args:
        file_bytes: Raw bytes of the artifact file.
        filename: Optional user filename (used only for fallback extension hint checking).

    Returns:
        Tuple of (mime_type, modality)

    Raises:
        IngestValidationError: If type is unsupported or file is empty/corrupt.
    """
    if not file_bytes:
        raise IngestValidationError("EMPTY_CONTENT", "File content is empty")

    header = file_bytes[:32]

    # JPEG: FF D8 FF
    if header.startswith(b"\xFF\xD8\xFF"):
        mime = "image/jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    # WebP: RIFF ... WEBP
    elif header.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP":
        mime = "image/webp"
    # PDF: %PDF-
    elif header.startswith(b"%PDF-"):
        mime = "application/pdf"
    # MP4 / QuickTime: ftyp box at offset 4
    elif len(file_bytes) >= 12 and file_bytes[4:8] == b"ftyp":
        brand = file_bytes[8:12]
        if brand in (b"qt  ", b"moov"):
            mime = "video/quicktime"
        else:
            mime = "video/mp4"
    # WebM / OGG / FLAC / WAV / MP3 / Text checks
    elif header.startswith(b"\x1a\x45\xdf\xa3"):
        mime = "video/webm"
    elif header.startswith(b"OggS"):
        mime = "audio/ogg"
    elif header.startswith(b"fLaC"):
        mime = "audio/flac"
    elif header.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WAVE":
        mime = "audio/wav"
    elif header.startswith(b"\xFF\xFB") or header.startswith(b"\xFF\xF3") or header.startswith(b"ID3"):
        mime = "audio/mpeg"
    else:
        # Check text/plain if valid UTF-8 text without control characters
        try:
            sample = file_bytes[:1024].decode("utf-8")
            # Printable text only: tab (9), LF (10), CR (13), and printable chars (>= 32, excluding DEL 127)
            is_text = all(ord(c) in (9, 10, 13) or (32 <= ord(c) != 127) for c in sample)
            if is_text:
                mime = "text/plain"
            else:
                raise IngestValidationError("UNSUPPORTED_TYPE", "File content contains non-text binary bytes")
        except UnicodeDecodeError:
            raise IngestValidationError("UNSUPPORTED_TYPE", "File header magic bytes not recognized")

    if mime not in ALL_SUPPORTED_MIME_TYPES:
        raise IngestValidationError("UNSUPPORTED_TYPE", f"Type {mime} is not supported")

    modality = map_mime_to_modality(mime)
    return mime, modality
