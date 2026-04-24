"""Custom exception hierarchy for MakePDF."""


class MakePdfError(Exception):
    """Base exception for all MakePDF errors."""


class InputError(MakePdfError):
    """Bad input file or format."""


class DependencyError(MakePdfError):
    """Missing optional dependency."""


class EncryptionError(MakePdfError):
    """Password or permission issues."""


class SignatureError(MakePdfError):
    """Signature creation or verification failed."""


class OCRError(MakePdfError):
    """OCR processing failed."""
