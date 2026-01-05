from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

class PromptType(str, Enum):
    TYPE_A = "type_a"  # Information (정답/사실/근거 요구)
    TYPE_B_TEXT = "type_b_text"  # Creative 글
    TYPE_B_IMAGE = "type_b_image"  # Creative 이미지

class ClaimType(str, Enum):
    FACT_VERIFIABLE = "fact_verifiable"      # 외부 근거로 참/거짓 판정 가능
    FACT_UNVERIFIABLE = "fact_unverifiable"  # 사실처럼 보이나 검증 불가
    OPINION_JUDGEMENT = "opinion_judgement"   # 의견/평가/주관
    CREATIVE_CONTENT = "creative_content"     # 창작 설정/허구
    PREDICTION_SPECULATION = "prediction_speculation"  # 미래 예측/추정
    INSTRUCTIONAL = "instructional"           # 방법/절차 설명

class Verdict(str, Enum):
    SUPPORTED = "supported"      # 참 (근거 있음, 일치)
    REFUTED = "refuted"         # 거짓 (근거 있음, 불일치)
    INSUFFICIENT = "insufficient"  # 불충분 (근거 없음 또는 불완전)

class RecommendedModel(str, Enum):
    # Claude 모델들 (글 관련 타입용) - Bedrock 확실 지원
    CLAUDE_3_5_SONNET = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    CLAUDE_3_SONNET = "anthropic.claude-3-sonnet-20240229-v1:0"
    CLAUDE_3_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"
    
    # 이미지 생성 모델들 - Bedrock 확실 지원
    NOVA_CANVAS = "amazon.nova-canvas-v1:0"
    TITAN_IMAGE_V1 = "amazon.titan-image-generator-v1"
    TITAN_IMAGE_V2 = "amazon.titan-image-generator-v2:0"

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# Request Schemas
class ExampleInput(BaseModel):
    content: str
    input_type: Literal["text", "image"] = "text"

class JobCreateRequest(BaseModel):
    prompt: str = Field(..., description="평가할 프롬프트")
    example_inputs: List[ExampleInput] = Field(..., min_items=3, max_items=3, description="예시 입력 3개")
    prompt_type: PromptType = Field(..., description="프롬프트 타입")
    recommended_model: Optional[RecommendedModel] = Field(None, description="권장 모델 (Claude: 글 타입, Nova: 이미지 타입)")
    repeat_count: int = Field(5, ge=1, le=10, description="반복 실행 횟수")

class CompareRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_a: RecommendedModel
    model_b: RecommendedModel
    prompt: str
    example_inputs: List[ExampleInput]
    prompt_type: PromptType

# Response Schemas
class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

class MetricScore(BaseModel):
    score: float = Field(..., ge=0, le=100)
    details: Dict[str, Any] = Field(default_factory=dict)

class TokenMetricScore(BaseModel):
    """토큰 사용량 전용 스키마 (100점 제한 없음)"""
    score: float = Field(..., ge=0)
    details: Dict[str, Any] = Field(default_factory=dict)

class EvaluationResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    token_usage: Optional[TokenMetricScore] = None  # 토큰은 100점 제한 없음
    information_density: Optional[MetricScore] = None
    consistency: Optional[MetricScore] = None
    model_variance: Optional[MetricScore] = None
    hallucination: Optional[MetricScore] = None
    relevance: Optional[MetricScore] = None
    final_score: float = Field(..., ge=0, le=100)
    execution_results: Optional[Dict[str, Any]] = Field(None, description="실제 AI 출력 결과들")

class JobResponse(BaseModel):
    id: str
    status: JobStatus
    prompt: str
    prompt_type: PromptType
    example_inputs: List[ExampleInput]
    recommended_model: Optional[RecommendedModel]
    repeat_count: int
    result: Optional[EvaluationResult] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    size: int

class CompareResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_a: RecommendedModel
    model_b: RecommendedModel
    model_a_result: EvaluationResult
    model_b_result: EvaluationResult
    variance_score: float = Field(..., ge=0, le=1)

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str