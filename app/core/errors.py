from enum import Enum
from typing import Optional

class ErrorCategory(str, Enum):
    """에러 분류 - 재시도 여부 결정용"""
    RETRYABLE = "retryable"          # 일시적 오류 → SQS 재시도
    NON_RETRYABLE = "non_retryable"  # 영구 오류 → DLQ로 이동


class PromptEvalError(Exception):
    """Base exception for prompt evaluation system"""
    category: ErrorCategory = ErrorCategory.NON_RETRYABLE
    
    def __init__(self, message: str, request_id: Optional[str] = None, metadata: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "category": self.category.value,
            "message": self.message,
            "request_id": self.request_id,
            "metadata": self.metadata
        }


class ModelInvocationError(PromptEvalError):
    """Error during model invocation"""
    category = ErrorCategory.RETRYABLE  # 모델 호출 실패는 재시도 가능


class EmbeddingError(PromptEvalError):
    """Error during embedding generation"""
    category = ErrorCategory.RETRYABLE


class TokenizationError(PromptEvalError):
    """Error during tokenization"""
    category = ErrorCategory.NON_RETRYABLE  # 입력 문제 → 재시도 불가


class CacheError(PromptEvalError):
    """Error in cache operations"""
    category = ErrorCategory.RETRYABLE


class StorageError(PromptEvalError):
    """Error in storage operations"""
    category = ErrorCategory.RETRYABLE


class ValidationError(PromptEvalError):
    """Error in input validation"""
    category = ErrorCategory.NON_RETRYABLE  # 잘못된 입력 → 재시도 불가


class RateLimitError(PromptEvalError):
    """Rate limit exceeded"""
    category = ErrorCategory.RETRYABLE  # 잠시 후 재시도


class TimeoutError(PromptEvalError):
    """Operation timeout"""
    category = ErrorCategory.RETRYABLE