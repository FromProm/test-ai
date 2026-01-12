import numpy as np
from typing import List
from app.adapters.embedder.base import BaseEmbedder

class MockEmbedder(BaseEmbedder):
    """테스트용 Mock Embedder - 실제 임베딩 호출 없이 가짜 벡터 생성"""
    
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
    
    async def embed_text(self, text: str) -> List[float]:
        """가짜 텍스트 임베딩 생성"""
        # 텍스트 해시를 시드로 사용해서 일관된 벡터 생성
        seed = hash(text) % 2**32
        np.random.seed(seed)
        
        # 정규화된 랜덤 벡터 생성
        vector = np.random.normal(0, 1, self.dimension)
        vector = vector / np.linalg.norm(vector)
        
        return vector.tolist()
    
    async def embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """가짜 텍스트 배치 임베딩"""
        return [await self.embed_text(text) for text in texts]
    
    async def embed_multilingual(self, text: str) -> List[float]:
        """가짜 다국어 임베딩 (약간 다른 시드 사용)"""
        seed = (hash(text) + 1) % 2**32
        np.random.seed(seed)
        
        vector = np.random.normal(0, 1, self.dimension)
        vector = vector / np.linalg.norm(vector)
        
        return vector.tolist()
    
    async def embed_multilingual_batch(self, texts: List[str]) -> List[List[float]]:
        """가짜 다국어 배치 임베딩"""
        return [await self.embed_multilingual(text) for text in texts]
    
    async def embed_multimodal(self, content: str) -> List[float]:
        """가짜 멀티모달 임베딩"""
        seed = (hash(content) + 2) % 2**32
        np.random.seed(seed)
        
        vector = np.random.normal(0, 1, self.dimension)
        vector = vector / np.linalg.norm(vector)
        
        return vector.tolist()
    
    async def embed_cohere_v4(self, content: str) -> List[float]:
        """가짜 Cohere v4 임베딩"""
        seed = (hash(content) + 3) % 2**32
        np.random.seed(seed)
        
        vector = np.random.normal(0, 1, self.dimension)
        vector = vector / np.linalg.norm(vector)
        
        return vector.tolist()