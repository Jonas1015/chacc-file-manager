class FileStorageError(Exception):
    """Base exception for file storage errors."""
    pass


class FileNotFoundError(FileStorageError):
    """File not found in storage."""
    pass


class InvalidPathError(FileStorageError):
    """Invalid or unsafe file path detected."""
    pass


class QuotaExceededError(FileStorageError):
    """Storage quota exceeded."""
    pass


class InvalidContentTypeError(FileStorageError):
    """Invalid content type for the channel."""
    pass


class FileTooLargeError(FileStorageError):
    """File size exceeds limit."""
    pass