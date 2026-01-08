#!/usr/bin/env python3
"""
SQS 큐 상태 확인 스크립트
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

def check_queue_status():
    print("📡 SQS 큐 상태 확인...")
    
    try:
        sqs = boto3.client(
            "sqs", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        # 큐 속성 조회
        response = sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=[
                'ApproximateNumberOfMessages',
                'ApproximateNumberOfMessagesNotVisible',
                'ApproximateNumberOfMessagesDelayed'
            ]
        )
        
        attrs = response['Attributes']
        visible = int(attrs.get('ApproximateNumberOfMessages', 0))
        not_visible = int(attrs.get('ApproximateNumberOfMessagesNotVisible', 0))
        delayed = int(attrs.get('ApproximateNumberOfMessagesDelayed', 0))
        
        print(f"✅ SQS 큐 상태:")
        print(f"   - 처리 대기 중인 메시지: {visible}개")
        print(f"   - 처리 중인 메시지 (Invisible): {not_visible}개")
        print(f"   - 지연된 메시지: {delayed}개")
        print(f"   - 총 메시지: {visible + not_visible + delayed}개")
        
        if visible > 0:
            print(f"\n⚠️  처리 대기 중인 메시지가 {visible}개 있습니다!")
            print("   Worker를 실행하면 즉시 처리를 시작합니다.")
        
        return visible > 0
        
    except Exception as e:
        print(f"❌ SQS 큐 확인 실패: {e}")
        return False

if __name__ == "__main__":
    check_queue_status()