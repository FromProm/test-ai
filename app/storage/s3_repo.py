import json
import uuid
import boto3
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.storage.repo import BaseRepository
from app.core.schemas import JobResponse, JobStatus, PromptType, ExampleInput, EvaluationResult
from app.core.errors import StorageError
from app.core.config import settings

logger = logging.getLogger(__name__)

class S3Repository(BaseRepository):
    """S3 기반 저장소 - 프롬프트와 지표값만 저장"""
    
    def __init__(self, bucket_name: str = "prompt-eval-bucket"):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        # 메타데이터용 로컬 캐시 (실제로는 DynamoDB 사용 권장)
        self.metadata_cache = {}
    
    async def initialize(self):
        """S3 버킷 초기화"""
        try:
            # 버킷 존재 확인, 없으면 생성
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"S3 bucket created: {self.bucket_name}")
            
            logger.info(f"S3 repository initialized: {self.bucket_name}")
        except Exception as e:
            logger.error(f"S3 initialization failed: {str(e)}")
            raise StorageError(f"Failed to initialize S3: {str(e)}")
    
    async def close(self):
        """S3 연결 종료 (실제로는 필요 없음)"""
        pass
    
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """작업 생성 - 프롬프트 정보만 S3에 저장"""
        try:
            job_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            
            # 저장할 데이터 (AI 출력 제외)
            job_metadata = {
                'id': job_id,
                'status': JobStatus.PENDING.value,
                'prompt': job_data['prompt'],
                'prompt_type': job_data['prompt_type'],
                'example_inputs': [
                    {
                        'content': inp.content if hasattr(inp, 'content') else inp['content'],
                        'input_type': inp.input_type if hasattr(inp, 'input_type') else inp['input_type']
                    }
                    for inp in job_data['example_inputs']
                ],
                'recommended_model': job_data.get('recommended_model'),
                'repeat_count': job_data['repeat_count'],
                'created_at': now,
                'updated_at': now,
                # AI 출력은 저장하지 않음
                'ai_outputs_stored': False
            }
            
            # S3에 메타데이터 저장
            s3_key = f"jobs/{job_id}/metadata.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(job_metadata, ensure_ascii=False),
                ContentType='application/json'
            )
            
            # 로컬 캐시에도 저장
            self.metadata_cache[job_id] = job_metadata
            
            logger.info(f"Job created in S3: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Job creation failed: {str(e)}")
            raise StorageError(f"Failed to create job: {str(e)}")
    
    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """작업 조회"""
        try:
            # 로컬 캐시 먼저 확인
            if job_id in self.metadata_cache:
                job_data = self.metadata_cache[job_id]
            else:
                # S3에서 메타데이터 조회
                s3_key = f"jobs/{job_id}/metadata.json"
                try:
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
                    job_data = json.loads(response['Body'].read().decode('utf-8'))
                    self.metadata_cache[job_id] = job_data
                except self.s3_client.exceptions.NoSuchKey:
                    return None
            
            # 지표 결과 조회 (있다면)
            result = None
            if job_data.get('status') == JobStatus.COMPLETED.value:
                result = await self._get_evaluation_result(job_id)
            
            return self._dict_to_job_response(job_data, result)
            
        except Exception as e:
            logger.error(f"Job retrieval failed: {str(e)}")
            raise StorageError(f"Failed to get job: {str(e)}")
    
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """작업 업데이트"""
        try:
            # 현재 데이터 조회
            current_job = await self.get_job(job_id)
            if not current_job:
                return False
            
            # 메타데이터 업데이트
            job_data = self.metadata_cache.get(job_id, {})
            
            if 'status' in updates:
                job_data['status'] = updates['status']
            
            if 'error_message' in updates:
                job_data['error_message'] = updates['error_message']
            
            job_data['updated_at'] = datetime.utcnow().isoformat()
            
            # 지표 결과 저장 (AI 출력은 제외)
            if 'result' in updates and updates['result']:
                await self._save_evaluation_result(job_id, updates['result'])
            
            # S3에 메타데이터 업데이트
            s3_key = f"jobs/{job_id}/metadata.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(job_data, ensure_ascii=False),
                ContentType='application/json'
            )
            
            # 로컬 캐시 업데이트
            self.metadata_cache[job_id] = job_data
            
            return True
            
        except Exception as e:
            logger.error(f"Job update failed: {str(e)}")
            raise StorageError(f"Failed to update job: {str(e)}")
    
    async def list_jobs(self, page: int = 1, size: int = 10) -> List[JobResponse]:
        """작업 목록 조회 (간단 구현)"""
        try:
            # S3에서 모든 job 메타데이터 조회
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="jobs/",
                Delimiter="/"
            )
            
            jobs = []
            job_folders = response.get('CommonPrefixes', [])
            
            # 페이징 처리
            start_idx = (page - 1) * size
            end_idx = start_idx + size
            
            for folder in job_folders[start_idx:end_idx]:
                job_id = folder['Prefix'].split('/')[1]
                job = await self.get_job(job_id)
                if job:
                    jobs.append(job)
            
            # 최신순 정렬
            jobs.sort(key=lambda x: x.created_at, reverse=True)
            return jobs
            
        except Exception as e:
            logger.error(f"Job listing failed: {str(e)}")
            raise StorageError(f"Failed to list jobs: {str(e)}")
    
    async def count_jobs(self) -> int:
        """전체 작업 수"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="jobs/",
                Delimiter="/"
            )
            return len(response.get('CommonPrefixes', []))
        except Exception as e:
            logger.error(f"Job counting failed: {str(e)}")
            return 0
    
    async def _save_evaluation_result(self, job_id: str, result: EvaluationResult):
        """지표 결과만 S3에 저장 (AI 출력 제외)"""
        try:
            # 지표값만 추출 (AI 출력 데이터 제외)
            metrics_only = {
                'token_usage': result.token_usage.model_dump() if result.token_usage else None,
                'information_density': result.information_density.model_dump() if result.information_density else None,
                'consistency': result.consistency.model_dump() if result.consistency else None,
                'model_variance': result.model_variance.model_dump() if result.model_variance else None,
                'hallucination': result.hallucination.model_dump() if result.hallucination else None,
                'relevance': result.relevance.model_dump() if result.relevance else None,
                'final_score': result.final_score,
                'saved_at': datetime.utcnow().isoformat(),
                'note': 'AI outputs not stored for privacy/storage efficiency'
            }
            
            # S3에 지표만 저장
            s3_key = f"jobs/{job_id}/evaluation_result.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(metrics_only, ensure_ascii=False),
                ContentType='application/json'
            )
            
            logger.info(f"Evaluation metrics saved to S3: {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to save evaluation result: {str(e)}")
    
    async def _get_evaluation_result(self, job_id: str) -> Optional[EvaluationResult]:
        """S3에서 지표 결과 조회"""
        try:
            s3_key = f"jobs/{job_id}/evaluation_result.json"
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            metrics_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # EvaluationResult 객체로 변환
            return EvaluationResult(**metrics_data)
            
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"Failed to get evaluation result: {str(e)}")
            return None
    
    def _dict_to_job_response(self, job_data: Dict, result: Optional[EvaluationResult]) -> JobResponse:
        """딕셔너리를 JobResponse로 변환"""
        example_inputs = [
            ExampleInput(**inp) for inp in job_data['example_inputs']
        ]
        
        return JobResponse(
            id=job_data['id'],
            status=JobStatus(job_data['status']),
            prompt=job_data['prompt'],
            prompt_type=PromptType(job_data['prompt_type']),
            example_inputs=example_inputs,
            recommended_model=job_data.get('recommended_model'),
            repeat_count=job_data['repeat_count'],
            result=result,
            error_message=job_data.get('error_message'),
            created_at=datetime.fromisoformat(job_data['created_at']),
            updated_at=datetime.fromisoformat(job_data['updated_at'])
        )