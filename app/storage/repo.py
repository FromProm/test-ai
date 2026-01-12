from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.schemas import JobResponse, JobStatus

class BaseRepository(ABC):
    """저장소 기본 인터페이스"""
    
    @abstractmethod
    async def initialize(self):
        """저장소 초기화"""
        pass
    
    @abstractmethod
    async def close(self):
        """저장소 연결 종료"""
        pass
    
    @abstractmethod
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """작업 생성"""
        pass
    
    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """작업 조회"""
        pass
    
    @abstractmethod
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """작업 업데이트"""
        pass
    
    @abstractmethod
    async def list_jobs(self, page: int = 1, size: int = 10, request_id: Optional[str] = None) -> List[JobResponse]:
        """작업 목록 조회"""
        pass
    
    @abstractmethod
    async def count_jobs(self, request_id: Optional[str] = None) -> int:
        """전체 작업 수"""
        pass