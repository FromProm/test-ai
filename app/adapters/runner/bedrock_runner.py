import json
import logging
import boto3
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
from app.adapters.runner.base import BaseRunner
from app.core.config import settings
from app.core.errors import ModelInvocationError

logger = logging.getLogger(__name__)

class BedrockRunner(BaseRunner):
    """AWS Bedrock 모델 실행기 (병렬 처리 지원)"""
    
    def __init__(self):
        # boto3 설정 (연결 풀 크기 증가)
        from botocore.config import Config
        config = Config(
            max_pool_connections=25,  # 연결 풀 크기 증가
            retries={'max_attempts': 3}
        )
        
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            config=config
        )
        # 스레드풀 생성 (병렬 처리용)
        self.executor = ThreadPoolExecutor(max_workers=20)
    
    async def invoke(
        self, 
        model: str, 
        prompt: str, 
        input_type: str = "text",
        **kwargs
    ) -> Dict[str, Any]:
        """Bedrock 모델 호출 (비동기 병렬 처리)"""
        try:
            logger.info(f"Invoking model: {model}")
            
            # 동기 함수를 비동기로 실행
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._sync_invoke,
                model, prompt, input_type, kwargs
            )
            return result
            
        except Exception as e:
            logger.error(f"Model invocation failed for {model}: {str(e)}")
            raise ModelInvocationError(f"Failed to invoke {model}: {str(e)}")
    
    def _sync_invoke(self, model: str, prompt: str, input_type: str, kwargs: dict) -> Dict[str, Any]:
        """동기 Bedrock 호출 (스레드에서 실행)"""
        try:
            # inference profile ARN인 경우 converse API 사용
            if model.startswith("arn:aws:bedrock"):
                return self._invoke_with_converse(model, prompt, **kwargs)
            
            # 모델별 요청 형식 구성
            if "anthropic.claude" in model:
                body = self._build_claude_request(prompt, **kwargs)
            elif "openai.gpt" in model:
                body = self._build_openai_request(prompt, **kwargs)
            elif "google.gemma" in model:
                return self._invoke_with_converse(model, prompt, **kwargs)
            elif "amazon.titan" in model:
                if "image" in model:
                    # Titan Image Generator
                    body = self._build_titan_image_request(prompt, **kwargs)
                else:
                    # Titan Text
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
            elif "openai.gpt" in model:
                return self._parse_openai_response(response_body)
            elif "amazon.titan" in model:
                if "image" in model:
                    return self._parse_titan_image_response(response_body)
                else:
                    return self._parse_titan_response(response_body)
            elif "amazon.nova" in model:
                return self._parse_nova_response(response_body, model)
            
        except Exception as e:
            logger.error(f"Model invocation failed: {str(e)}")
            raise ModelInvocationError(f"Failed to invoke {model}: {str(e)}")
    
    def _invoke_with_converse(self, model_arn: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Converse API를 사용한 inference profile 호출"""
        try:
            response = self.client.converse(
                modelId=model_arn,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": kwargs.get('max_tokens', 1000),
                    "temperature": kwargs.get('temperature', 0.7)
                }
            )
            
            # 응답 파싱
            output_message = response.get('output', {}).get('message', {})
            content = output_message.get('content', [])
            output_text = content[0].get('text', '') if content else ''
            
            usage = response.get('usage', {})
            token_usage = {
                'input_tokens': usage.get('inputTokens', 0),
                'output_tokens': usage.get('outputTokens', 0),
                'total_tokens': usage.get('inputTokens', 0) + usage.get('outputTokens', 0)
            }
            
            return {
                'output': output_text,
                'token_usage': token_usage
            }
            
        except Exception as e:
            logger.error(f"Converse API failed: {str(e)}")
            raise ModelInvocationError(f"Failed to invoke with converse: {str(e)}")
    
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
    
    def _build_openai_request(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """OpenAI GPT OSS 요청 구성"""
        return {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_completion_tokens": kwargs.get('max_tokens', 1000),
            "temperature": kwargs.get('temperature', 0.7),
            "top_p": kwargs.get('top_p', 0.9)
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
    
    def _parse_openai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """OpenAI GPT OSS 응답 파싱"""
        choices = response.get('choices', [])
        output_text = ''
        if choices:
            message = choices[0].get('message', {})
            output_text = message.get('content', '')
        
        usage = response.get('usage', {})
        token_usage = {
            'input_tokens': usage.get('prompt_tokens', 0),
            'output_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0)
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
                    "negativeText": kwargs.get('negative_prompt', 'blurry, low quality, distorted')
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
    
    def _build_titan_image_request(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Titan Image Generator 요청 구성"""
        return {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
                "negativeText": kwargs.get('negative_prompt', 'blurry, low quality, distorted')
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
    
    def _parse_nova_response(self, response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Nova 응답 파싱"""
        if "canvas" in model:
            # Nova Canvas 이미지 응답
            images = response.get('images', [])
            
            if images:
                # 이미지를 파일로 저장
                import base64
                import os
                from datetime import datetime
                
                # outputs 디렉토리 생성
                output_dir = "outputs/images"
                os.makedirs(output_dir, exist_ok=True)
                
                image_paths = []
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                for i, image_data in enumerate(images):
                    # base64 디코딩
                    image_bytes = base64.b64decode(image_data)
                    
                    # 파일명 생성
                    filename = f"nova_canvas_{timestamp}_{i+1}.png"
                    filepath = os.path.join(output_dir, filename)
                    
                    # 파일 저장
                    with open(filepath, 'wb') as f:
                        f.write(image_bytes)
                    
                    image_paths.append(filepath)
                    logger.info(f"Image saved: {filepath}")
                
                output_text = f"Generated {len(images)} image(s): {', '.join(image_paths)}"
            else:
                output_text = "No images generated"
        else:
            output_text = "Unknown Nova model response"
        
        # 토큰 사용량 (Nova는 직접 제공하지 않으므로 근사치)
        input_tokens = 50  # 기본값
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
    def _parse_titan_image_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Titan Image Generator 응답 파싱"""
        images = response.get('images', [])
        
        if images:
            # 이미지를 파일로 저장
            import base64
            import os
            from datetime import datetime
            
            # outputs 디렉토리 생성
            output_dir = "outputs/images"
            os.makedirs(output_dir, exist_ok=True)
            
            image_paths = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            for i, image_data in enumerate(images):
                # base64 디코딩
                image_bytes = base64.b64decode(image_data)
                
                # 파일명 생성
                filename = f"titan_image_{timestamp}_{i+1}.png"
                filepath = os.path.join(output_dir, filename)
                
                # 파일 저장
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                
                image_paths.append(filepath)
                logger.info(f"Image saved: {filepath}")
            
            output_text = f"Generated {len(images)} image(s): {', '.join(image_paths)}"
        else:
            output_text = "No images generated"
        
        # 토큰 사용량 (Titan Image는 직접 제공하지 않으므로 근사치)
        input_tokens = 50  # 기본값
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