import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    """헬스 체크 테스트"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_create_job():
    """작업 생성 테스트"""
    job_data = {
        "prompt": "다음 질문에 답하세요: {{}}",
        "example_inputs": [
            {"content": "파리의 인구는?", "input_type": "text"},
            {"content": "지구의 나이는?", "input_type": "text"},
            {"content": "광속은 얼마인가?", "input_type": "text"}
        ],
        "prompt_type": "type_a",
        "repeat_count": 3
    }
    
    response = client.post("/api/v1/jobs", json=job_data)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"

def test_list_jobs():
    """작업 목록 조회 테스트"""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert "total" in data