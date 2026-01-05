import json
import logging
import boto3
from typing import Dict, Any
from app.adapters.runner.base import BaseRunner
from app.core.config import settings
from app.core.errors import ModelInvocationError

logger = logging.getLogger(__name__)

class BedrockRunner(BaseRunner):
    """AWS Bedrock 모델 실행기"""
    
    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
    
    async def invoke(
        self, 
        model: str, 
        prompt: str, 
        input_type: str = "text",
        **kwargs
    ) -> Dict[str, Any]:
        """Bedrock 모델 호출"""
        try:
            logger.info(f"Invoking model: {model}")
            
            # 모델별 요청 형식 구성
            if "anthropic.claude" in model:
                body = self._build_claude_request(prompt, **kwargs)
            elif "amazon.titan" in model:
                body = self._build_titan_request(prompt, **kwargs)
            elif "amazon.nova" in model:
                body = self._build_nova_request(model, prompt, input_type, **kwargs)
            else:
                raise ModelInvocationError(f"Unsupported model: {model}")
            
            # Bedrock 호출
            response = self.client.invoke_model(
                modelId=model,
                body=json.dumps(body),
                contentType='application/json'
            )
            
            # 응답 파싱
            response_body = json.loads(response['body'].read())
            
            # 모델별 응답 파싱
            if "anthropic.claude" in model:
                return self._parse_claude_response(response_body)
            elif "amazon.titan" in model:
                return self._parse_titan_response(response_body)
            elif "amazon.nova" in model:
                return self._parse_nova_response(response_body, model)
            
        except Exception as e:
            logger.error(f"Model invocation failed: {str(e)}")
            raise ModelInvocationError(f"Failed to invoke {model}: {str(e)}")
    
    def _build_claude_request(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Claude 요청 구성"""
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": kwargs.get('max_tokens', 1000),
            "temperature": kwargs.get('temperature', 0.7),
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    
    def _build_titan_request(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Titan 요청 구성"""
        return {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": kwargs.get('max_tokens', 1000),
                "temperature": kwargs.get('temperature', 0.7),
                "topP": kwargs.get('top_p', 0.9)
            }
        }
    
    def _parse_claude_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Claude 응답 파싱"""
        content = response.get('content', [])
        output_text = content[0].get('text', '') if content else ''
        
        usage = response.get('usage', {})
        token_usage = {
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0),
            'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
        }
        
        return {
            'output': output_text,
            'token_usage': token_usage
        }
    
    def _parse_titan_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Titan 응답 파싱"""
        results = response.get('results', [])
        output_text = results[0].get('outputText', '') if results else ''
        
        # Titan은 토큰 사용량을 직접 제공하지 않으므로 근사치 계산
        input_tokens = len(response.get('inputText', '').split()) * 1.3  # 근사치
        output_tokens = len(output_text.split()) * 1.3
        
        token_usage = {
            'input_tokens': int(input_tokens),
            'output_tokens': int(output_tokens),
            'total_tokens': int(input_tokens + output_tokens)
        }
        
        return {
            'output': output_text,
            'token_usage': token_usage
        }
    
    def _build_nova_request(self, model: str, prompt: str, input_type: str, **kwargs) -> Dict[str, Any]:
        """Nova 요청 구성"""
        if "canvas" in model:
            # Nova Canvas (이미지 생성)
            return {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": prompt,
                    "negativeText": kwargs.get('negative_prompt', ''),
                    "images": []
                },
                "imageGenerationConfig": {
                    "numberOfImages": kwargs.get('number_of_images', 1),
                    "quality": kwargs.get('quality', 'standard'),
                    "cfgScale": kwargs.get('cfg_scale', 8.0),
                    "height": kwargs.get('height', 1024),
                    "width": kwargs.get('width', 1024),
                    "seed": kwargs.get('seed', 0)
                }
            }
        else:
            raise ModelInvocationError(f"Unsupported Nova model: {model}")
    
    def _parse_nova_response(self, response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Nova 응답 파싱"""
        if "canvas" in model:
            # Nova Canvas 이미지 응답
            images = response.get('images', [])
            output_text = f"Generated {len(images)} image(s)" if images else "No images generated"
        else:
            output_text = "Unknown Nova model response"
        
        # 토큰 사용량 (Nova는 직접 제공하지 않으므로 근사치)
        input_tokens = len(prompt.split()) * 0.75 if 'prompt' in locals() else 50
        output_tokens = len(output_text.split()) * 0.75
        
        token_usage = {
            'input_tokens': int(input_tokens),
            'output_tokens': int(output_tokens),
            'total_tokens': int(input_tokens + output_tokens)
        }
        
        return {
            'output': output_text,
            'token_usage': token_usage
        }