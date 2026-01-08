#!/usr/bin/env python3
"""
SQS Worker 실행 스크립트
서울 리전의 SQS 큐에서 메시지를 받아서 프롬프트 평가를 수행합니다.
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일 직접 로드
def load_env_file():
    env_path = project_root / '.env'
    if env_path.exists():
        print(f"📄 .env 파일 로드: {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        print("✅ .env 파일 로드 완료")
    else:
        print(f"❌ .env 파일 없음: {env_path}")

# 환경변수 확인
def check_environment():
    required_vars = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY", 
        "SQS_QUEUE_URL",
        "DDB_TABLE_NAME"
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print("❌ 필수 환경변수가 설정되지 않았습니다:")
        for var in missing:
            print(f"   - {var}")
        print("\n.env 파일을 확인해주세요.")
        return False
    
    print("✅ 환경변수 확인 완료")
    print(f"   - AWS_REGION: {os.getenv('AWS_REGION', 'us-east-1')}")
    print(f"   - AWS_REGION_SQS_DDB: {os.getenv('AWS_REGION_SQS_DDB', 'ap-northeast-2')}")
    print(f"   - SQS_QUEUE_URL: {os.getenv('SQS_QUEUE_URL')}")
    print(f"   - DDB_TABLE_NAME: {os.getenv('DDB_TABLE_NAME')}")
    return True

if __name__ == "__main__":
    print("🚀 SQS Worker 시작 중...")
    
    # .env 파일 로드
    load_env_file()
    
    if not check_environment():
        sys.exit(1)
    
    # SQS Worker 실행
    from app.storage.sqs_worker import main
    main()