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
        port=8000,
        reload=is_development,  # 개발환경에서만 reload
        log_level="info"
    )