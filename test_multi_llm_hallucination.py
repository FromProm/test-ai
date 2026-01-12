#!/usr/bin/env python3
"""
다중 LLM 교차 검증 기반 환각탐지 테스트 스크립트
"""
import asyncio
import logging
import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.orchestrator.context import ExecutionContext
from app.orchestrator.stages.judge_stage import JudgeStage
from app.core.schemas import ExampleInput

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_multi_llm_hallucination_detection():
    """다중 LLM 환각탐지 테스트"""
    
    try:
        # ExecutionContext 생성
        context = ExecutionContext()
        
        # JudgeStage 초기화
        judge_stage = JudgeStage(context)
        
        # 테스트용 실행 결과 (일부는 사실, 일부는 거짓 정보 포함)
        test_execution_results = {
            'executions': [
                {
                    'input_index': 0,
                    'outputs': [
                        "삼성전자는 2023년에 300조원의 매출을 기록했습니다. 이는 전년 대비 15% 증가한 수치입니다.",
                        "애플은 2007년에 첫 번째 아이폰을 출시했으며, 이는 스마트폰 시장에 혁명을 일으켰습니다.",
                        "구글은 1998년에 래리 페이지와 세르게이 브린에 의해 설립되었습니다."
                    ]
                },
                {
                    'input_index': 1,
                    'outputs': [
                        "마이크로소프트는 2025년에 1조 달러의 매출을 달성할 예정입니다.",  # 미래 예측 - 검증 어려움
                        "테슬라의 CEO 일론 머스크는 화성에 도시를 건설하겠다고 발표했습니다.",  # 부분적 사실
                        "비트코인은 2009년에 사토시 나카모토에 의해 만들어졌습니다."  # 사실
                    ]
                }
            ]
        }
        
        # 테스트용 예시 입력
        example_inputs = [
            ExampleInput(content="삼성전자의 최근 실적에 대해 알려주세요."),
            ExampleInput(content="주요 기술 기업들의 현황을 설명해주세요.")
        ]
        
        logger.info("Starting Multi-LLM hallucination detection test...")
        
        # 환각탐지 실행
        result = await judge_stage.execute(example_inputs, test_execution_results)
        
        # 결과 출력
        print("\n" + "="*80)
        print("다중 LLM 교차 검증 기반 환각탐지 결과")
        print("="*80)
        print(f"환각 점수: {result.score:.2f}/100 (낮을수록 좋음)")
        print(f"총 클레임 수: {result.details.get('total_claims', 0)}")
        print(f"유니크 클레임 수: {result.details.get('unique_claims', 0)}")
        print(f"평균 검증 점수: {result.details.get('average_verification_score', 0):.2f}/100")
        print(f"캐시 히트: {result.details.get('cache_hits', 0)}")
        print(f"새로운 검증: {result.details.get('new_verifications', 0)}")
        print(f"검증 방법: {result.details.get('verification_method', 'Unknown')}")
        print(f"사용된 모델: {', '.join(result.details.get('models_used', ['Claude Sonnet 4.5', 'GPT OSS 120B', 'Claude 3.5 Sonnet']))}")
        print(f"근거 출처: {result.details.get('evidence_source', 'Wikipedia MCP')}")
        print(f"캐시 시스템: {result.details.get('cache_system', 'Hybrid (Memory + SQLite + DynamoDB)')}")
        print(f"검증 방법: {result.details.get('verification_method', 'Wikipedia Evidence-based Multi-LLM Cross-Verification')}")
        
        print("\n검증된 클레임들:")
        print("-" * 80)
        for i, claim_info in enumerate(result.details.get('verified_claims', []), 1):
            claim = claim_info.get('claim', '')
            score = claim_info.get('verification_score', 0)
            print(f"{i:2d}. [{score:5.1f}] {claim}")
        
        # 하이브리드 캐시 통계 출력
        print("\n하이브리드 캐시 통계:")
        print("-" * 80)
        try:
            cache_stats = await judge_stage.get_cache_stats()
            
            if 'overall' in cache_stats:
                overall = cache_stats['overall']
                print(f"전체 요청: {overall['total_requests']}")
                print(f"캐시 히트: {overall['cache_hits']} ({overall['hit_rate_percent']:.1f}%)")
                print(f"캐시 미스: {overall['cache_misses']}")
            
            if 'by_layer' in cache_stats:
                by_layer = cache_stats['by_layer']
                print(f"메모리 히트: {by_layer['memory_hits']} ({by_layer['memory_hit_rate']:.1f}%)")
                print(f"SQLite 히트: {by_layer['sqlite_hits']} ({by_layer['sqlite_hit_rate']:.1f}%)")
                print(f"DynamoDB 히트: {by_layer['dynamodb_hits']} ({by_layer['dynamodb_hit_rate']:.1f}%)")
            
            if 'memory_cache' in cache_stats:
                memory = cache_stats['memory_cache']
                print(f"메모리 캐시 사용량: {memory['size']}/{memory['max_size']} ({memory['usage_percent']:.1f}%)")
            
            if 'dynamodb_cache' in cache_stats:
                dynamodb = cache_stats['dynamodb_cache']
                if dynamodb.get('status') == 'active':
                    print(f"DynamoDB 테이블: {dynamodb.get('table_name', 'N/A')}")
                    print(f"DynamoDB 항목 수: {dynamodb.get('item_count', 0)}")
                    print(f"DynamoDB 크기: {dynamodb.get('table_size_mb', 0):.2f} MB")
                else:
                    print(f"DynamoDB 상태: {dynamodb.get('status', 'unknown')}")
            
        except Exception as e:
            print(f"캐시 통계 조회 실패: {str(e)}")
        
        print("\n" + "="*80)
        
        return result
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

async def main():
    """메인 함수"""
    try:
        result = await test_multi_llm_hallucination_detection()
        print(f"\n테스트 완료! 환각 점수: {result.score:.2f}")
        
    except Exception as e:
        logger.error(f"테스트 실패: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())