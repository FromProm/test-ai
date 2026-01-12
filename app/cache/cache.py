import json
import logging
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.errors import CacheError

logger = logging.getLogger(__name__)

class Cache:
    """인메모리 캐시 (선택적 영속성)"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = settings.cache_ttl
    
    async def initialize(self):
        """캐시 초기화"""
        logger.info("Cache initialized")
    
    async def close(self):
        """캐시 정리"""
        self._cache.clear()
        logger.info("Cache cleared")
    
    async def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        try:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # TTL 확인
            if self._is_expired(entry):
                del self._cache[key]
                return None
            
            logger.debug(f"Cache hit: {key}")
            return entry['value']
            
        except Exception as e:
            logger.error(f"Cache get failed: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """캐시에 값 저장"""
        try:
            expire_time = datetime.utcnow() + timedelta(seconds=ttl or self.ttl)
            
            self._cache[key] = {
                'value': value,
                'expire_time': expire_time
            }
            
            logger.debug(f"Cache set: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Cache set failed: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """캐시에서 값 삭제"""
        try:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache deleted: {key}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Cache delete failed: {str(e)}")
            return False
    
    async def clear(self) -> bool:
        """전체 캐시 삭제"""
        try:
            self._cache.clear()
            logger.info("Cache cleared")
            return True
            
        except Exception as e:
            logger.error(f"Cache clear failed: {str(e)}")
            return False
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """만료 여부 확인"""
        return datetime.utcnow() > entry['expire_time']
    
    async def cleanup_expired(self):
        """만료된 항목 정리"""
        try:
            expired_keys = [
                key for key, entry in self._cache.items()
                if self._is_expired(entry)
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
                
        except Exception as e:
            logger.error(f"Cache cleanup failed: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계"""
        return {
            'total_entries': len(self._cache),
            'ttl_seconds': self.ttl
        }