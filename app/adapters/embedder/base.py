from abc import ABC, abstractmethod
from typing import List

class BaseEmbedder(ABC):
    """Embedder 기본 인터페이스"""
    
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """텍스트 임베딩"""
        pass
    
    @abstractmethod
    async def embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """텍스트 배치 임베딩"""
        pass
    
    @abstractmethod
    async def embed_multilingual(self, text: str) -> List[float]:
        """다국어 텍스트 임베딩"""
        pass
    
    @abstractmethod
    async def embed_multilingual_batch(self, texts: List[str]) -> List[List[float]]:
        """다국어 텍스트 배치 임베딩"""
        pass
    
    @abstractmethod
    async def embed_multimodal(self, content: str) -> List[float]:
        """멀티모달 임베딩 (이미지 포함)"""
        pass
    
    @abstractmethod
    async def embed_cohere_v4(self, content: str) -> List[float]:
        """Cohere v4 임베딩"""
        pass