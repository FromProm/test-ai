class PromptEvalError(Exception):
    """Base exception for prompt evaluation system"""
    pass

class ModelInvocationError(PromptEvalError):
    """Error during model invocation"""
    pass

class EmbeddingError(PromptEvalError):
    """Error during embedding generation"""
    pass

class TokenizationError(PromptEvalError):
    """Error during tokenization"""
    pass

class CacheError(PromptEvalError):
    """Error in cache operations"""
    pass

class StorageError(PromptEvalError):
    """Error in storage operations"""
    pass