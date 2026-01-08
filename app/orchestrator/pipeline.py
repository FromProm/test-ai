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
from app.orchestrator.stages.feedback_stage import FeedbackStage
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
            'aggregate': AggregateStage(context),
            'feedback': FeedbackStage(context)
        }
    
    async def run(self, job_request: JobCreateRequest) -> EvaluationResult:
        """전체 파이프라인 실행 (병렬 처리)"""
        logger.info(f"Starting pipeline for prompt type: {job_request.prompt_type}")
        
        try:
            # [1단계] 프롬프트 실행 - 출력 생성 + Variance 모델 실행 (선행 필수)
            logger.info("Step 1: Starting RunStage execution...")
            execution_results = await self.stages['run'].execute(
                job_request.prompt,
                job_request.example_inputs,
                job_request.recommended_model,
                job_request.repeat_count,
                job_request.prompt_type
            )
            logger.info("Step 1: RunStage execution completed")
            
            # 실행 결과 보존 (S3 저장용)
            self._last_execution_results = execution_results
            
            # [2단계] 임베딩 + 독립 지표들 병렬 실행
            # 임베딩은 일관성 계산에 필요하므로 함께 실행
            logger.info("Step 2: Starting parallel tasks...")
            parallel_tasks = []
            task_names = []
            
            # 토큰 계산 (항상)
            parallel_tasks.append(
                self.stages['token'].execute(job_request.prompt, execution_results)
            )
            task_names.append('token')
            
            # 정보 밀도 (TYPE_A, TYPE_B_TEXT)
            if job_request.prompt_type in [PromptType.TYPE_A, PromptType.TYPE_B_TEXT]:
                parallel_tasks.append(
                    self.stages['density'].execute(execution_results)
                )
                task_names.append('density')
            
            # 임베딩 생성 (일관성 계산용)
            parallel_tasks.append(
                self.stages['embed'].execute(
                    execution_results,
                    job_request.example_inputs,
                    job_request.prompt_type
                )
            )
            task_names.append('embed')
            
            # 정확도 계산 (모든 타입)
            parallel_tasks.append(
                self.stages['relevance'].execute(
                    job_request.prompt,
                    job_request.example_inputs,
                    execution_results,
                    job_request.prompt_type
                )
            )
            task_names.append('relevance')
            
            # 환각 탐지 (TYPE_A만)
            if job_request.prompt_type == PromptType.TYPE_A:
                parallel_tasks.append(
                    self.stages['judge'].execute(
                        job_request.example_inputs,
                        execution_results
                    )
                )
                task_names.append('judge')
            
            # 모델별 편차 (모든 타입) - 기존 출력 재사용
            parallel_tasks.append(
                self.stages['variance'].execute(
                    job_request.prompt,
                    job_request.example_inputs,
                    job_request.prompt_type,
                    job_request.recommended_model,
                    execution_results  # 기존 출력 전달
                )
            )
            task_names.append('variance')
            
            # 병렬 실행
            logger.info(f"Running {len(parallel_tasks)} tasks in parallel: {task_names}")
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            
            # 결과 매핑
            results_map = {}
            for name, result in zip(task_names, parallel_results):
                if isinstance(result, Exception):
                    logger.error(f"Task {name} failed: {str(result)}")
                    results_map[name] = None
                else:
                    results_map[name] = result
            
            # 결과 추출
            token_score = results_map.get('token')
            density_score = results_map.get('density')
            embeddings = results_map.get('embed')
            relevance_score = results_map.get('relevance')
            hallucination_score = results_map.get('judge')
            variance_score = results_map.get('variance')
            
            # [3단계] 일관성 계산 (임베딩 완료 후)
            consistency_score = None
            if job_request.prompt_type in [PromptType.TYPE_A, PromptType.TYPE_B_IMAGE]:
                if embeddings and 'outputs' in embeddings:
                    consistency_score = await self.stages['consistency'].execute(
                        embeddings['outputs']
                    )
                else:
                    logger.warning("Embeddings not available for consistency calculation")
            
            # [4단계] 최종 점수 집계
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
            
            # [5단계] 프롬프트 개선 피드백 생성
            try:
                evaluation_data = {
                    'token_usage': {'score': token_score.score if token_score else 0} if token_score else None,
                    'information_density': {'score': density_score.score if density_score else 0} if density_score else None,
                    'consistency': {'score': consistency_score.score if consistency_score else 0} if consistency_score else None,
                    'relevance': {'score': relevance_score.score if relevance_score else 0} if relevance_score else None,
                    'hallucination': {'score': hallucination_score.score if hallucination_score else 0} if hallucination_score else None,
                    'model_variance': {'score': variance_score.score if variance_score else 0} if variance_score else None,
                    'execution_results': execution_results
                }
                
                feedback = await self.stages['feedback'].execute(
                    evaluation_data,
                    prompt=job_request.prompt,
                    prompt_type=job_request.prompt_type,
                    example_inputs=job_request.example_inputs
                )
                final_result.feedback = feedback
                logger.info("Feedback generation completed")
            except Exception as e:
                logger.warning(f"Feedback generation failed: {str(e)}")
                final_result.feedback = {'error': str(e)}
            
            logger.info("Pipeline completed successfully (parallel execution)")
            return final_result
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {str(e)}")
            raise