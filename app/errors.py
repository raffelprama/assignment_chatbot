"""Typed domain errors. The API maps them to one error shape and an HTTP status."""


class AppError(Exception):
    status_code = 500
    code = "InternalError"

    def __init__(self, message: str, detail: object | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFound(AppError):
    status_code = 404
    code = "NotFound"


class BadRequest(AppError):
    status_code = 400
    code = "BadRequest"


class UnsupportedFile(AppError):
    status_code = 415
    code = "UnsupportedFile"


class FileTooLarge(AppError):
    status_code = 413
    code = "FileTooLarge"


class ServiceUnavailable(AppError):
    """A dependency (Qdrant, embeddings, LLM) failed. Never disguised as "no answer"."""

    status_code = 503
    code = "ServiceUnavailable"


class ExtractionError(AppError):
    """The PDF could not be turned into validated sections. Fails the ingestion job loudly."""

    status_code = 422
    code = "ExtractionFailed"
