#!/usr/bin/env python3
"""
이미지 생성 테스트 메시지 전송
"""
import json
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

# SQS 클라이언트 생성
sqs = boto3.client(
    'sqs',
    region_name=os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# 테스트 메시지 생성 (이미지 생성용)
test_message = {
    "PK": "PROMPT#image-test-12345",
    "SK": "METADATA",
    "PROMPT_INDEX_PK": "USER_PROMPT_LIST",
    "PROMPT_INDEX_SK": "USER#test#2026-01-08T19:30:00Z",
    "type": "PROMPT",
    "create_user": "USER#test",
    "title": "이미지 생성 테스트 프롬프트",
    "content": "A beautiful {{subject}} in {{style}} style, with {{lighting}} lighting",
    "prompt_description": "이미지 생성 테스트용 프롬프트입니다.",
    "price": 5000,
    "prompt_type": "type_b_image",
    "examples": [
        {
            "index": 0,
            "input": {
                "content": "{\"subject\": \"mountain landscape\", \"style\": \"impressionist\", \"lighting\": \"golden hour\"}",
                "input_type": "text"
            },
            "output": ""
        },
        {
            "index": 1,
            "input": {
                "content": "{\"subject\": \"city skyline\", \"style\": \"cyberpunk\", \"lighting\": \"neon\"}",
                "input_type": "text"
            },
            "output": ""
        },
        {
            "index": 2,
            "input": {
                "content": "{\"subject\": \"forest path\", \"style\": \"realistic\", \"lighting\": \"soft morning\"}",
                "input_type": "text"
            },
            "output": ""
        }
    ],
    "examples_s3_url": "",
    "model": "amazon.nova-canvas-v1:0",
    "evaluation_metrics": {},
    "status": "processing",
    "created_at": "2026-01-08T19:30:00Z",
    "updated_at": "",
    "like_count": 0,
    "comment_count": 0,
    "bookmark_count": 0,
    "is_public": False
}

def send_message():
    queue_url = os.getenv("SQS_QUEUE_URL")
    if not queue_url:
        print("❌ SQS_QUEUE_URL 환경변수가 설정되지 않았습니다!")
        return
    
    try:
        print("📤 이미지 생성 테스트 메시지 전송...")
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(test_message, ensure_ascii=False)
        )
        
        print("✅ 이미지 생성 테스트 메시지 전송 완료!")
        print(f"   - Message ID: {response['MessageId']}")
        print(f"   - PK: {test_message['PK']}")
        print(f"   - 프롬프트: {test_message['content']}")
        print(f"   - 타입: {test_message['prompt_type']}")
        print(f"   - 모델: {test_message['model']}")
        print(f"   - 예시 개수: {len(test_message['examples'])}개")
        
    except Exception as e:
        print(f"❌ 메시지 전송 실패: {e}")

if __name__ == "__main__":
    send_message()