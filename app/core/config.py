from pydantic_settings import BaseSettings
from typing import List, Dict, Any
import os
from dotenv import load_dotenv
from pathlib import Path

# .env 파일 로드 (현재 파일 기준으로 프로젝트 루트 찾기)
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

class Settings(BaseSettings):
    # API Settings
    api_title: str = "Prompt Evaluation API"
    api_version: str = "0.1.0"
    
    # AWS Settings
    aws_region: str = "us-east-1"  # Bedrock 모델용 (US East)
    aws_region_sqs_ddb: str = "ap-northeast-2"  # SQS/DynamoDB용 (Seoul)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    
    # SQS & DynamoDB Settings
    sqs_queue_url: str = ""
    ddb_table_name: str = "FromProm_Table"
    
    # Perplexity Settings
    perplexity_api_key: str = ""
    perplexity_api_key_2: str = ""
    perplexity_model: str = "sonar-pro"
    
    @property
    def perplexity_api_keys(self) -> List[str]:
        """사용 가능한 Perplexity API 키들 반환"""
        keys = []
        if self.perplexity_api_key:
            keys.append(self.perplexity_api_key)
        if self.perplexity_api_key_2:
            keys.append(self.perplexity_api_key_2)
        return keys
    
    # Model Configuration
    default_models: Dict[str, str] = {
        "type_a": "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "type_b_text": "anthropic.claude-3-haiku-20240307-v1:0",
        "type_b_image": "amazon.nova-canvas-v1:0"
    }
    
    # Embedding Models
    embedding_models: Dict[str, str] = {
        "titan_text": "amazon.titan-embed-text-v2:0",
        "cohere_multilingual": "cohere.embed-multilingual-v3",
        "nova_multimodal": "amazon.nova-2-multimodal-embeddings-v1:0",
        "cohere_v4": "cohere.embed-english-v3.0"
    }
    
    # Judge Model (저렴한 모델)
    judge_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    
    # Scoring Weights
    weights: Dict[str, Dict[str, float]] = {
        "type_a": {
            "token_usage": 0.15,
            "information_density": 0.20,
            "consistency": 0.20,
            "model_variance": 0.15,
            "hallucination": 0.15,
            "relevance": 0.15
        },
        "type_b_text": {
            "token_usage": 0.25,
            "information_density": 0.25,
            "model_variance": 0.25,
            "relevance": 0.25
        },
        "type_b_image": {
            "token_usage": 0.30,
            "consistency": 0.30,
            "model_variance": 0.20,
            "relevance": 0.20
        }
    }
    
    # 모델 패밀리 매핑 (선택한 모델 -> 비교 모델들)
    model_families: Dict[str, List[str]] = {
        # GPT OSS (2개)
        "openai.gpt-oss-120b-1:0": ["openai.gpt-oss-20b-1:0"],
        "openai.gpt-oss-20b-1:0": ["openai.gpt-oss-120b-1:0"],
        
        # Claude (3개) - Sonnet 4.5와 3.5 v2만 ARN 필요
        "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0": [
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0"
        ],
        "anthropic.claude-3-5-sonnet-20240620-v1:0": [
            "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0"
        ],
        "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0": [
            "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "anthropic.claude-3-5-sonnet-20240620-v1:0"
        ],
        "anthropic.claude-3-haiku-20240307-v1:0": [
            "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "anthropic.claude-3-5-sonnet-20240620-v1:0"
        ],
        
        # Gemma (3개)
        "google.gemma-3-27b-it-v1:0": [
            "google.gemma-3-12b-it-v1:0",
            "google.gemma-3-4b-it-v1:0"
        ],
        "google.gemma-3-12b-it-v1:0": [
            "google.gemma-3-27b-it-v1:0",
            "google.gemma-3-4b-it-v1:0"
        ],
        "google.gemma-3-4b-it-v1:0": [
            "google.gemma-3-27b-it-v1:0",
            "google.gemma-3-12b-it-v1:0"
        ],
        
        # 이미지 모델 (2개)
        "amazon.titan-image-generator-v2:0": ["amazon.nova-canvas-v1:0"],
        "amazon.nova-canvas-v1:0": ["amazon.titan-image-generator-v2:0"]
    }
    
    # Consistency Parameters
    alpha: float = 0.2  # centroid 계산에서 max penalty 가중치
    
    # Information Density Weights
    density_weights: Dict[str, float] = {
        "unigram": 0.5,
        "bigram": 0.5
    }
    
    # Database
    database_url: str = "sqlite:///./prompt_eval.db"
    
    # Storage Backend
    storage_backend: str = "sqlite"  # "sqlite" (기본) or "s3" or "dynamodb_s3"
    s3_bucket_name: str = "prompt-eval-bucket"
    table_name: str = "prompt-evaluations"
    
    # Cache Settings
    cache_enabled: bool = True
    cache_ttl: int = 3600  # 1 hour
    
    # Hybrid Cache Settings
    memory_cache_size: int = 1000  # 메모리 캐시 최대 항목 수
    cache_fact_check_ttl: int = 30 * 24 * 3600  # Fact check 캐시 TTL (30일)
    dynamodb_cache_table: str = "fact-check-cache"  # DynamoDB 캐시 테이블명
    dynamodb_cache_enabled: bool = True  # DynamoDB 캐시 사용 여부
    dynamodb_batch_size: int = 25  # DynamoDB 배치 저장 크기 (최대 25)
    dynamodb_batch_interval: int = 300  # DynamoDB 배치 저장 간격 (초, 5분)
    
    # Mock Mode (테스트용)
    mock_mode: bool = True  # AWS 없이 테스트할 때 True
    
    # Private Deployment Settings
    private_mode: bool = False  # 프라이빗 환경 모드
    vpc_endpoint_bedrock: str = ""  # VPC Endpoint for Bedrock
    vpc_endpoint_s3: str = ""  # VPC Endpoint for S3
    vpc_endpoint_dynamodb: str = ""  # VPC Endpoint for DynamoDB
    vpc_endpoint_sqs: str = ""  # VPC Endpoint for SQS
    
    # Self-hosted Model Settings (완전 프라이빗 모드용)
    self_hosted_mode: bool = False
    local_model_endpoint: str = "http://localhost:8080"  # 로컬 모델 서버
    local_embedding_endpoint: str = "http://localhost:8081"  # 로컬 임베딩 서버
    
    class Config:
        env_file = ".env"

settings = Settings()