import logging
from typing import Dict, Any, Optional
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, EvaluationResult, PromptType
from app.core.config import settings

logger = logging.getLogger(__name__)

class AggregateStage:
    """평가 결과 집계 단계"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(
        self, 
        prompt_type: PromptType, 
        metric_scores: Dict[str, Optional[MetricScore]]
    ) -> EvaluationResult:
        """
        타입별 평가 지표를 집계하여 EvaluationResult 생성
        """
        logger.info(f"Aggregating metrics for {prompt_type}")
        
        try:
            # 각 지표별 점수 로깅
            for metric_name, score_obj in metric_scores.items():
                if score_obj is not None:
                    logger.info(f"{metric_name}: {score_obj.score:.3f}")
                else:
                    logger.warning(f"{metric_name}: No score available")
            
            logger.info("Aggregation completed")
            
            # EvaluationResult 생성 (final_score 없음)
            return EvaluationResult(
                token_usage=metric_scores.get('token_usage'),
                information_density=metric_scores.get('information_density'),
                consistency=metric_scores.get('consistency'),
                model_variance=metric_scores.get('model_variance'),
                hallucination=metric_scores.get('hallucination'),
                relevance=metric_scores.get('relevance')
            )
            
        except Exception as e:
            logger.error(f"Aggregation failed: {str(e)}")
            # 실패시 기본 결과 반환
            return EvaluationResult()