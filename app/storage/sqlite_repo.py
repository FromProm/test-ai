import json
import uuid
import aiosqlite
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.storage.repo import BaseRepository
from app.core.schemas import JobResponse, JobStatus, PromptType, ExampleInput, EvaluationResult
from app.core.errors import StorageError

logger = logging.getLogger(__name__)

class SQLiteRepository(BaseRepository):
    """SQLite 기반 저장소"""
    
    def __init__(self, db_path: str = "prompt_eval.db"):
        self.db_path = db_path
        self.db = None
    
    async def initialize(self):
        """데이터베이스 초기화"""
        try:
            self.db = await aiosqlite.connect(self.db_path)
            await self._create_tables()
            logger.info(f"SQLite database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            raise StorageError(f"Failed to initialize database: {str(e)}")
    
    async def close(self):
        """데이터베이스 연결 종료"""
        if self.db:
            await self.db.close()
    
    async def _create_tables(self):
        """테이블 생성"""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                prompt TEXT NOT NULL,
                prompt_type TEXT NOT NULL,
                example_inputs TEXT NOT NULL,
                recommended_model TEXT,
                repeat_count INTEGER NOT NULL,
                result TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self.db.commit()
    
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """작업 생성"""
        try:
            job_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            
            await self.db.execute("""
                INSERT INTO jobs (
                    id, status, prompt, prompt_type, example_inputs,
                    recommended_model, repeat_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                JobStatus.PENDING.value,
                job_data['prompt'],
                job_data['prompt_type'],
                json.dumps([inp.model_dump() if hasattr(inp, 'model_dump') else inp for inp in job_data['example_inputs']]),
                job_data.get('recommended_model'),
                job_data['repeat_count'],
                now,
                now
            ))
            await self.db.commit()
            
            logger.info(f"Job created: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Job creation failed: {str(e)}")
            raise StorageError(f"Failed to create job: {str(e)}")
    
    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """작업 조회"""
        try:
            cursor = await self.db.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            return self._row_to_job_response(row)
            
        except Exception as e:
            logger.error(f"Job retrieval failed: {str(e)}")
            raise StorageError(f"Failed to get job: {str(e)}")
    
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """작업 업데이트"""
        try:
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                if key == 'result' and value:
                    set_clauses.append("result = ?")
                    values.append(json.dumps(value.model_dump()))
                elif key == 'status':
                    set_clauses.append("status = ?")
                    # JobStatus enum인 경우 .value로 변환
                    values.append(value.value if hasattr(value, 'value') else value)
                elif key == 'error_message':
                    set_clauses.append("error_message = ?")
                    values.append(value)
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at = ?")
            values.append(datetime.utcnow().isoformat())
            values.append(job_id)
            
            query = f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?"
            await self.db.execute(query, values)
            await self.db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Job update failed: {str(e)}")
            raise StorageError(f"Failed to update job: {str(e)}")
    
    async def list_jobs(self, page: int = 1, size: int = 10, request_id: Optional[str] = None) -> List[JobResponse]:
        """작업 목록 조회"""
        try:
            offset = (page - 1) * size
            
            if request_id:
                cursor = await self.db.execute(
                    "SELECT * FROM jobs WHERE id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (request_id, size, offset)
                )
            else:
                cursor = await self.db.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (size, offset)
                )
            
            rows = await cursor.fetchall()
            
            return [self._row_to_job_response(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Job listing failed: {str(e)}")
            raise StorageError(f"Failed to list jobs: {str(e)}")
    
    async def count_jobs(self, request_id: Optional[str] = None) -> int:
        """전체 작업 수"""
        try:
            if request_id:
                cursor = await self.db.execute("SELECT COUNT(*) FROM jobs WHERE id = ?", (request_id,))
            else:
                cursor = await self.db.execute("SELECT COUNT(*) FROM jobs")
            
            row = await cursor.fetchone()
            return row[0] if row else 0
            
        except Exception as e:
            logger.error(f"Job counting failed: {str(e)}")
            raise StorageError(f"Failed to count jobs: {str(e)}")
    
    def _row_to_job_response(self, row) -> JobResponse:
        """데이터베이스 행을 JobResponse로 변환"""
        example_inputs_data = json.loads(row[4])
        example_inputs = [ExampleInput(**inp) for inp in example_inputs_data]
        
        result = None
        if row[7]:  # result column
            result_data = json.loads(row[7])
            result = EvaluationResult(**result_data)
        
        return JobResponse(
            request_id=row[0],
            status=JobStatus(row[1]),
            prompt=row[2],
            prompt_type=PromptType(row[3]),
            example_inputs=example_inputs,
            recommended_model=row[5],
            repeat_count=row[6],
            result=result,
            error_message=row[8],
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10])
        )
    
    # ============================================
    # 새 스키마용 저장 메서드 (로컬 테스트용)
    # ============================================
    
    async def save_completed_job(
        self,
        job: 'JobResponse',
        title: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        완료된 Job을 S3 + DynamoDB에 저장
        """
        import os
        import boto3
        from decimal import Decimal
        from app.core.schemas import convert_job_to_dynamodb_record, create_s3_examples_data
        from app.core.config import settings
        
        def convert_floats(obj):
            """float를 Decimal로 변환"""
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: convert_floats(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats(item) for item in obj]
            return obj
        
        try:
            prompt_id = job.request_id
            
            # 1. 로컬에도 백업 저장
            output_dir = f"outputs/{prompt_id}"
            os.makedirs(output_dir, exist_ok=True)
            
            # examples.json 생성
            s3_examples_data = create_s3_examples_data(job)
            examples_path = f"{output_dir}/examples.json"
            with open(examples_path, 'w', encoding='utf-8') as f:
                json.dump(s3_examples_data.model_dump(), f, ensure_ascii=False, indent=2)
            
            # DynamoDB 형식 레코드 생성
            dynamodb_record = convert_job_to_dynamodb_record(
                job=job,
                title=title,
                description=description,
                user_id=user_id,
                s3_bucket=settings.s3_bucket_name
            )
            
            record_path = f"{output_dir}/dynamodb_record.json"
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(dynamodb_record.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
            
            logger.info(f"Local backup saved: {output_dir}")
            
            s3_url = None
            dynamodb_pk = None
            
            # AWS 클라이언트 생성
            if settings.aws_access_key_id:
                # 2. S3에 업로드
                try:
                    s3_client = boto3.client(
                        's3',
                        region_name=settings.aws_region,
                        aws_access_key_id=settings.aws_access_key_id,
                        aws_secret_access_key=settings.aws_secret_access_key
                    )
                    
                    s3_key = f"prompts/{prompt_id}/examples.json"
                    s3_client.put_object(
                        Bucket=settings.s3_bucket_name,
                        Key=s3_key,
                        Body=json.dumps(s3_examples_data.model_dump(), ensure_ascii=False, indent=2),
                        ContentType='application/json'
                    )
                    
                    s3_url = f"s3://{settings.s3_bucket_name}/{s3_key}"
                    logger.info(f"S3 upload success: {s3_url}")
                    
                except Exception as s3_error:
                    logger.warning(f"S3 upload failed: {str(s3_error)}")
                
                # 3. DynamoDB에 저장
                try:
                    dynamodb = boto3.resource(
                        'dynamodb',
                        region_name=settings.aws_region,
                        aws_access_key_id=settings.aws_access_key_id,
                        aws_secret_access_key=settings.aws_secret_access_key
                    )
                    
                    table = dynamodb.Table(settings.table_name)
                    item = dynamodb_record.model_dump(by_alias=True)
                    item = convert_floats(item)
                    
                    table.put_item(Item=item)
                    dynamodb_pk = dynamodb_record.pk
                    logger.info(f"DynamoDB save success: PK={dynamodb_pk}")
                    
                except Exception as ddb_error:
                    logger.warning(f"DynamoDB save failed: {str(ddb_error)}")
            
            return {
                "success": True,
                "prompt_id": prompt_id,
                "local_path": output_dir,
                "s3_url": s3_url,
                "dynamodb_pk": dynamodb_pk
            }
            
        except Exception as e:
            logger.error(f"Failed to save completed job: {str(e)}")
            raise StorageError(f"Failed to save completed job: {str(e)}")