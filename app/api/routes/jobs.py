import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Optional

from app.core.schemas import (
    JobCreateRequest, JobResponse, JobListResponse, JobStatus
)
from app.orchestrator.context import ExecutionContext
from app.orchestrator.pipeline import Orchestrator
from app.core.errors import PromptEvalError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])

# Context will be injected from main.py
def get_context():
    from app.main import context
    return context

# Context initialization will be handled in main.py

@router.post("/jobs", response_model=JobResponse)
async def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    """프롬프트 평가 작업 생성"""
    try:
        # 작업 생성
        context = get_context()
        storage = context.get_storage()
        job_id = await storage.create_job(request.model_dump())
        
        # 백그라운드에서 실행
        background_tasks.add_task(run_evaluation, job_id, request)
        
        # 생성된 작업 반환
        job = await storage.get_job(job_id)
        return job
        
    except Exception as e:
        logger.error(f"Job creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """작업 조회"""
    try:
        context = get_context()
        storage = context.get_storage()
        job = await storage.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    """작업 목록 조회"""
    try:
        context = get_context()
        storage = context.get_storage()
        jobs = await storage.list_jobs(page, size)
        total = await storage.count_jobs()
        
        return JobListResponse(
            jobs=jobs,
            total=total,
            page=page,
            size=size
        )
        
    except Exception as e:
        logger.error(f"Job listing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/{job_id}/rerun", response_model=JobResponse)
async def rerun_job(job_id: str, background_tasks: BackgroundTasks):
    """작업 재실행"""
    try:
        context = get_context()
        storage = context.get_storage()
        job = await storage.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 새 요청 객체 생성
        request = JobCreateRequest(
            prompt=job.prompt,
            example_inputs=job.example_inputs,
            prompt_type=job.prompt_type,
            recommended_model=job.recommended_model,
            repeat_count=job.repeat_count
        )
        
        # 상태 초기화
        await storage.update_job(job_id, {
            'status': JobStatus.PENDING,
            'result': None,
            'error_message': None
        })
        
        # 백그라운드에서 재실행
        background_tasks.add_task(run_evaluation, job_id, request)
        
        # 업데이트된 작업 반환
        updated_job = await storage.get_job(job_id)
        return updated_job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job rerun failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_evaluation(job_id: str, request: JobCreateRequest):
    """백그라운드 평가 실행"""
    context = get_context()
    storage = context.get_storage()
    
    try:
        # 상태 업데이트: RUNNING
        await storage.update_job(job_id, {'status': JobStatus.RUNNING})
        
        # 파이프라인 실행
        orchestrator = Orchestrator(context)
        result = await orchestrator.run(request)
        
        # 상태 업데이트: COMPLETED (결과 + 실행 결과 모두 저장)
        await storage.update_job(job_id, {
            'status': JobStatus.COMPLETED,
            'result': result,
            'execution_results': getattr(orchestrator, '_last_execution_results', None)
        })
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        
        # 상태 업데이트: FAILED
        await storage.update_job(job_id, {
            'status': JobStatus.FAILED,
            'error_message': str(e)
        })