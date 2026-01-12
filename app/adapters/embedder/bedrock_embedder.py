import json
import logging
import boto3
from typing import List
from app.adapters.embedder.base import BaseEmbedder
from app.core.config import settings
from app.core.errors import EmbeddingError

logger = logging.getLogger(__name__)

class BedrockEmbedder(BaseEmbedder):
    """AWS Bedrock 임베딩 생성기"""
    
    # 모델별 최대 텍스트 길이 제한
    MAX_TEXT_LENGTHS = {
        'titan_text': 8000,  # Titan Text v2
        'cohere_multilingual': 2048,  # Cohere Multilingual v3
        'nova_multimodal': 8000,  # Nova Multimodal
        'cohere_v4': 2048  # Cohere v4
    }
    
    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
    
    def _truncate_text(self, text: str, model_type: str) -> str:
        """모델별 최대 길이에 맞게 텍스트 자르기"""
        max_length = self.MAX_TEXT_LENGTHS.get(model_type, 2048)
        if len(text) > max_length:
            logger.warning(f"Text truncated from {len(text)} to {max_length} chars for {model_type}")
            return text[:max_length]
        return text
    
    async def embed_text(self, text: str) -> List[float]:
        """Titan Text 임베딩"""
        text = self._truncate_text(text, 'titan_text')
        return await self._invoke_embedding(
            settings.embedding_models['titan_text'],
            {"inputText": text}
        )
    
    async def embed_text_batch(self, texts: List[str]) -> List[List[float]]:
        """Titan Text 배치 임베딩"""
        if not texts:
            return []
        
        # 텍스트 길이 제한 적용
        truncated_texts = [self._truncate_text(text, 'titan_text') for text in texts]
        
        # Titan은 배치를 지원하지 않으므로 개별 호출을 병렬로 처리
        import asyncio
        tasks = [self.embed_text(text) for text in truncated_texts]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def embed_multilingual(self, text: str) -> List[float]:
        """Cohere Multilingual 임베딩"""
        text = self._truncate_text(text, 'cohere_multilingual')
        return await self._invoke_embedding(
            settings.embedding_models['cohere_multilingual'],
            {
                "texts": [text],
                "input_type": "search_document"
            }
        )
    
    async def embed_multilingual_batch(self, texts: List[str]) -> List[List[float]]:
        """Cohere Multilingual 배치 임베딩"""
        if not texts:
            return []
        
        # 텍스트 길이 제한 적용
        truncated_texts = [self._truncate_text(text, 'cohere_multilingual') for text in texts]
        
        # Cohere는 배치를 지원하므로 한 번에 처리
        try:
            response_body = await self._invoke_embedding_raw(
                settings.embedding_models['cohere_multilingual'],
                {
                    "texts": truncated_texts,
                    "input_type": "search_document"
                }
            )
            return response_body.get('embeddings', [])
        except Exception as e:
            logger.error(f"Batch embedding failed: {str(e)}")
            # 실패 시 개별 처리로 fallback
            import asyncio
            tasks = [self.embed_multilingual(text) for text in truncated_texts]
            return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def embed_multimodal(self, content: str) -> List[float]:
        """Nova Multimodal 임베딩"""
        content = self._truncate_text(content, 'nova_multimodal')
        return await self._invoke_embedding(
            settings.embedding_models['nova_multimodal'],
            {"inputText": content}  # Nova Multimodal 요청 형식
        )
    
    async def embed_cohere_v4(self, content: str) -> List[float]:
        """Cohere v4 임베딩"""
        content = self._truncate_text(content, 'cohere_v4')
        return await self._invoke_embedding(
            settings.embedding_models['cohere_v4'],
            {
                "texts": [content],
                "input_type": "search_document"
            }
        )
    
    async def _invoke_embedding(self, model_id: str, body: dict) -> List[float]:
        """임베딩 모델 호출"""
        response_body = await self._invoke_embedding_raw(model_id, body)
        
        # 모델별 응답 파싱
        if "titan" in model_id:
            return response_body.get('embedding', [])
        elif "cohere" in model_id:
            embeddings = response_body.get('embeddings', [])
            return embeddings[0] if embeddings else []
        else:
            raise EmbeddingError(f"Unknown embedding model: {model_id}")
    
    async def _invoke_embedding_raw(self, model_id: str, body: dict) -> dict:
        """임베딩 모델 원시 호출 (응답 파싱 없음)"""
        try:
            logger.debug(f"Invoking embedding model: {model_id}")
            
            # 입력 검증: texts 배열의 각 요소가 문자열인지 확인
            if "texts" in body:
                texts = body["texts"]
                if isinstance(texts, list):
                    for i, text in enumerate(texts):
                        if not isinstance(text, str):
                            logger.warning(f"Converting non-string text at index {i}: {type(text)}")
                            body["texts"][i] = str(text)
            
            # inputText 검증
            if "inputText" in body and not isinstance(body["inputText"], str):
                logger.warning(f"Converting non-string inputText: {type(body['inputText'])}")
                body["inputText"] = str(body["inputText"])
            
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType='application/json'
            )
            
            return json.loads(response['body'].read())
                
        except Exception as e:
            logger.error(f"Embedding generation failed for {model_id}: {str(e)}")
            raise EmbeddingError(f"Failed to generate embedding: {str(e)}")