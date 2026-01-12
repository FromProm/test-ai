#!/usr/bin/env python3
"""
SQS 및 DynamoDB 연결 테스트 스크립트
"""

import os
import sys
import boto3
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일 직접 로드 (dotenv 대신)
def load_env_direct():
    env_path = project_root / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env_direct()

def test_sqs_connection():
    """SQS 연결 테스트"""
    print("📡 SQS 연결 테스트...")
    
    queue_url = os.getenv("SQS_QUEUE_URL")
    if not queue_url:
        print("❌ SQS_QUEUE_URL이 설정되지 않았습니다.")
        return False
    
    try:
        # SQS는 서울 리전 사용
        sqs_region = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")
        sqs = boto3.client("sqs", region_name=sqs_region)
        
        # 큐 속성 조회로 연결 테스트
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['QueueArn', 'ApproximateNumberOfMessages']
        )
        
        print(f"✅ SQS 연결 성공!")
        print(f"   - Region: {sqs_region}")
        print(f"   - Queue ARN: {response['Attributes'].get('QueueArn')}")
        print(f"   - 대기 중인 메시지: {response['Attributes'].get('ApproximateNumberOfMessages')}")
        return True
        
    except Exception as e:
        print(f"❌ SQS 연결 실패: {e}")
        return False

def test_s3_connection():
    """S3 연결 테스트"""
    print("\n📦 S3 연결 테스트...")
    
    bucket_name = os.getenv("S3_BUCKET_NAME", "fromprom_s3")
    
    try:
        # S3는 서울 리전 사용
        s3_region = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")
        s3 = boto3.client("s3", region_name=s3_region)
        
        # 버킷 존재 확인
        response = s3.head_bucket(Bucket=bucket_name)
        
        print(f"✅ S3 연결 성공!")
        print(f"   - Bucket: {bucket_name}")
        print(f"   - Region: {s3_region}")
        return True
        
    except Exception as e:
        print(f"❌ S3 연결 실패: {e}")
        return False

def test_dynamodb_connection():
    """DynamoDB 연결 테스트"""
    print("\n🗄️ DynamoDB 연결 테스트...")
    
    table_name = os.getenv("DDB_TABLE_NAME", "FromProm_Table")
    
    try:
        # DynamoDB는 서울 리전 사용
        ddb_region = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")
        ddb = boto3.client("dynamodb", region_name=ddb_region)
        
        # 테이블 정보 조회로 연결 테스트
        response = ddb.describe_table(TableName=table_name)
        
        print(f"✅ DynamoDB 연결 성공!")
        print(f"   - Table: {table_name}")
        print(f"   - Region: {ddb_region}")
        print(f"   - Status: {response['Table']['TableStatus']}")
        print(f"   - Item Count: {response['Table']['ItemCount']}")
        return True
        
    except Exception as e:
        print(f"❌ DynamoDB 연결 실패: {e}")
        return False

def test_aws_credentials():
    """AWS 자격증명 테스트"""
    print("🔑 AWS 자격증명 테스트...")
    
    try:
        sts = boto3.client("sts", region_name="ap-northeast-2")
        response = sts.get_caller_identity()
        
        print(f"✅ AWS 자격증명 확인!")
        print(f"   - Account: {response['Account']}")
        print(f"   - User ARN: {response['Arn']}")
        return True
        
    except Exception as e:
        print(f"❌ AWS 자격증명 실패: {e}")
        return False

if __name__ == "__main__":
    print("🧪 AWS 서비스 연결 테스트 시작")
    print("=" * 50)
    
    # 환경변수 확인
    print(f"AWS_REGION (Bedrock): {os.getenv('AWS_REGION', 'us-east-1')}")
    print(f"AWS_REGION_SQS_DDB: {os.getenv('AWS_REGION_SQS_DDB', 'ap-northeast-2')}")
    print(f"SQS_QUEUE_URL: {os.getenv('SQS_QUEUE_URL')}")
    print(f"DDB_TABLE_NAME: {os.getenv('DDB_TABLE_NAME')}")
    print("=" * 50)
    
    # 테스트 실행
    tests = [
        test_aws_credentials,
        test_sqs_connection, 
        test_dynamodb_connection,
        test_s3_connection
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 50)
    if all(results):
        print("🎉 모든 연결 테스트 통과!")
        print("SQS Worker를 실행할 준비가 되었습니다.")
        print("\n실행 명령어:")
        print("python run_sqs_worker.py")
    else:
        print("❌ 일부 테스트 실패")
        print(".env 파일과 AWS 설정을 확인해주세요.")