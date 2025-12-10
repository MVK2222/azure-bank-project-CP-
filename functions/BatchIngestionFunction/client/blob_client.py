"""
Blob client helper for reading blob content as text.

Responsibilities:
- Provide a convenience function to read blob content from a full blob URL.
- Handle SDK differences by attempting readall() first, then falling back to
  content_as_text() where available.
"""

from urllib.parse import urlparse
import logging
import os

from azure.storage.blob import BlobServiceClient

# READ ENV once
_STORAGE_CONN = os.environ.get("STORAGE_CONNECTION_STRING")
if not _STORAGE_CONN:
    raise RuntimeError("Missing STORAGE_CONNECTION_STRING env var for blob client")

_blob_service_client = BlobServiceClient.from_connection_string(_STORAGE_CONN)


def read_blob_text(file_url: str, encoding: str = "utf-8") -> str:
    """
    Download blob content as text given a full blob URL.

    Behavior:
    - Parses the provided blob URL to extract container and blob path.
    - Attempts to download blob bytes via downloader.readall() and decode.
    - If that fails (SDK variant differences), attempts downloader.content_as_text().

    Args:
        file_url: Full URL to the blob (https://<account>.blob.core.windows.net/<container>/<path>).
        encoding: Text encoding to use when decoding bytes.

    Returns:
        The blob content decoded as a string.

    Raises:
        ValueError for invalid file_url.
        Exception when blob download fails.
    """
    if not file_url:
        raise ValueError("file_url is required")

    parsed = urlparse(file_url)
    # parsed.path looks like "/<container>/<path/to/blob>" — strip leading '/'
    path = parsed.path.lstrip("/")
    parts = path.split("/", 1)
    if len(parts) == 0:
        raise ValueError(f"Invalid file_url: {file_url}")
    container_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ""

    try:
        container_client = _blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_path)
        downloader = blob_client.download_blob()
        # Prefer readall() and decode; some SDK versions may not expose readall() directly
        try:
            raw = downloader.readall()
            return raw.decode(encoding)
        except Exception:
            # As a last resort attempt content_as_text() for SDK variants (may be deprecated)
            try:
                return downloader.content_as_text(encoding=encoding)
            except Exception:
                # Re-raise the underlying exception so callers get the real error
                raise
    except Exception as e:
        logging.error(f"Failed to read blob {file_url}: {e}")
        raise
