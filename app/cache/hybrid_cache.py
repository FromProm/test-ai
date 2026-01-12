import asyncio
import logging
import time
from typing import Any, Optional, Dict, List
from collections import OrderedDict
from datetime import datetime, timedelta

from app.cache.sqlite_cache import SQLiteCache
from app.cache.dynamodb_cache import DynamoDBFactCheckCache
from app.core.config import settings

logger = logging.getLogger(__name__)

class MemoryCache:
    """메모리 캐시 (LRU 방식)"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.access_times = {}
        self.hit_count = 0
        self.miss_count = 0
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """메모리에서 조회"""
        if key in self.cache:
            # LRU: 최근 사용된 항목을 맨 뒤로 이동
            value = self.cache.pop(key)
            self.cache[key] = value
            self.access_times[key] = time.time()
            self.hit_count += 1
            return value
        
        self.miss_count += 1
        return None
    
    def set(self, key: str, value: Dict[str, Any]) -> None:
        """메모리에 저장"""
        if key in self.cache:
            # 기존 항목 업데이트
            self.cache.pop(key)
        elif len(self.cache) >= self.max_size:
            # 용량 초과 시 가장 오래된 항목 제거
            oldest_key = next(iter(self.cache))
            self.cache.pop(oldest_key)
            self.access_times.pop(oldest_key, None)
        
        self.cache[key] = value
        self.access_times[key] = time.time()
    
    def clear(self) -> None:
        """메모리 캐시 전체 삭제"""
        self.cache.clear()
        self.access_times.clear()
        self.hit_count = 0
        self.miss_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """메모리 캐시 통계"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_rate_percent': round(hit_rate, 2),
            'usage_percent': round(len(self.cache) / self.max_size * 100, 2)
        }

