import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime

from app.core.schemas import JobCreateRequest, EvaluationResult, MetricScore, PromptType
from app.orchestrator.context import ExecutionContext
from app.orchestrator.stages.run_stage import RunStage
from app.orchestrator.stages.token_stage import TokenStage
from app.orchestrator.stages.density_stage import DensityStage
from app.orchestrator.stages.embed_stage import EmbedStage
from app.orchestrator.stages.consistency_stage import ConsistencyStage
from app.orchestrator.stages.relevance_stage import RelevanceStage
from app.orchestrator.stages.variance_stage import VarianceStage
from app.orchestrator.stages.judge_stage import JudgeStage
from app.orchestrator.stages.aggregate_stage import AggregateStage
from app.core.config import settings

logger = logging.getLogger(__name__)

class Orchestrator:
    """전체 파이프라인 오케스트레이터 - 유일한 진실의 소스"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        self.stages = {
            'run': RunStage(context),
            'token': TokenStage(context),
            'density': DensityStage(context),
            'embed': EmbedStage(context),
            'consistency': ConsistencyStage(context),
            'relevance': RelevanceStage(context),
            'variance': VarianceStage(context),
            'judge': JudgeStage(context),
            'aggregate': AggregateStage(context)
        }
    
    async def run(self, job_request: JobCreateRequest) -> EvaluationResult:
        """전체 파이프라인 실행"""
        logger.info(f"Starting pipeline for prompt type: {job_request.prompt_type}")
        
        try:
            # 1. 프롬프트 실행 단계
            execution_results = await self.stages['run'].execute(
                job_request.prompt,
                job_request.example_inputs,
                job_request.recommended_model,
                job_request.repeat_count
            )
            
            # 실행 결과 보존 (S3 저장용)
            self._last_execution_results = execution_results
            
            # 2. 토큰 사용량 계산
            token_score = await self.stages['token'].execute(
                job_request.prompt,
                execution_results
            )
            
            # 3. 정보 밀도 계산 (TYPE_A, TYPE_B_TEXT만)
            density_score = None
            if job_request.prompt_type in [PromptType.TYPE_A, PromptType.TYPE_B_TEXT]:
                density_score = await self.stages['density'].execute(execution_results)
            
            # 4. 임베딩 생성 (일관성, 관련성, 환각 탐지용)
            embeddings = await self.stages['embed'].execute(
                execution_results,
                job_request.example_inputs,
                job_request.prompt_type
            )
            
            # 5. 일관성 계산 (TYPE_A, TYPE_B_IMAGE)
            consistency_score = None
            if job_request.prompt_type in [PromptType.TYPE_A, PromptType.TYPE_B_IMAGE]:
                consistency_score = await self.stages['consistency'].execute(
                    embeddings['outputs']
                )
            
            # 6. 정확도 계산 (모든 타입) - AI 기반 조건 준수 평가
            relevance_score = await self.stages['relevance'].execute(
                job_request.prompt,
                job_request.example_inputs,
                execution_results,
                job_request.prompt_type
            )
            
            # 7. 환각 탐지 (TYPE_A만)
            hallucination_score = None
            if job_request.prompt_type == PromptType.TYPE_A:
                hallucination_score = await self.stages['judge'].execute(
                    job_request.example_inputs,
                    execution_results
                )
            
            # 8. 모델별 편차 (모든 타입)
            variance_score = await self.stages['variance'].execute(
                job_request.prompt,
                job_request.example_inputs,
                job_request.prompt_type,
                job_request.recommended_model
            )
            
            # 9. 최종 점수 집계
            final_result = await self.stages['aggregate'].execute(
                job_request.prompt_type,
                {
                    'token_usage': token_score,
                    'information_density': density_score,
                    'consistency': consistency_score,
                    'relevance': relevance_score,
                    'hallucination': hallucination_score,
                    'model_variance': variance_score
                }
            )
            
            # 실제 AI 출력 결과 포함
            final_result.execution_results = execution_results
            
            logger.info(f"Pipeline completed successfully. Final score: {final_result.final_score}")
            return final_result
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {str(e)}")
            raise