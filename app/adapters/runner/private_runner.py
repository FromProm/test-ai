"""
프라이빗 환경용 모델 실행기
VPC Endpoints 또는 Self-hosted 모델 지원
"""
import logging
import boto3
from typing import Dict, Any
from app.adapters.runner.base import BaseRunner
from app.adapters.runner.bedrock_runner import BedrockRunner
from app.core.config import settings
import httpx
import asyncio

logger = logging.getLogger(__name__)

class PrivateRunner(BaseRunner):
    """프라이빗 환경용 모델 실행기"""
    
    def __init__(self):
        self.settings = settings
        
        if self.settings.self_hosted_mode:
            # 완전 프라이빗: 로컬 모델 서버 사용
            self.mode = "self_hosted"
            self.client = httpx.AsyncClient(
                base_url=self.settings.local_model_endpoint,
                timeout=300.0
            )
        elif self.settings.private_mode:
            # VPC 프라이빗: VPC Endpoints 사용
            self.mode = "vpc_private"
            self.bedrock_runner = self._create_vpc_bedrock_client()
        else:
            # 기본 모드: 일반 Bedrock
            self.mode = "standard"
            self.bedrock_runner = BedrockRunner()
    
    def _create_vpc_bedrock_client(self) -> BedrockRunner:
        """VPC Endpoint를 사용하는 Bedrock 클라이언트 생성"""
        runner = BedrockRunner()
        
        # VPC Endpoint URL이 설정된 경우 사용
        if self.settings.vpc_endpoint_bedrock:
            runner.client = boto3.client(
                'bedrock-runtime',
                region_name=self.settings.aws_region,
                aws_access_key_id=self.settings.aws_access_key_id or None,
                aws_secret_access_key=self.settings.aws_secret_access_key or None,
                endpoint_url=self.settings.vpc_endpoint_bedrock
            )
        
        return runner
    
    async def invoke_async(
        self, 
        model: str, 
        prompt: str, 
        input_type: str = "text",
        **kwargs
    ) -> Dict[str, Any]:
        """프라이빗 모드에 따른 모델 호출"""
        
        if self.mode == "self_hosted":
            return await self._invoke_self_hosted(model, prompt, input_type, **kwargs)
        else:
            # VPC 또는 표준 모드는 기존 Bedrock 사용
            return await self.bedrock_runner.invoke_async(model, prompt, input_type, **kwargs)
    
    async def _invoke_self_hosted(
        self, 
        model: str, 
        prompt: str, 
        input_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """로컬 모델 서버 호출"""
        try:
            # 로컬 모델 서버 API 호출
            payload = {
                "model": self._map_model_to_local(model),
                "prompt": prompt,
                "input_type": input_type,
                "max_tokens": kwargs.get('max_tokens', 1000),
                "temperature": kwargs.get('temperature', 0.7)
            }
            
            response = await self.client.post("/generate", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            return {
                "response": result.get("text", ""),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "model": model,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Self-hosted model invocation failed: {e}")
            return {
                "response": f"Error: {str(e)}",
                "input_tokens": 0,
                "output_tokens": 0,
                "model": model,
                "success": False,
                "error": str(e)
            }
    
    def _map_model_to_local(self, bedrock_model: str) -> str:
        """Bedrock 모델명을 로컬 모델명으로 매핑"""
        model_mapping = {
            "anthropic.claude-3-5-sonnet-20240620-v1:0": "llama-3.1-70b",
            "anthropic.claude-3-haiku-20240307-v1:0": "llama-3.1-8b",
            "amazon.titan-embed-text-v2:0": "sentence-transformers/all-MiniLM-L6-v2"
        }
        
        return model_mapping.get(bedrock_model, "llama-3.1-8b")
    
    async def cleanup(self):
        """리소스 정리"""
        if hasattr(self, 'client') and self.client:
            await self.client.aclose()