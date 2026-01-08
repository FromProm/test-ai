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
    # ===== Type A, Type B 글 모델들 =====
    
    # GPT OSS 모델들
    GPT_OSS_120B = "openai.gpt-oss-120b-1:0"
    GPT_OSS_20B = "openai.gpt-oss-20b-1:0"
    
    # Claude 모델들
    CLAUDE_SONNET_4_5 = "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    CLAUDE_3_5_SONNET = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    CLAUDE_3_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"
    
    # Gemma 모델들
    GEMMA_3_27B = "google.gemma-3-27b-it-v1:0"
    GEMMA_3_12B = "google.gemma-3-12b-it-v1:0"
    GEMMA_3_4B = "google.gemma-3-4b-it-v1:0"
    
    # ===== Type B 이미지 모델들 =====
    TITAN_IMAGE_V2 = "amazon.titan-image-generator-v2:0"
    NOVA_CANVAS = "amazon.nova-canvas-v1:0"

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
    example_inputs: List[ExampleInput] = Field(..., description="예시 입력들 (개수 제한 없음)")
    prompt_type: PromptType = Field(..., description="프롬프트 타입")
    recommended_model: Optional[RecommendedModel] = Field(None, description="권장 모델 (Claude: 글 타입, Nova: 이미지 타입)")
    repeat_count: int = Field(5, ge=1, le=10, description="반복 실행 횟수")
    # WAS 연동용 추가 필드
    title: Optional[str] = Field(None, description="프롬프트 제목 (WAS 전달용)")
    description: Optional[str] = Field(None, description="프롬프트 설명 (WAS 전달용)")
    user_id: Optional[str] = Field(None, description="사용자 ID (SB에서 전달)")

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
    execution_results: Optional[Dict[str, Any]] = Field(None, description="실제 AI 출력 결과들")
    feedback: Optional[Dict[str, Any]] = Field(None, description="프롬프트 개선 피드백")

class JobResponse(BaseModel):
    request_id: str = Field(..., description="요청 고유 ID (UUID)")
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


# ============================================
# DynamoDB/WAS 전달용 스키마
# ============================================

class PromptInfo(BaseModel):
    """프롬프트 기본 정보"""
    title: str = Field(..., description="프롬프트 제목")
    content: str = Field(..., description="프롬프트 내용")
    description: Optional[str] = Field(None, description="프롬프트 설명")
    prompt_type: PromptType = Field(..., description="프롬프트 타입")
    example_inputs: List[ExampleInput] = Field(..., description="예시 입력들")
    recommended_model: Optional[str] = Field(None, description="권장 모델")


class EvaluationMetrics(BaseModel):
    """평가 지표 결과"""
    token_usage: Optional[float] = Field(None, description="토큰 사용량 점수")
    information_density: Optional[float] = Field(None, description="정보 밀도 점수")
    consistency: Optional[float] = Field(None, description="일관성 점수")
    model_variance: Optional[float] = Field(None, description="모델 편차 점수")
    hallucination: Optional[float] = Field(None, description="환각 탐지 점수")
    relevance: Optional[float] = Field(None, description="관련성 점수")


class DynamoDBPromptRecord(BaseModel):
    """DynamoDB 저장용 프롬프트 레코드"""
    model_config = ConfigDict(populate_by_name=True)
    
    # DynamoDB Keys
    pk: str = Field(..., alias="PK", description="파티션 키: PROMPT#{prompt_id}")
    sk: str = Field(default="METADATA", alias="SK", description="정렬 키: METADATA (고정)")
    
    # GSI Keys
    gsi1_pk: str = Field(default="USER_PROMPT_LIST", alias="GSI1_PK", description="GSI1 파티션 키 (고정)")
    gsi1_sk: Optional[str] = Field(None, alias="GSI1_SK", description="GSI1 정렬 키: USER#{user_id}#{created_at}")
    
    # 타입 구분
    type: str = Field(default="PROMPT", alias="Type", description="레코드 타입 (고정)")
    
    # 사용자 정보 (SB에서 전달받음)
    create_user: Optional[str] = Field(None, description="생성자: USER#{user_id}")
    
    # 프롬프트 정보
    title: str = Field(..., description="프롬프트 제목")
    content: str = Field(..., description="프롬프트 내용")
    description: Optional[str] = Field(None, description="프롬프트 설명")
    prompt_type: str = Field(..., description="프롬프트 타입")
    
    # 예시 입력-출력 쌍
    examples: List[Dict[str, Any]] = Field(..., description="예시 입력-출력 쌍")
    examples_s3_url: Optional[str] = Field(None, description="S3 저장 URL")
    
    recommended_model: Optional[str] = Field(None, description="권장 모델")
    
    # 평가 지표 결과
    evaluation_metrics: EvaluationMetrics = Field(..., description="평가 지표")
    
    # 메타 정보
    status: str = Field(default="COMPLETED", description="상태")
    created_at: str = Field(..., description="생성 일시 (ISO 8601)")
    updated_at: str = Field(..., description="수정 일시 (ISO 8601)")
    
    # 통계 (초기값)
    like_count: int = Field(default=0, description="좋아요 수")
    comment_count: int = Field(default=0, description="댓글 수")
    bookmark_count: int = Field(default=0, description="북마크 수")
    is_public: bool = Field(default=False, description="공개 여부")


