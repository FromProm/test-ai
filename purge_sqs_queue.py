#!/usr/bin/env python3
"""
SQS 큐 비우기 스크립트
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

def purge_queue():
    print("🗑️  SQS 큐 비우기...")
    
    try:
        sqs = boto3.client(
            "sqs", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        # 큐 비우기 (모든 메시지 삭제)
        sqs.purge_queue(QueueUrl=SQS_QUEUE_URL)
        
        print("✅ SQS 큐가 비워졌습니다!")
        print("   - 모든 메시지가 삭제되었습니다")
        print("   - Invisible 메시지도 삭제됩니다")
        
    except Exception as e:
        print(f"❌ 큐 비우기 실패: {e}")

if __name__ == "__main__":
    confirm = input("정말로 SQS 큐의 모든 메시지를 삭제하시겠습니까? (y/N): ")
    if confirm.lower() == 'y':
        purge_queue()
    else:
        print("취소되었습니다.")