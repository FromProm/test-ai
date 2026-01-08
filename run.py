#!/usr/bin/env python3
"""
Prompt Evaluation System 실행 스크립트
"""
import uvicorn
import os
from app.main import app

if __name__ == "__main__":
    # 환경에 따라 reload 모드 결정
    is_development = os.getenv("ENVIRONMENT", "development") == "development"
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,  # 포트 변경
        reload=False,  # 리로드 비활성화 (안정성 향상)
        log_level="info",
        timeout_keep_alive=3600  # 1시간 타임아웃 설정
    )