class HybridFactCheckCache:
    """하이브리드 3단계 캐시 시스템 (메모리 + SQLite + DynamoDB)"""
    
    def __init__(self, 
                 memory_max_size: int = 1000,
                 sqlite_db_path: str = "fact_check_cache.db",
                 dynamodb_table_name: str = None):
        
        # 3단계 캐시 초기화
        self.memory_cache = MemoryCache(memory_max_size)
        self.sqlite_cache = SQLiteCache(sqlite_db_path)
        self.dynamodb_cache = DynamoDBFactCheckCache(dynamodb_table_name)
        
        # 통계
        self.stats = {
            'memory_hits': 0,
            'sqlite_hits': 0,
            'dynamodb_hits': 0,
            'cache_misses': 0,
            'total_requests': 0
        }
        
        # DynamoDB 배치 저장용 버퍼
        self.dynamodb_batch_buffer = []
        self.dynamodb_batch_size = getattr(settings, 'dynamodb_batch_size', 25)
        self.last_dynamodb_batch_time = time.time()
        self.dynamodb_batch_interval = getattr(settings, 'dynamodb_batch_interval', 300)  # 5분
        
        logger.info("Hybrid cache initialized (Memory + SQLite + DynamoDB)")
    
    async def get_fact_check(self, claim: str) -> Optional[Dict[str, Any]]:
        """하이브리드 캐시에서 fact check 결과 조회"""
        self.stats['total_requests'] += 1
        start_time = time.time()
        
        try:
            # 1단계: 메모리 캐시 확인
            result = self.memory_cache.get(claim)
            if result:
                self.stats['memory_hits'] += 1
                logger.debug(f"Memory cache hit for claim: {claim[:50]}... ({time.time() - start_time:.3f}s)")
                return result
            
            # 2단계: SQLite 캐시 확인
            result = await self.sqlite_cache.get_fact_check(claim)
            if result:
                self.stats['sqlite_hits'] += 1
                # 메모리 캐시에도 저장
                self.memory_cache.set(claim, result)
                logger.debug(f"SQLite cache hit for claim: {claim[:50]}... ({time.time() - start_time:.3f}s)")
                return result
            
            # 3단계: DynamoDB 캐시 확인
            result = await self.dynamodb_cache.get_fact_check(claim)
            if result:
                self.stats['dynamodb_hits'] += 1
                # SQLite와 메모리 캐시에도 저장
                await self.sqlite_cache.set_fact_check(claim, result)
                self.memory_cache.set(claim, result)
                logger.debug(f"DynamoDB cache hit for claim: {claim[:50]}... ({time.time() - start_time:.3f}s)")
                return result
            
            # 모든 캐시에서 미스
            self.stats['cache_misses'] += 1
            logger.debug(f"Cache miss for claim: {claim[:50]}... ({time.time() - start_time:.3f}s)")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get fact check from hybrid cache: {str(e)}")
            return None
    
    async def set_fact_check(self, claim: str, result: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """하이브리드 캐시에 fact check 결과 저장"""
        try:
            success_count = 0
            
            # 1단계: 메모리 캐시에 즉시 저장
            self.memory_cache.set(claim, result)
            success_count += 1
            
            # 2단계: SQLite 캐시에 비동기 저장
            try:
                sqlite_success = await self.sqlite_cache.set_fact_check(claim, result, ttl)
                if sqlite_success:
                    success_count += 1
            except Exception as e:
                logger.warning(f"SQLite cache set failed: {str(e)}")
            
            # 3단계: DynamoDB 배치 버퍼에 추가 (나중에 배치 저장)
            try:
                self.dynamodb_batch_buffer.append({
                    'claim': claim,
                    'result': result,
                    'ttl': ttl,
                    'timestamp': time.time()
                })
                
                # 배치 저장 조건 확인
                await self._check_dynamodb_batch_save()
                success_count += 1
                
            except Exception as e:
                logger.warning(f"DynamoDB batch buffer add failed: {str(e)}")
            
            logger.debug(f"Hybrid cache set for claim: {claim[:50]}... (success: {success_count}/3)")
            return success_count >= 2  # 메모리 + SQLite 성공하면 OK
            
        except Exception as e:
            logger.error(f"Failed to set fact check in hybrid cache: {str(e)}")
            return False
    
    async def _check_dynamodb_batch_save(self) -> None:
        """DynamoDB 배치 저장 조건 확인 및 실행"""
        current_time = time.time()
        
        # 조건: 버퍼 크기 또는 시간 간격
        should_save = (
            len(self.dynamodb_batch_buffer) >= self.dynamodb_batch_size or
            (current_time - self.last_dynamodb_batch_time) >= self.dynamodb_batch_interval
        )
        
        if should_save and self.dynamodb_batch_buffer:
            # 백그라운드에서 DynamoDB 배치 저장 실행
            asyncio.create_task(self._execute_dynamodb_batch_save())
    
    async def _execute_dynamodb_batch_save(self) -> None:
        """DynamoDB 배치 저장 실행"""
        if not self.dynamodb_batch_buffer:
            return
        
        try:
            # 현재 버퍼 복사 후 초기화
            batch_items = self.dynamodb_batch_buffer.copy()
            self.dynamodb_batch_buffer.clear()
            self.last_dynamodb_batch_time = time.time()
            
            logger.info(f"Starting DynamoDB batch save: {len(batch_items)} items")
            
            # DynamoDB에 배치 저장
            success_count = await self.dynamodb_cache.batch_set_fact_checks(batch_items)
            
            logger.info(f"DynamoDB batch save completed: {success_count}/{len(batch_items)} successful")
            
        except Exception as e:
            logger.error(f"DynamoDB batch save failed: {str(e)}")
            # 실패한 항목들을 다시 버퍼에 추가 (재시도용)
            if 'batch_items' in locals():
                self.dynamodb_batch_buffer.extend(batch_items[-10:])  # 최근 10개만 재시도
    
    async def cleanup_expired(self) -> Dict[str, int]:
        """모든 캐시에서 만료된 항목 정리"""
        results = {
            'memory_cleared': 0,
            'sqlite_cleaned': 0,
            'dynamodb_cleaned': 0
        }
        
        try:
            # 메모리 캐시는 TTL이 없으므로 전체 클리어 (선택적)
            # results['memory_cleared'] = len(self.memory_cache.cache)
            # self.memory_cache.clear()
            
            # SQLite 캐시 정리
            results['sqlite_cleaned'] = await self.sqlite_cache.cleanup_expired()
            
            # DynamoDB 캐시 정리 (TTL 자동 처리되므로 통계만)
            results['dynamodb_cleaned'] = await self.dynamodb_cache.cleanup_expired()
            
            logger.info(f"Cache cleanup completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {str(e)}")
            return results
    
    async def get_comprehensive_stats(self) -> Dict[str, Any]:
        """전체 캐시 시스템 통계"""
        try:
            # 기본 통계
            total_requests = self.stats['total_requests']
            cache_hits = self.stats['memory_hits'] + self.stats['sqlite_hits'] + self.stats['dynamodb_hits']
            overall_hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
            
            stats = {
                'overall': {
                    'total_requests': total_requests,
                    'cache_hits': cache_hits,
                    'cache_misses': self.stats['cache_misses'],
                    'hit_rate_percent': round(overall_hit_rate, 2)
                },
                'by_layer': {
                    'memory_hits': self.stats['memory_hits'],
                    'sqlite_hits': self.stats['sqlite_hits'],
                    'dynamodb_hits': self.stats['dynamodb_hits'],
                    'memory_hit_rate': round(self.stats['memory_hits'] / total_requests * 100, 2) if total_requests > 0 else 0,
                    'sqlite_hit_rate': round(self.stats['sqlite_hits'] / total_requests * 100, 2) if total_requests > 0 else 0,
                    'dynamodb_hit_rate': round(self.stats['dynamodb_hits'] / total_requests * 100, 2) if total_requests > 0 else 0
                },
                'memory_cache': self.memory_cache.get_stats(),
                'dynamodb_batch': {
                    'buffer_size': len(self.dynamodb_batch_buffer),
                    'batch_size_limit': self.dynamodb_batch_size,
                    'last_batch_time': datetime.fromtimestamp(self.last_dynamodb_batch_time).isoformat(),
                    'batch_interval_minutes': self.dynamodb_batch_interval / 60
                }
            }
            
            # SQLite 통계 추가
            sqlite_stats = await self.sqlite_cache.get_stats()
            stats['sqlite_cache'] = sqlite_stats
            
            # DynamoDB 통계 추가
            try:
                dynamodb_stats = await self.dynamodb_cache.get_stats()
                stats['dynamodb_cache'] = dynamodb_stats
            except Exception as e:
                stats['dynamodb_cache'] = {'status': 'error', 'error': str(e)}
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get comprehensive stats: {str(e)}")
            return {'error': str(e)}
    
    async def force_dynamodb_batch_save(self) -> int:
        """DynamoDB 배치 저장 강제 실행"""
        if not self.dynamodb_batch_buffer:
            return 0
        
        await self._execute_dynamodb_batch_save()
        return len(self.dynamodb_batch_buffer)
    
    async def clear_all_caches(self) -> Dict[str, bool]:
        """모든 캐시 삭제"""
        results = {
            'memory_cleared': False,
            'sqlite_cleared': False,
            's3_cleared': False
        }
        
        try:
            # 메모리 캐시 삭제
            self.memory_cache.clear()
            results['memory_cleared'] = True
            
            # SQLite 캐시 삭제
            results['sqlite_cleared'] = await self.sqlite_cache.clear_all()
            
            # DynamoDB 배치 버퍼 삭제
            self.dynamodb_batch_buffer.clear()
            
            # 통계 초기화
            self.stats = {
                'memory_hits': 0,
                'sqlite_hits': 0,
                'dynamodb_hits': 0,
                'cache_misses': 0,
                'total_requests': 0
            }
            
            logger.info("All caches cleared")
            return results
            
        except Exception as e:
            logger.error(f"Failed to clear all caches: {str(e)}")
            return results