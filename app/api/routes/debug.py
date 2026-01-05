from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import boto3
import json
from app.core.config import settings

router = APIRouter(tags=["debug"])

@router.get("/debug/s3/buckets")
async def list_s3_buckets():
    """S3 버킷 목록 확인"""
    try:
        s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        
        return {
            "buckets": buckets,
            "target_bucket": settings.s3_bucket_name,
            "bucket_exists": settings.s3_bucket_name in buckets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 access failed: {str(e)}")

@router.get("/debug/s3/jobs")
async def list_s3_jobs():
    """S3에 저장된 작업 목록 확인"""
    try:
        s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        # jobs/ 폴더 내용 확인
        response = s3_client.list_objects_v2(
            Bucket=settings.s3_bucket_name,
            Prefix="jobs/",
            Delimiter="/"
        )
        
        job_folders = []
        for prefix in response.get('CommonPrefixes', []):
            job_id = prefix['Prefix'].split('/')[1]
            job_folders.append(job_id)
        
        return {
            "bucket": settings.s3_bucket_name,
            "job_count": len(job_folders),
            "job_ids": job_folders
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 jobs listing failed: {str(e)}")

@router.get("/debug/s3/jobs/{job_id}")
async def get_s3_job_files(job_id: str):
    """특정 작업의 S3 파일들 확인"""
    try:
        s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        # 해당 job의 모든 파일 확인
        response = s3_client.list_objects_v2(
            Bucket=settings.s3_bucket_name,
            Prefix=f"jobs/{job_id}/"
        )
        
        files = []
        for obj in response.get('Contents', []):
            files.append({
                "key": obj['Key'],
                "size": obj['Size'],
                "last_modified": obj['LastModified'].isoformat()
            })
        
        return {
            "job_id": job_id,
            "files": files,
            "file_count": len(files)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 job files listing failed: {str(e)}")

@router.get("/debug/s3/jobs/{job_id}/metadata")
async def get_s3_job_metadata(job_id: str):
    """S3에서 작업 메타데이터 내용 확인"""
    try:
        s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        # 메타데이터 파일 읽기
        response = s3_client.get_object(
            Bucket=settings.s3_bucket_name,
            Key=f"jobs/{job_id}/metadata.json"
        )
        
        metadata = json.loads(response['Body'].read().decode('utf-8'))
        
        return {
            "job_id": job_id,
            "metadata": metadata,
            "ai_outputs_stored": metadata.get('ai_outputs_stored', 'unknown')
        }
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"Job {job_id} metadata not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {str(e)}")

@router.get("/debug/s3/jobs/{job_id}/result")
async def get_s3_job_result(job_id: str):
    """S3에서 평가 결과 확인"""
    try:
        s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None
        )
        
        # 평가 결과 파일 읽기
        response = s3_client.get_object(
            Bucket=settings.s3_bucket_name,
            Key=f"jobs/{job_id}/evaluation_result.json"
        )
        
        result = json.loads(response['Body'].read().decode('utf-8'))
        
        return {
            "job_id": job_id,
            "evaluation_result": result,
            "contains_ai_outputs": "outputs" in str(result)
        }
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"Job {job_id} result not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {str(e)}")

@router.get("/debug/storage/backend")
async def get_storage_backend():
    """현재 사용 중인 저장소 백엔드 확인"""
    return {
        "storage_backend": settings.storage_backend,
        "s3_bucket_name": settings.s3_bucket_name,
        "table_name": settings.table_name,
        "mock_mode": settings.mock_mode,
        "database_url": settings.database_url
    }

@router.get("/debug/dynamodb/jobs/{job_id}/inputs")
async def get_job_inputs_from_s3(job_id: str):
    """S3에서 작업 입력 데이터 확인"""
    try:
        from app.main import context
        storage = context.get_storage()
        
        if hasattr(storage, 'get_job_inputs'):
            inputs = await storage.get_job_inputs(job_id)
            return {
                "job_id": job_id,
                "inputs": inputs,
                "has_inputs": inputs is not None
            }
        else:
            return {"error": "Storage backend does not support direct input access"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get inputs: {str(e)}")

@router.get("/debug/dynamodb/jobs/{job_id}/outputs")
async def get_job_outputs_from_s3(job_id: str):
    """S3에서 작업 출력 데이터 확인"""
    try:
        from app.main import context
        storage = context.get_storage()
        
        if hasattr(storage, 'get_job_outputs'):
            outputs = await storage.get_job_outputs(job_id)
            return {
                "job_id": job_id,
                "outputs": outputs,
                "has_outputs": outputs is not None,
                "contains_ai_generated_text": "execution_results" in str(outputs) if outputs else False
            }
        else:
            return {"error": "Storage backend does not support direct output access"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get outputs: {str(e)}")