#!/usr/bin/env python3
"""
간단한 Bedrock 연결 테스트
"""
import os
import asyncio
from pathlib import Path

# .env 파일 직접 파싱
def load_env_file():
    env_path = Path.cwd() / '.env'
    if env_path.exists():
        print(f"[init] .env 파일 발견: {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        print(f"[init] .env 로드 완료")

load_env_file()

from app.orchestrator.context import ExecutionContext

async def test_bedrock():
    print("🧪 Bedrock 연결 테스트 시작...")
    
    try:
        # ExecutionContext 생성
        context = ExecutionContext()
        runner = context.get_runner()
        
        print("✅ ExecutionContext 및 Runner 생성 성공")
        
        # 간단한 프롬프트 테스트
        model = "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        prompt = "안녕하세요. 간단히 인사해주세요."
        
        print(f"📤 모델: {model}")
        print(f"📤 프롬프트: {prompt}")
        print("🔄 API 호출 중...")
        
        result = await runner.invoke(
            model=model,
            prompt=prompt,
            input_type="text"
        )
        
        print("✅ API 호출 성공!")
        print(f"📥 응답: {result.get('output', 'No output')[:100]}...")
        
    except Exception as e:
        print(f"❌ 에러 발생: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_bedrock())