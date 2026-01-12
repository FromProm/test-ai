#!/usr/bin/env python3
"""
자격증명 포함 SQS 연결 테스트
"""

import boto3
import os
from pathlib import Path

# .env 파일 직접 파싱
def load_env_file():
    env_path = Path.cwd() / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env_file()

# 환경변수에서 설정 읽기
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
AWS_REGION_SQS_DDB = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")

def test_with_explicit_creds():
    print("🧪 명시적 자격증명으로 테스트")
    print("=" * 50)
    
    # 자격증명 확인
    print("🔑 자격증명 확인...")
    try:
        sts = boto3.client(
            "sts", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        identity = sts.get_caller_identity()
        print(f"✅ 계정: {identity['Account']}")
        print(f"   사용자: {identity['Arn']}")
    except Exception as e:
        print(f"❌ 자격증명 실패: {e}")
        return False
    
    # SQS 테스트
    print("\n📡 SQS 연결 테스트...")
    try:
        sqs = boto3.client(
            "sqs", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        response = sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=['QueueArn', 'ApproximateNumberOfMessages']
        )
        
        print(f"✅ SQS 연결 성공!")
        print(f"   - Queue ARN: {response['Attributes'].get('QueueArn')}")
        print(f"   - 대기 중인 메시지: {response['Attributes'].get('ApproximateNumberOfMessages')}")
        sqs_ok = True
        
    except Exception as e:
        print(f"❌ SQS 연결 실패: {e}")
        sqs_ok = False
    
    # DynamoDB 테스트
    print("\n🗄️ DynamoDB 연결 테스트...")
    try:
        ddb = boto3.client(
            "dynamodb", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        response = ddb.describe_table(TableName="FromProm_Table")
        
        print(f"✅ DynamoDB 연결 성공!")
        print(f"   - Table: FromProm_Table")
        print(f"   - Status: {response['Table']['TableStatus']}")
        print(f"   - Item Count: {response['Table']['ItemCount']}")
        ddb_ok = True
        
    except Exception as e:
        print(f"❌ DynamoDB 연결 실패: {e}")
        ddb_ok = False
    
    print("\n" + "=" * 50)
    if sqs_ok and ddb_ok:
        print("🎉 모든 연결 테스트 통과!")
        print("리전 분리 + 자격증명이 정상 작동합니다.")
        return True
    else:
        print("❌ 일부 테스트 실패")
        return False

if __name__ == "__main__":
    test_with_explicit_creds()