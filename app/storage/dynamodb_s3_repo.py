import json
import uuid
import boto3
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from app.storage.repo import BaseRepository
from app.core.schemas import JobResponse, JobStatus, PromptType, ExampleInput, EvaluationResult, MetricScore
from app.core.errors import StorageError
from app.core.config import settings

logger = logging.getLogger(__name__)

class DynamoDBS3Repository(BaseRepository):
    """DynamoDB + S3 하이브리드 저장소 - 입력/출력 분리 저장"""
    
    def __init__(self, table_name: str = "prompt-evaluations", bucket_name: str = "prompt-eval-bucket"):
        self.table_name = table_name
        self.bucket_name = bucket_name
        
        # DynamoDB 클라이언트
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        # S3 클라이언트
        self.s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        self.table = None
    
    async def initialize(self):
        """DynamoDB 테이블 및 S3 버킷 초기화"""
        try:
            # DynamoDB 테이블 생성 (없으면)
            try:
                self.table = self.dynamodb.Table(self.table_name)
                self.table.load()
            except self.dynamodb.meta.client.exceptions.ResourceNotFoundException:
                self.table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {'AttributeName': 'job_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'job_id', 'AttributeType': 'S'},
                        {'AttributeName': 'created_at', 'AttributeType': 'S'},
                        {'AttributeName': 'prompt_type', 'AttributeType': 'S'},
                        {'AttributeName': 'final_score', 'AttributeType': 'N'}
                    ],
                    GlobalSecondaryIndexes=[
                        {
                            'IndexName': 'prompt-type-score-index',
                            'KeySchema': [
                                {'AttributeName': 'prompt_type', 'KeyType': 'HASH'},
                                {'AttributeName': 'final_score', 'KeyType': 'RANGE'}
                            ],
                            'Projection': {'ProjectionType': 'ALL'},
                            'BillingMode': 'PAY_PER_REQUEST'
                        },
                        {
                            'IndexName': 'created-at-index',
                            'KeySchema': [
                                {'AttributeName': 'created_at', 'KeyType': 'HASH'}
                            ],
                            'Projection': {'ProjectionType': 'ALL'},
                            'BillingMode': 'PAY_PER_REQUEST'
                        }
                    ],
                    BillingMode='PAY_PER_REQUEST'
                )
                self.table.wait_until_exists()
            
            # S3 버킷 생성 (없으면)
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            
            logger.info(f"DynamoDB + S3 repository initialized: {self.table_name}, {self.bucket_name}")
            
        except Exception as e:
            logger.error(f"Repository initialization failed: {str(e)}")
            raise StorageError(f"Failed to initialize repository: {str(e)}")
    
    async def close(self):
        """리소스 정리"""
        pass
    
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """작업 생성 - DynamoDB에 메타데이터, S3에 입력 데이터"""
        try:
            job_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            
            # 1. S3에 입력 데이터 저장
            input_data = {
                'job_id': job_id,
                'prompt': job_data['prompt'],
                'example_inputs': [
                    {
                        'content': inp.content if hasattr(inp, 'content') else inp['content'],
                        'input_type': inp.input_type if hasattr(inp, 'input_type') else inp['input_type']
                    }
                    for inp in job_data['example_inputs']
                ],
                'recommended_model': job_data.get('recommended_model'),
                'repeat_count': job_data['repeat_count'],
                'created_at': now
            }
            
            input_s3_key = f"inputs/{job_id}.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=input_s3_key,
                Body=json.dumps(input_data, ensure_ascii=False),
                ContentType='application/json',
                Metadata={
                    'job-id': job_id,
                    'data-type': 'input',
                    'created_at': now
                }
            )
            
            # 2. DynamoDB에 메타데이터 저장
            item = {
                'job_id': job_id,
                'created_at': now,
                'updated_at': now,
                'status': JobStatus.PENDING.value,
                'prompt_type': job_data['prompt_type'],
                'repeat_count': job_data['repeat_count'],
                'recommended_model': job_data.get('recommended_model'),
                's3_input_key': input_s3_key,
                's3_output_key': f"outputs/{job_id}.json",  # 미리 예약
                'has_outputs': False
            }
            
            self.table.put_item(Item=item)
            
            logger.info(f"Job created: {job_id} (Input stored in S3: {input_s3_key})")
            return job_id
            
        except Exception as e:
            logger.error(f"Job creation failed: {str(e)}")
            raise StorageError(f"Failed to create job: {str(e)}")
    
    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """작업 조회 - DynamoDB에서 지표, S3에서 입력/출력"""
        try:
            # DynamoDB에서 메타데이터 조회
            response = self.table.query(
                KeyConditionExpression='job_id = :job_id',
                ExpressionAttributeValues={':job_id': job_id},
                ScanIndexForward=False,  # 최신순
                Limit=1
            )
            
            if not response['Items']:
                return None
            
            item = response['Items'][0]
            
            # S3에서 입력 데이터 조회
            input_data = await self._get_data_from_s3(item['s3_input_key'])
            
            # S3에서 출력 데이터 조회 (있으면)
            output_data = None
            if item.get('has_outputs', False):
                output_data = await self._get_data_from_s3(item['s3_output_key'])
            
            # JobResponse 생성
            return self._item_to_job_response(item, input_data, output_data)
            
        except Exception as e:
            logger.error(f"Job retrieval failed: {str(e)}")
            raise StorageError(f"Failed to get job: {str(e)}")
    
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """작업 업데이트 - DynamoDB 지표 업데이트, S3에 출력 저장"""
        try:
            # 현재 아이템 조회
            response = self.table.query(
                KeyConditionExpression='job_id = :job_id',
                ExpressionAttributeValues={':job_id': job_id},
                ScanIndexForward=False,
                Limit=1
            )
            
            if not response['Items']:
                return False
            
            item = response['Items'][0]
            
            # 업데이트 표현식 구성
            update_expression = "SET updated_at = :updated_at"
            expression_values = {':updated_at': datetime.utcnow().isoformat()}
            
            if 'status' in updates:
                update_expression += ", #status = :status"
                expression_values[':status'] = updates['status']
            
            if 'error_message' in updates:
                update_expression += ", error_message = :error_message"
                expression_values[':error_message'] = updates['error_message']
            
            # 평가 결과 저장
            if 'result' in updates and updates['result']:
                result = updates['result']
                
                # DynamoDB에 지표 저장
                metrics = self._extract_metrics_for_dynamodb(result)
                update_expression += ", metrics = :metrics, final_score = :final_score"
                expression_values[':metrics'] = metrics
                expression_values[':final_score'] = metrics['final_score']
            
            # 실행 결과가 있으면 S3에 출력 저장
            if 'execution_results' in updates and updates['execution_results']:
                await self._save_outputs_to_s3(job_id, item['s3_output_key'], updates['execution_results'])
                update_expression += ", has_outputs = :has_outputs"
                expression_values[':has_outputs'] = True
            
            # DynamoDB 업데이트
            self.table.update_item(
                Key={
                    'job_id': item['job_id'],
                    'created_at': item['created_at']
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ExpressionAttributeNames={'#status': 'status'} if 'status' in updates else None
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Job update failed: {str(e)}")
            raise StorageError(f"Failed to update job: {str(e)}")
    
    async def list_jobs(self, page: int = 1, size: int = 10) -> List[JobResponse]:
        """작업 목록 조회 - DynamoDB 스캔 (지표만, 성능 최적화)"""
        try:
            # DynamoDB 스캔 (최신순)
            response = self.table.scan(
                Limit=size * 2,  # 여유분 확보
                ProjectionExpression='job_id, created_at, updated_at, #status, prompt_type, final_score, metrics, s3_input_key',
                ExpressionAttributeNames={'#status': 'status'}
            )
            
            jobs = []
            for item in response['Items']:
                # 목록에서는 입력/출력 데이터 로드하지 않음 (성능 최적화)
                job = self._item_to_job_response(item, None, None, summary_only=True)
                jobs.append(job)
            
            # 생성일시 기준 정렬 후 페이징
            jobs.sort(key=lambda x: x.created_at, reverse=True)
            start_idx = (page - 1) * size
            return jobs[start_idx:start_idx + size]
            
        except Exception as e:
            logger.error(f"Job listing failed: {str(e)}")
            raise StorageError(f"Failed to list jobs: {str(e)}")
    
    async def count_jobs(self) -> int:
        """전체 작업 수"""
        try:
            response = self.table.scan(Select='COUNT')
            return response['Count']
        except Exception as e:
            logger.error(f"Job counting failed: {str(e)}")
            return 0
    
    async def _get_data_from_s3(self, s3_key: str) -> Optional[Dict]:
        """S3에서 데이터 조회"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"S3 key not found: {s3_key}")
            return None
        except Exception as e:
            logger.error(f"Failed to get data from S3 ({s3_key}): {str(e)}")
            return None
    
    async def _save_outputs_to_s3(self, job_id: str, s3_key: str, execution_results: Dict[str, Any]):
        """S3에 AI 출력 결과 저장"""
        try:
            output_data = {
                'job_id': job_id,
                'execution_results': execution_results,
                'saved_at': datetime.utcnow().isoformat(),
                'note': 'AI generated outputs - full execution results'
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(output_data, ensure_ascii=False),
                ContentType='application/json',
                Metadata={
                    'job-id': job_id,
                    'data-type': 'output',
                    'saved-at': output_data['saved_at']
                }
            )
            
            logger.info(f"Outputs saved to S3: {s3_key}")
            
        except Exception as e:
            logger.error(f"Failed to save outputs to S3: {str(e)}")
            raise
    
    def _extract_metrics_for_dynamodb(self, result: EvaluationResult) -> Dict[str, Decimal]:
        """EvaluationResult에서 DynamoDB용 지표 추출"""
        metrics = {
            'final_score': Decimal(str(result.final_score))
        }
        
        if result.token_usage:
            metrics['token_usage'] = Decimal(str(result.token_usage.score))
        if result.information_density:
            metrics['information_density'] = Decimal(str(result.information_density.score))
        if result.consistency:
            metrics['consistency'] = Decimal(str(result.consistency.score))
        if result.relevance:
            metrics['relevance'] = Decimal(str(result.relevance.score))
        if result.hallucination:
            metrics['hallucination'] = Decimal(str(result.hallucination.score))
        if result.model_variance:
            metrics['model_variance'] = Decimal(str(result.model_variance.score))
        
        return metrics
    
    def _item_to_job_response(
        self, 
        item: Dict, 
        input_data: Optional[Dict], 
        output_data: Optional[Dict],
        summary_only: bool = False
    ) -> JobResponse:
        """DynamoDB 아이템을 JobResponse로 변환"""
        
        # 기본 정보
        job_response_data = {
            'id': item['job_id'],
            'status': JobStatus(item['status']),
            'created_at': datetime.fromisoformat(item['created_at']),
            'updated_at': datetime.fromisoformat(item['updated_at']),
            'repeat_count': item.get('repeat_count', 5),
            'recommended_model': item.get('recommended_model'),
            'error_message': item.get('error_message')
        }
        
        # 입력 정보
        if input_data and not summary_only:
            job_response_data.update({
                'prompt': input_data['prompt'],
                'prompt_type': PromptType(item['prompt_type']),
                'example_inputs': [ExampleInput(**inp) for inp in input_data['example_inputs']]
            })
        else:
            # 목록 조회시에는 요약 정보만
            job_response_data.update({
                'prompt': f"[Stored in S3: {item.get('s3_input_key', 'unknown')}]",
                'prompt_type': PromptType(item['prompt_type']),
                'example_inputs': []
            })
        
        # 평가 결과 (DynamoDB에서)
        if 'metrics' in item:
            metrics = item['metrics']
            job_response_data['result'] = EvaluationResult(
                token_usage=MetricScore(score=float(metrics.get('token_usage', 0)), details={}) if 'token_usage' in metrics else None,
                information_density=MetricScore(score=float(metrics.get('information_density', 0)), details={}) if 'information_density' in metrics else None,
                consistency=MetricScore(score=float(metrics.get('consistency', 0)), details={}) if 'consistency' in metrics else None,
                relevance=MetricScore(score=float(metrics.get('relevance', 0)), details={}) if 'relevance' in metrics else None,
                hallucination=MetricScore(score=float(metrics.get('hallucination', 0)), details={}) if 'hallucination' in metrics else None,
                model_variance=MetricScore(score=float(metrics.get('model_variance', 0)), details={}) if 'model_variance' in metrics else None,
                final_score=float(metrics['final_score'])
            )
        
        return JobResponse(**job_response_data)
    
    # 추가: S3 데이터 직접 조회 메서드들
    async def get_job_inputs(self, job_id: str) -> Optional[Dict]:
        """작업의 입력 데이터만 S3에서 조회"""
        try:
            response = self.table.query(
                KeyConditionExpression='job_id = :job_id',
                ExpressionAttributeValues={':job_id': job_id},
                ProjectionExpression='s3_input_key',
                Limit=1
            )
            
            if not response['Items']:
                return None
            
            s3_key = response['Items'][0]['s3_input_key']
            return await self._get_data_from_s3(s3_key)
            
        except Exception as e:
            logger.error(f"Failed to get job inputs: {str(e)}")
            return None
    
    async def get_job_outputs(self, job_id: str) -> Optional[Dict]:
        """작업의 출력 데이터만 S3에서 조회"""
        try:
            response = self.table.query(
                KeyConditionExpression='job_id = :job_id',
                ExpressionAttributeValues={':job_id': job_id},
                ProjectionExpression='s3_output_key, has_outputs',
                Limit=1
            )
            
            if not response['Items'] or not response['Items'][0].get('has_outputs', False):
                return None
            
            s3_key = response['Items'][0]['s3_output_key']
            return await self._get_data_from_s3(s3_key)
            
        except Exception as e:
            logger.error(f"Failed to get job outputs: {str(e)}")
            return None
    
    # ============================================
    # 새 스키마용 저장 메서드 (WAS 연동용)
    # ============================================
    
    async def save_completed_job(
        self,
        job: 'JobResponse',
        title: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        완료된 Job을 새 스키마로 S3/DynamoDB에 저장
        
        Returns:
            저장 결과 정보 (s3_url, dynamodb_pk 등)
        """
        from app.core.schemas import convert_job_to_dynamodb_record, create_s3_examples_data
        
        try:
            prompt_id = job.request_id
            
            # 1. S3에 examples.json 저장
            s3_examples_data = create_s3_examples_data(job)
            s3_key = f"prompts/{prompt_id}/examples.json"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(s3_examples_data.model_dump(), ensure_ascii=False, indent=2),
                ContentType='application/json',
                Metadata={
                    'prompt-id': prompt_id,
                    'prompt-type': job.prompt_type.value,
                    'created_at': s3_examples_data.created_at
                }
            )
            
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            logger.info(f"S3 examples saved: {s3_url}")
            
            # 2. TYPE_B_IMAGE인 경우 이미지도 S3에 저장 (TODO: 실제 이미지 데이터 처리)
            # 현재는 URL만 생성, 실제 이미지 업로드는 별도 처리 필요
            
            # 3. DynamoDB에 새 스키마로 저장
            dynamodb_record = convert_job_to_dynamodb_record(
                job=job,
                title=title,
                description=description,
                user_id=user_id,
                s3_bucket=self.bucket_name
            )
            
            # DynamoDB에 저장 (새 테이블 또는 기존 테이블에 새 형식으로)
            item = dynamodb_record.model_dump(by_alias=True)
            
            # Decimal 변환 (DynamoDB는 float 대신 Decimal 사용)
            item = self._convert_floats_to_decimal(item)
            
            self.table.put_item(Item=item)
            logger.info(f"DynamoDB record saved: PK={dynamodb_record.pk}")
            
            return {
                "success": True,
                "prompt_id": prompt_id,
                "s3_url": s3_url,
                "dynamodb_pk": dynamodb_record.pk,
                "dynamodb_sk": dynamodb_record.sk
            }
            
        except Exception as e:
            logger.error(f"Failed to save completed job: {str(e)}")
            raise StorageError(f"Failed to save completed job: {str(e)}")
    
    def _convert_floats_to_decimal(self, obj: Any) -> Any:
        """float를 Decimal로 변환 (DynamoDB 호환)"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        return obj