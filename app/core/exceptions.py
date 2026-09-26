"""Application errors mapped to a consistent API envelope."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthRequiredError(AppError):
    def __init__(self, message: str = "Authentication is required") -> None:
        super().__init__("AUTH_REQUIRED", message, 401)


class InvalidTokenError(AppError):
    def __init__(self, message: str = "The access token is invalid or expired") -> None:
        super().__init__("INVALID_TOKEN", message, 401)


class InvalidRequestError(AppError):
    def __init__(self, message: str = "The request is invalid") -> None:
        super().__init__("INVALID_REQUEST", message, 422)


class BusinessNotFoundError(AppError):
    def __init__(self, message: str = "Business was not found") -> None:
        super().__init__("BUSINESS_NOT_FOUND", message, 404)


class BusinessAccessDeniedError(AppError):
    def __init__(self, message: str = "You do not have access to this business") -> None:
        super().__init__("BUSINESS_ACCESS_DENIED", message, 403)


class BusinessNotActiveError(AppError):
    def __init__(self, message: str = "Business knowledge base is not active") -> None:
        super().__init__("BUSINESS_NOT_ACTIVE", message, 409)


class BusinessIndexingFailedError(AppError):
    def __init__(self, message: str = "Business indexing failed") -> None:
        super().__init__("BUSINESS_INDEXING_FAILED", message, 502)


class PineconeError(AppError):
    def __init__(self, message: str = "Vector store operation failed") -> None:
        super().__init__("PINECONE_ERROR", message, 502)


class EmbeddingError(AppError):
    def __init__(self, message: str = "Embedding generation failed") -> None:
        super().__init__("EMBEDDING_ERROR", message, 502)


class LLMError(AppError):
    def __init__(self, message: str = "Language model request failed") -> None:
        super().__init__("LLM_ERROR", message, 502)


class ChatError(AppError):
    def __init__(self, message: str = "Chat request failed") -> None:
        super().__init__("CHAT_ERROR", message, 502)


class WhatsAppBusinessNotFoundError(AppError):
    def __init__(self, message: str = "No MindDesk business is connected to this WhatsApp number") -> None:
        super().__init__("WHATSAPP_BUSINESS_NOT_FOUND", message, 404)


class WhatsAppConflictError(AppError):
    def __init__(self, message: str = "This WhatsApp number is already connected to another business") -> None:
        super().__init__("WHATSAPP_CONFLICT", message, 409)


class WhatsAppSendError(AppError):
    def __init__(self, message: str = "Unable to send the WhatsApp message") -> None:
        super().__init__("WHATSAPP_SEND_FAILED", message, 502)


class WhatsAppWebhookForbiddenError(AppError):
    def __init__(self, message: str = "WhatsApp webhook verification failed") -> None:
        super().__init__("WHATSAPP_WEBHOOK_FORBIDDEN", message, 403)
