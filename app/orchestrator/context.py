from typing import Dict, Any, Optional
from app.adapters.runner.bedrock_runner import BedrockRunner
from app.adapters.runner.mock_runner import MockRunner
from app.adapters.embedder.bedrock_embedder import BedrockEmbedder
from app.adapters.embedder.mock_embedder import MockEmbedder
from app.adapters.judge.bedrock_judge import BedrockJudge
from app.adapters.judge.mock_judge import MockJudge
from app.storage.sqlite_repo import SQLiteRepository
from app.storage.s3_repo import S3Repository
from app.storage.dynamodb_s3_repo import DynamoDBS3Repository
from app.cache.cache import Cache
from app.core.config import settings

class ExecutionContext:
    """실행 컨텍스트 - 캐시, 스토리지, 어댑터 핸들 관리"""
    
    def __init__(self):
        self.cache = Cache() if settings.cache_enabled else None
        
        # 저장소 선택
        if settings.storage_backend == "dynamodb_s3":
            self.storage = DynamoDBS3Repository(settings.table_name, settings.s3_bucket_name)
        elif settings.storage_backend == "s3":
            self.storage = S3Repository(settings.s3_bucket_name)
        else:
            self.storage = SQLiteRepository()
        
        # Mock 모드 여부에 따라 어댑터 선택
        if settings.mock_mode:
            self.runner = MockRunner()
            self.embedder = MockEmbedder()
            self.judge = MockJudge()
        else:
            self.runner = BedrockRunner()
            self.embedder = BedrockEmbedder()
            self.judge = BedrockJudge()
        
    async def initialize(self):
        """Initialize all components"""
        await self.storage.initialize()
        if self.cache:
            await self.cache.initialize()
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.storage.close()
        if self.cache:
            await self.cache.close()
    
    def get_runner(self) -> BedrockRunner:
        return self.runner
    
    def get_embedder(self) -> BedrockEmbedder:
        return self.embedder
    
    def get_judge(self) -> BedrockJudge:
        return self.judge
    
    def get_storage(self) -> SQLiteRepository:
        return self.storage
    
    def get_cache(self) -> Optional[Cache]:
        return self.cache