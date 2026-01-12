#!/usr/bin/env python3
"""
테스트용 SQS 메시지 전송
"""

import boto3
import json
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

def send_test_message():
    print("📤 테스트 메시지 전송...")
    
    # 실제 SQS 메시지 형식 (DynamoDB 구조)
    test_message = {
        "PK": "PROMPT#test-12345",
        "SK": "METADATA",
        "PROMPT_INDEX_PK": "USER_PROMPT_LIST",
        "PROMPT_INDEX_SK": "USER#test#2026-01-08T18:35:00Z",
        "type": "PROMPT",
        "create_user": "USER#test",
        "title": "테스트 프롬프트",
        "content": "{{topic}}에 대해 간단히 설명해주세요.",  # content 필드 사용
        "prompt_description": "테스트용 프롬프트입니다.",
        "price": 3000,
        "prompt_type": "type_a",
        "examples": [
            {
                "index": 0,
                "input": {
                    "content": "{\"topic\": \"인공지능\"}",
                    "input_type": "text"
                },
                "output": ""
            },
            {
                "index": 1,
                "input": {
                    "content": "{\"topic\": \"기계학습\"}",
                    "input_type": "text"
                },
                "output": ""
            },
            {
                "index": 2,
                "input": {
                    "content": "{\"topic\": \"딥러닝\"}",
                    "input_type": "text"
                },
                "output": ""
            }
        ],
        "examples_s3_url": "",
        "model": "",
        "evaluation_metrics": {},
        "status": "processing",
        "created_at": "2026-01-08T18:35:00Z",
        "updated_at": "",
        "like_count": 0,
        "comment_count": 0,
        "bookmark_count": 0,
        "is_public": False
    }
    
    try:
        sqs = boto3.client(
            "sqs", 
            region_name=AWS_REGION_SQS_DDB,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        # 메시지 전송
        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(test_message, ensure_ascii=False)
        )
        
        print(f"✅ 테스트 메시지 전송 완료!")
        print(f"   - Message ID: {response['MessageId']}")
        print(f"   - PK: {test_message['PK']}")
        print(f"   - 프롬프트: {test_message['content']}")
        print(f"   - 예시 개수: {len(test_message['examples'])}개")
        
    except Exception as e:
        print(f"❌ 메시지 전송 실패: {e}")

if __name__ == "__main__":
    send_test_message()