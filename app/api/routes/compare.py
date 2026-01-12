import logging
from fastapi import APIRouter, HTTPException

from app.core.schemas import CompareRequest, CompareResponse, JobCreateRequest
from app.orchestrator.context import ExecutionContext
from app.orchestrator.pipeline import Orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])

def get_context():
    from app.main import context
    return context

@router.post("/compare", response_model=CompareResponse)
async def compare_models(request: CompareRequest):
    """모델/버전 비교"""
    try:
        context = get_context()
        orchestrator = Orchestrator(context)
        
        # 모델 A로 평가
        request_a = JobCreateRequest(
            prompt=request.prompt,
            example_inputs=request.example_inputs,
            prompt_type=request.prompt_type,
            recommended_model=request.model_a,
            repeat_count=5
        )
        result_a = await orchestrator.run(request_a)
        
        # 모델 B로 평가
        request_b = JobCreateRequest(
            prompt=request.prompt,
            example_inputs=request.example_inputs,
            prompt_type=request.prompt_type,
            recommended_model=request.model_b,
            repeat_count=5
        )
        result_b = await orchestrator.run(request_b)
        
        # 편차 계산 (각 지표별 평균 편차)
        variance_score = 0.0
        count = 0
        
        for metric in ['token_usage', 'information_density', 'consistency', 'model_variance', 'hallucination', 'relevance']:
            score_a = getattr(result_a, metric)
            score_b = getattr(result_b, metric)
            if score_a and score_b:
                variance_score += abs(score_a.score - score_b.score)
                count += 1
        
        if count > 0:
            variance_score = variance_score / count / 100  # 0-1 범위로 정규화
        
        return CompareResponse(
            model_a=request.model_a,
            model_b=request.model_b,
            model_a_result=result_a,
            model_b_result=result_b,
            variance_score=variance_score
        )
        
    except Exception as e:
        logger.error(f"Model comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))