# S3 저장용 스키마
class ExamplePair(BaseModel):
    """예시 입력-출력 쌍"""
    index: int = Field(..., description="예시 인덱스 (0, 1, 2)")
    input: Dict[str, Any] = Field(..., description="예시 입력")
    output: Optional[str] = Field(None, description="예시 출력 (텍스트)")
    output_s3_url: Optional[str] = Field(None, description="예시 출력 S3 URL (이미지)")


class S3ExamplesData(BaseModel):
    """S3 저장용 예시 데이터"""
    prompt_id: str = Field(..., description="프롬프트 ID")
    prompt: str = Field(..., description="고정 입력 프롬프트")
    prompt_type: str = Field(..., description="프롬프트 타입")
    examples: List[ExamplePair] = Field(..., description="예시 입력-출력 쌍 목록")
    created_at: str = Field(..., description="생성 일시")


def convert_job_to_dynamodb_record(
    job: JobResponse,
    title: str,
    description: Optional[str] = None,
    user_id: Optional[str] = None,
    s3_bucket: Optional[str] = None
) -> DynamoDBPromptRecord:
    """JobResponse를 DynamoDB 레코드로 변환"""
    
    now = datetime.utcnow().isoformat() + "Z"
    created_at_str = job.created_at.isoformat() + "Z"
    
    # 평가 지표 추출
    metrics = EvaluationMetrics(
        token_usage=job.result.token_usage.score if job.result and job.result.token_usage else None,
        information_density=job.result.information_density.score if job.result and job.result.information_density else None,
        consistency=job.result.consistency.score if job.result and job.result.consistency else None,
        model_variance=job.result.model_variance.score if job.result and job.result.model_variance else None,
        hallucination=job.result.hallucination.score if job.result and job.result.hallucination else None,
        relevance=job.result.relevance.score if job.result and job.result.relevance else None
    )
    
    # GSI1_SK 생성 (user_id가 있을 때만) - created_at 사용
    gsi1_sk = None
    create_user = None
    if user_id:
        gsi1_sk = f"USER#{user_id}#{created_at_str}"
        create_user = f"USER#{user_id}"
    
    # 예시 입력-출력 쌍 생성
    examples = []
    executions = job.result.execution_results.get('executions', []) if job.result and job.result.execution_results else []
    
    for i, example_input in enumerate(job.example_inputs):
        # 해당 입력의 출력 찾기
        output = None
        output_s3_url = None
        
        for exec_data in executions:
            if exec_data.get('input_index') == i:
                outputs = exec_data.get('outputs', [])
                if outputs:
                    # 첫 번째 출력 사용 (대표 출력)
                    if job.prompt_type == PromptType.TYPE_B_IMAGE:
                        # 이미지는 S3 URL
                        if s3_bucket:
                            output_s3_url = f"s3://{s3_bucket}/prompts/{job.request_id}/images/output_{i}.png"
                    else:
                        # 텍스트는 직접 저장
                        output = outputs[0]
                break
        
        example_pair = {
            "index": i,
            "input": example_input.model_dump(),
        }
        
        if job.prompt_type == PromptType.TYPE_B_IMAGE:
            example_pair["output_s3_url"] = output_s3_url
        else:
            example_pair["output"] = output
        
        examples.append(example_pair)
    
    # S3 URL 생성
    examples_s3_url = None
    if s3_bucket:
        if job.prompt_type == PromptType.TYPE_B_IMAGE:
            examples_s3_url = f"s3://{s3_bucket}/prompts/{job.request_id}/images/"
        else:
            examples_s3_url = f"s3://{s3_bucket}/prompts/{job.request_id}/examples.json"
    
    return DynamoDBPromptRecord(
        pk=f"PROMPT#{job.request_id}",
        sk="METADATA",
        gsi1_pk="USER_PROMPT_LIST",
        gsi1_sk=gsi1_sk,
        type="PROMPT",
        create_user=create_user,
        title=title,
        content=job.prompt,
        description=description,
        prompt_type=job.prompt_type.value,
        examples=examples,
        examples_s3_url=examples_s3_url,
        recommended_model=job.recommended_model.value if job.recommended_model else None,
        evaluation_metrics=metrics,
        status=job.status.value,
        created_at=job.created_at.isoformat() + "Z",
        updated_at=now
    )


def create_s3_examples_data(job: JobResponse) -> S3ExamplesData:
    """S3 저장용 예시 데이터 생성"""
    
    examples = []
    executions = job.result.execution_results.get('executions', []) if job.result and job.result.execution_results else []
    
    for i, example_input in enumerate(job.example_inputs):
        output = None
        output_s3_url = None
        
        for exec_data in executions:
            if exec_data.get('input_index') == i:
                outputs = exec_data.get('outputs', [])
                if outputs:
                    if job.prompt_type == PromptType.TYPE_B_IMAGE:
                        output_s3_url = f"images/output_{i}.png"
                    else:
                        output = outputs[0]
                break
        
        example_pair = ExamplePair(
            index=i,
            input=example_input.model_dump(),
            output=output,
            output_s3_url=output_s3_url
        )
        examples.append(example_pair)
    
    return S3ExamplesData(
        prompt_id=job.request_id,
        prompt=job.prompt,
        prompt_type=job.prompt_type.value,
        examples=examples,
        created_at=datetime.utcnow().isoformat() + "Z"
    )
