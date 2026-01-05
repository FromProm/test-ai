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
        
        # 편차 계산
        variance_score = abs(result_a.final_score - result_b.final_score)
        
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