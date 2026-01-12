import json
import sqlite3
import logging
import hashlib
import re
from typing import Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

class SQLiteCache:
    """SQLite 기반 영속 캐시 (환각탐지용)"""
    
    def __init__(self, db_path: str = "cache.db"):
        self.db_path = Path(db_path)
        self.ttl = getattr(settings, 'cache_fact_check_ttl', settings.cache_ttl)  # Fact check 전용 TTL 사용
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS fact_check_cache (
                        claim_hash TEXT PRIMARY KEY,
                        claim_text TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL
                    )
                """)
                
                # 인덱스 생성
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expires_at 
                    ON fact_check_cache(expires_at)
                """)
                
                conn.commit()
                logger.info(f"SQLite cache initialized: {self.db_path}")
                
        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache: {str(e)}")
            raise
    
    def _hash_claim(self, claim: str) -> str:
        """Claim을 키워드 기반으로 해시 생성"""
        keywords = self._extract_keywords(claim)
        if not keywords:
            # 키워드가 없으면 원본 텍스트 해시 사용
            return hashlib.sha256(claim.encode('utf-8')).hexdigest()
        
        # 키워드를 정렬해서 순서에 상관없이 같은 해시 생성
        keywords_str = "_".join(sorted(keywords))
        return hashlib.sha256(keywords_str.encode('utf-8')).hexdigest()
    
    def _extract_keywords(self, claim: str) -> List[str]:
        """Claim에서 핵심 키워드 추출"""
        # 1. 숫자 (연도, 금액, 수량 등)
        numbers = re.findall(r'\d+(?:[.,]\d+)*(?:조|억|만|천|원|달러|%|년|월|일|개|명|대)?', claim)
        
        # 2. 고유명사 (회사명, 인명, 지명 등) - 대문자로 시작하거나 한글 2글자 이상
        proper_nouns = re.findall(r'[A-Z][a-zA-Z]+|[가-힣]{2,}(?:전자|그룹|회사|기업|대학|병원|은행|카드|생명|화학|건설|통신|시스템|테크|랩스?)', claim)
        
        # 3. 핵심 동사/명사 (사실 관련)
        key_terms = []
        fact_keywords = [
            '설립', '창립', '출시', '발표', '발매', '개발', '인수', '합병', '상장',
            '매출', '수익', '손실', '투자', '자금', '펀딩', '계약', '협약',
            'CEO', '대표', '회장', '사장', '임원', '직원', '근무',
            '본사', '지사', '공장', '연구소', '센터',
            '제품', '서비스', '기술', '특허', '브랜드'
        ]
        
        for keyword in fact_keywords:
            if keyword in claim:
                key_terms.append(keyword)
        
        # 4. 영어 단어 (브랜드명, 제품명 등)
        english_words = re.findall(r'[A-Za-z]{2,}', claim)
        # 일반적인 영어 단어 제외
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        english_words = [word for word in english_words if word.lower() not in common_words]
        
        # 5. 모든 키워드 합치기
        all_keywords = numbers + proper_nouns + key_terms + english_words
        
        # 6. 중복 제거 및 정리
        unique_keywords = []
        seen = set()
        
        for keyword in all_keywords:
            keyword = keyword.strip()
            if keyword and len(keyword) >= 2 and keyword not in seen:
                unique_keywords.append(keyword)
                seen.add(keyword)
        
        # 7. 최대 10개 키워드만 사용 (성능 고려)
        return unique_keywords[:10]
    
    async def get_fact_check(self, claim: str) -> Optional[dict]:
        """Fact check 결과 조회"""
        try:
            claim_hash = self._hash_claim(claim)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT result, expires_at 
                    FROM fact_check_cache 
                    WHERE claim_hash = ? AND expires_at > datetime('now')
                """, (claim_hash,))
                
                row = cursor.fetchone()
                if row:
                    logger.debug(f"Cache hit for claim: {claim[:50]}...")
                    return json.loads(row['result'])
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get fact check from cache: {str(e)}")
            return None
    
    async def set_fact_check(self, claim: str, result: dict, ttl: Optional[int] = None) -> bool:
        """Fact check 결과 저장"""
        try:
            claim_hash = self._hash_claim(claim)
            expires_at = datetime.utcnow() + timedelta(seconds=ttl or self.ttl)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO fact_check_cache 
                    (claim_hash, claim_text, result, expires_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    claim_hash,
                    claim,
                    json.dumps(result),
                    expires_at.isoformat()
                ))
                
                conn.commit()
                logger.debug(f"Cached fact check for claim: {claim[:50]}...")
                return True
                
        except Exception as e:
            logger.error(f"Failed to set fact check cache: {str(e)}")
            return False
    
    async def cleanup_expired(self) -> int:
        """만료된 캐시 정리"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM fact_check_cache 
                    WHERE expires_at <= datetime('now')
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired cache: {str(e)}")
            return 0
    
    async def get_stats(self) -> dict:
        """캐시 통계"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_entries,
                        COUNT(CASE WHEN expires_at > datetime('now') THEN 1 END) as active_entries,
                        COUNT(CASE WHEN expires_at <= datetime('now') THEN 1 END) as expired_entries
                    FROM fact_check_cache
                """)
                
                row = cursor.fetchone()
                return {
                    'total_entries': row[0],
                    'active_entries': row[1], 
                    'expired_entries': row[2],
                    'db_path': str(self.db_path),
                    'ttl_seconds': self.ttl
                }
                
        except Exception as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {}
    
    async def clear_all(self) -> bool:
        """전체 캐시 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM fact_check_cache")
                conn.commit()
                logger.info("All cache entries cleared")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear cache: {str(e)}")
            return False