import logging
from typing import Dict, Any, Optional
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, EvaluationResult, PromptType
from app.core.config import settings

logger = logging.getLogger(__name__)

class AggregateStage:
    """최종 점수 집계 단계"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(
        self, 
        prompt_type: PromptType, 
        metric_scores: Dict[str, Optional[MetricScore]]
    ) -> EvaluationResult:
        """
        타입별 가중 합산하여 최종 평가 점수 산출
        """
        logger.info(f"Aggregating final score for {prompt_type}")
        
        try:
            # 타입별 가중치 가져오기
            weights = settings.weights[prompt_type.value]
            
            # 각 지표별 점수 계산
            weighted_scores = {}
            total_weight = 0
            
            for metric_name, weight in weights.items():
                score_obj = metric_scores.get(metric_name)
                
                if score_obj is not None:
                    score = score_obj.score
                    weighted_scores[metric_name] = score * weight
                    total_weight += weight
                    logger.info(f"{metric_name}: {score:.3f} (weight: {weight}) = {score * weight:.3f}")
                else:
                    weighted_scores[metric_name] = 0.0
                    logger.warning(f"{metric_name}: No score available")
            
            # 최종 점수 계산
            if total_weight > 0:
                final_score = sum(weighted_scores.values()) / total_weight
            else:
                final_score = 0.0
            
            # 패널티 규칙 적용
            final_score = self._apply_penalty_rules(final_score, metric_scores, prompt_type)
            
            # 0-1 범위로 클리핑
            final_score = max(0.0, min(1.0, final_score))
            
            logger.info(f"Final aggregated score: {final_score:.3f}")
            
            # EvaluationResult 생성
            return EvaluationResult(
                token_usage=metric_scores.get('token_usage'),
                information_density=metric_scores.get('information_density'),
                consistency=metric_scores.get('consistency'),
                model_variance=metric_scores.get('model_variance'),
                hallucination=metric_scores.get('hallucination'),
                relevance=metric_scores.get('relevance'),
                final_score=final_score
            )
            
        except Exception as e:
            logger.error(f"Aggregation failed: {str(e)}")
            # 실패시 기본 결과 반환
            return EvaluationResult(final_score=0.0)
    
    def _apply_penalty_rules(
        self, 
        base_score: float, 
        metric_scores: Dict[str, Optional[MetricScore]], 
        prompt_type: PromptType
    ) -> float:
        """패널티 규칙 적용"""
        penalty_factor = 1.0
        
        # 환각 탐지 심각한 실패시 큰 패널티
        if prompt_type == PromptType.TYPE_A:
            hallucination_score = metric_scores.get('hallucination')
            if hallucination_score and hallucination_score.score < 0.3:
                penalty_factor *= 0.5  # 50% 감점
                logger.warning("Applied hallucination penalty: 50% reduction")
        
        # 관련성 매우 낮을 때 패널티
        relevance_score = metric_scores.get('relevance')
        if relevance_score and relevance_score.score < 0.2:
            penalty_factor *= 0.7  # 30% 감점
            logger.warning("Applied relevance penalty: 30% reduction")
        
        # 일관성 매우 낮을 때 패널티 (TYPE_A, TYPE_B_IMAGE)
        if prompt_type in [PromptType.TYPE_A, PromptType.TYPE_B_IMAGE]:
            consistency_score = metric_scores.get('consistency')
            if consistency_score and consistency_score.score < 0.3:
                penalty_factor *= 0.8  # 20% 감점
                logger.warning("Applied consistency penalty: 20% reduction")
        
        return base_score * penalty_factor