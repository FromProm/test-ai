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
    
    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
    
    async def embed_text(self, text: str) -> List[float]:
        """Titan Text 임베딩"""
        return await self._invoke_embedding(
            settings.embedding_models['titan_text'],
            {"inputText": text}
        )
    
    async def embed_multilingual(self, text: str) -> List[float]:
        """Cohere Multilingual 임베딩"""
        return await self._invoke_embedding(
            settings.embedding_models['cohere_multilingual'],
            {
                "texts": [text],
                "input_type": "search_document"
            }
        )
    
    async def embed_multimodal(self, content: str) -> List[float]:
        """Nova Multimodal 임베딩"""
        return await self._invoke_embedding(
            settings.embedding_models['nova_multimodal'],
            {"inputText": content}  # Nova Multimodal 요청 형식
        )
    
    async def embed_cohere_v4(self, content: str) -> List[float]:
        """Cohere v4 임베딩"""
        return await self._invoke_embedding(
            settings.embedding_models['cohere_v4'],
            {
                "texts": [content],
                "input_type": "search_document"
            }
        )
    
    async def _invoke_embedding(self, model_id: str, body: dict) -> List[float]:
        """임베딩 모델 호출"""
        try:
            logger.debug(f"Invoking embedding model: {model_id}")
            
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            
            # 모델별 응답 파싱
            if "titan" in model_id:
                return response_body.get('embedding', [])
            elif "cohere" in model_id:
                embeddings = response_body.get('embeddings', [])
                return embeddings[0] if embeddings else []
            else:
                raise EmbeddingError(f"Unknown embedding model: {model_id}")
                
        except Exception as e:
            logger.error(f"Embedding generation failed for {model_id}: {str(e)}")
            raise EmbeddingError(f"Failed to generate embedding: {str(e)}")