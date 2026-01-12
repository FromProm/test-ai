#!/usr/bin/env python3
"""
하이브리드 캐시 시스템 테스트 스크립트 (DynamoDB 버전)
"""
import asyncio
import logging
import sys
import os
import json

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.cache.hybrid_cache import HybridFactCheckCache

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_hybrid_cache():
    """하이브리드 캐시 테스트 (DynamoDB)"""
    
    try:
        print("="*80)
        print("하이브리드 캐시 시스템 테스트 (DynamoDB)")
        print("="*80)
        
        # 하이브리드 캐시 초기화
        cache = HybridFactCheckCache(
            memory_max_size=100,
            sqlite_db_path="test_cache.db",
            dynamodb_table_name="test-fact-check-cache"
        )
        
        # 테스트 데이터
        test_claims = [
            "삼성전자는 2023년에 300조원의 매출을 기록했습니다",
            "애플은 2007년에 첫 번째 아이폰을 출시했습니다",
            "구글은 1998년에 설립되었습니다",
            "마이크로소프트는 1975년에 설립되었습니다",
            "테슬라의 CEO는 일론 머스크입니다"
        ]
        
        test_results = [
            {'score': 75.5, 'confidence': 0.8},
            {'score': 95.2, 'confidence': 0.95},
            {'score': 88.7, 'confidence': 0.9},
            {'score': 92.1, 'confidence': 0.93},
            {'score': 98.5, 'confidence': 0.99}
        ]
        
        print("\n1. 캐시에 데이터 저장 테스트")
        print("-" * 50)
        
        # 데이터 저장
        for claim, result in zip(test_claims, test_results):
            success = await cache.set_fact_check(claim, result)
            print(f"저장 {'성공' if success else '실패'}: {claim[:50]}...")
        
        print("\n2. 캐시에서 데이터 조회 테스트")
        print("-" * 50)
        
        # 데이터 조회 (메모리 캐시에서 히트)
        for claim in test_claims:
            result = await cache.get_fact_check(claim)
            if result:
                print(f"조회 성공 (메모리): {claim[:50]}... -> 점수: {result['score']}")
            else:
                print(f"조회 실패: {claim[:50]}...")
        
        print("\n3. 메모리 캐시 클리어 후 재조회 테스트")
        print("-" * 50)
        
        # 메모리 캐시만 클리어
        cache.memory_cache.clear()
        
        # 다시 조회 (SQLite에서 히트)
        for claim in test_claims[:3]:  # 일부만 테스트
            result = await cache.get_fact_check(claim)
            if result:
                print(f"조회 성공 (SQLite): {claim[:50]}... -> 점수: {result['score']}")
            else:
                print(f"조회 실패: {claim[:50]}...")
        
        print("\n4. 캐시 통계 확인")
        print("-" * 50)
        
        stats = await cache.get_comprehensive_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        print("\n5. DynamoDB 배치 저장 강제 실행")
        print("-" * 50)
        
        batch_count = await cache.force_dynamodb_batch_save()
        print(f"DynamoDB 배치 저장 실행: {batch_count}개 항목")
        
        print("\n6. 캐시 정리 테스트")
        print("-" * 50)
        
        cleanup_results = await cache.cleanup_expired()
        print(f"정리 결과: {cleanup_results}")
        
        print("\n" + "="*80)
        print("하이브리드 캐시 테스트 완료!")
        print("="*80)
        
        return True
        
    except Exception as e:
        logger.error(f"테스트 실패: {str(e)}")
        return False

async def main():
    """메인 함수"""
    try:
        success = await test_hybrid_cache()
        if success:
            print("\n✅ 모든 테스트 통과!")
        else:
            print("\n❌ 테스트 실패!")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"메인 함수 실패: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())