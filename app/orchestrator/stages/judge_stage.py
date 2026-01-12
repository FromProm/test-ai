import logging
import asyncio
import re
from typing import Dict, Any, List, Optional
from app.orchestrator.context import ExecutionContext
from app.core.config import settings
from app.core.schemas import MetricScore, ExampleInput, ClaimType, Verdict
from app.adapters.fact_checker import WikipediaEvidenceVerifier
from app.cache.hybrid_cache import HybridFactCheckCache

logger = logging.getLogger(__name__)

class JudgeStage:
    """환각 탐지 단계 - Wikipedia 근거 기반 다중 LLM 교차 검증 (하이브리드 캐싱)"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        self.wikipedia_verifier = WikipediaEvidenceVerifier(context)
        self.cache = HybridFactCheckCache(
            memory_max_size=getattr(settings, 'memory_cache_size', 1000),
            sqlite_db_path="fact_check_cache.db",
            dynamodb_table_name=getattr(settings, 'dynamodb_cache_table', None)
        )
    
    async def execute(
        self, 
        example_inputs: List[ExampleInput], 
        execution_results: Dict[str, Any]
    ) -> MetricScore:
        """
        환각 탐지 점수 계산 (Wikipedia 근거 기반 다중 LLM 교차 검증)
        1. 모든 출력에서 검증 가능한 사실 주장 추출
        2. claim 통합 + 중복 제거
        3. Wikipedia에서 관련 근거 수집
        4. 근거를 바탕으로 다중 LLM 교차 검증 (Claude Sonnet 4.5, GPT OSS 120B, Claude 3.5 Sonnet)
        5. 근거 기반 합의 알고리즘으로 최종 점수 계산
        """
        logger.info("Running hallucination detection with Wikipedia evidence-based Multi-LLM verification")
        
        try:
            judge = self.context.get_judge()
            executions = execution_results['executions']
            
            # [1단계] 모든 출력에서 claim 병렬 추출
            claim_extraction_tasks = []
            output_info = []  # 출력 정보 저장
            
            for exec_data in executions:
                input_index = exec_data['input_index']
                outputs = exec_data['outputs']
                
                for output_idx, output in enumerate(outputs):
                    if output.strip():
                        task = self._extract_claims_from_output(judge, output)
                        claim_extraction_tasks.append(task)
                        output_info.append({
                            'input_index': input_index,
                            'output_index': output_idx,
                            'output': output
                        })
            
            logger.info(f"Extracting claims from {len(claim_extraction_tasks)} outputs in parallel")
            
            # 병렬 claim 추출
            extraction_results = await asyncio.gather(*claim_extraction_tasks, return_exceptions=True)
            
            # [2단계] claim 통합 및 중복 제거
            all_claims = []
            claim_sources = {}  # claim -> 출처 정보
            
            for i, result in enumerate(extraction_results):
                if isinstance(result, Exception):
                    logger.error(f"Claim extraction failed for output {i}: {str(result)}")
                    continue
                
                if isinstance(result, list):
                    # 직접 claim 리스트가 반환된 경우
                    for claim_text in result:
                        if claim_text and len(claim_text) > 10:
                            all_claims.append(claim_text)
                            if claim_text not in claim_sources:
                                claim_sources[claim_text] = []
                            claim_sources[claim_text].append(output_info[i])
            
            # 중복 제거
            unique_claims = list(set(all_claims))
            logger.info(f"Found {len(unique_claims)} unique claims from {len(all_claims)} total claims")
            
            if not unique_claims:
                logger.warning("No verifiable claims found in outputs")
                return MetricScore(
                    score=0.0,  # claim이 없으면 환각도 없음 (낮은 점수 = 좋음)
                    details={
                        'total_claims': 0,
                        'unique_claims': 0,
                        'verified_claims': [],
                        'average_verification_score': 100.0,
                        'note': 'No verifiable claims found'
                    }
                )
            
            # [3단계] 하이브리드 캐시 확인 및 새 claim 필터링
            new_claims = []
            cached_scores = {}
            
            for claim in unique_claims:
                cached_result = await self.cache.get_fact_check(claim)
                if cached_result:
                    cached_scores[claim] = cached_result['score']
                    logger.debug(f"Using cached score for claim: {claim[:50]}...")
                else:
                    new_claims.append(claim)
            
            logger.info(f"Cache hits: {len(cached_scores)}, New claims to verify: {len(new_claims)}")
            
            # [4단계] Wikipedia 근거 기반 다중 LLM 교차 검증
            new_scores = {}
            if new_claims:
                logger.info(f"Wikipedia evidence-based verifying {len(new_claims)} claims")
                
                try:
                    scores = await self.wikipedia_verifier.verify_claims_batch(new_claims)
                    
                    for claim, score in zip(new_claims, scores):
                        new_scores[claim] = score
                        # 하이브리드 캐시에 저장 (설정된 TTL 사용)
                        ttl = getattr(settings, 'cache_fact_check_ttl', 30*24*3600)
                        await self.cache.set_fact_check(claim, {'score': score}, ttl=ttl)
                        
                except Exception as e:
                    logger.error(f"Wikipedia evidence-based verification failed: {str(e)}")
                    # 실패 시 기본 점수 할당
                    for claim in new_claims:
                        new_scores[claim] = 50.0  # 중간 점수
            
            # [5단계] 모든 점수 통합
            all_scores = {**cached_scores, **new_scores}
            
            # [6단계] 최종 점수 계산
            if all_scores:
                # 개별 claim 점수들의 평균 (0-100 범위)
                individual_scores = list(all_scores.values())
                average_verification_score = sum(individual_scores) / len(individual_scores)
                
                # 환각 탐지 관점에서 점수 해석
                # 높은 검증 점수 = 사실 확인됨 = 환각 적음
                # 낮은 검증 점수 = 사실 확인 안됨 = 환각 많음
                # 환각 점수 = 100 - 검증 점수 (역전)
                final_score = 100.0 - average_verification_score
                
                logger.info(f"Wikipedia evidence-based hallucination detection completed: {final_score:.3f} "
                          f"(unique claims: {len(unique_claims)}, average verification: {average_verification_score:.1f})")
            else:
                final_score = 0.0  # 검증할 claim이 없으면 환각 없음
                average_verification_score = 100.0
            
            # 상세 정보 구성
            verified_claims = [
                {
                    'claim': claim,
                    'verification_score': score
                }
                for claim, score in all_scores.items()
            ]
            
            details = {
                'total_claims': len(all_claims),
                'unique_claims': len(unique_claims),
                'verified_claims': verified_claims,
                'average_verification_score': average_verification_score,
                'cache_hits': len(cached_scores),
                'new_verifications': len(new_scores),
                'verification_method': 'Wikipedia Evidence-based Multi-LLM Cross-Verification',
                'models_used': ['Claude Sonnet 4.5', 'GPT OSS 120B', 'Claude 3.5 Sonnet'],
                'evidence_source': 'Wikipedia MCP',
                'cache_system': 'Hybrid (Memory + SQLite + DynamoDB)',
                'note': 'Wikipedia evidence collection → Multi-LLM cross-verification with consensus algorithm'
            }
            
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Hallucination detection failed: {str(e)}")
            return MetricScore(score=50.0, details={'error': str(e), 'note': 'Verification failed, using neutral score'})
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """하이브리드 캐시 통계 조회"""
        try:
            return await self.cache.get_comprehensive_stats()
        except Exception as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {'error': str(e)}
    
    async def cleanup_cache(self) -> Dict[str, int]:
        """캐시 정리"""
        try:
            return await self.cache.cleanup_expired()
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {str(e)}")
            return {'error': str(e)}
    
    async def force_dynamodb_batch_save(self) -> int:
        """DynamoDB 배치 저장 강제 실행"""
        try:
            return await self.cache.force_dynamodb_batch_save()
        except Exception as e:
            logger.error(f"Failed to force DynamoDB batch save: {str(e)}")
            return 0
    
    async def _extract_claims_from_output(self, judge, output: str) -> List[str]:
        """출력에서 검증 가능한 claim들을 추출 (Claude Haiku 사용)"""
        try:
            # 구조화된 프롬프트로 검증 가능한 사실 주장 추출
            prompt = f"""다음 텍스트에서 외부 자료로 검증 가능한 구체적인 사실 주장들을 추출해주세요.

텍스트:
{output}

추출 기준:
- 날짜, 숫자, 인물명, 회사명 등 구체적 정보가 포함된 문장
- 외부 검색으로 참/거짓을 확인할 수 있는 객관적 사실
- 주관적 의견이나 일반적 설명은 제외
- 중복된 내용은 하나로 통합

JSON 형식으로 응답:
{{
  "verifiable_claims": [
    "삼성전자의 2023년 매출은 300조원이다",
    "애플은 2007년에 아이폰을 출시했다"
  ]
}}

검증 가능한 사실이 없으면 빈 배열로 응답하세요."""
            
            result = await judge.analyze_text(prompt)
            
            # JSON 파싱 시도
            import json
            import re
            
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    claims = data.get('verifiable_claims', [])
                    
                    # 필터링: 최소 길이 및 유효성 검사
                    filtered_claims = []
                    for claim in claims:
                        if isinstance(claim, str) and len(claim.strip()) > 10:
                            filtered_claims.append(claim.strip())
                    
                    return filtered_claims
                    
                except json.JSONDecodeError:
                    logger.warning("JSON parsing failed, falling back to line-by-line parsing")
            
            # JSON 파싱 실패 시 기존 방식으로 폴백
            if result.strip().upper() == "NONE" or not result.strip():
                return []
            
            # 결과를 줄별로 분리하여 반환
            claims = []
            for line in result.split('\n'):
                line = line.strip()
                if line and line.upper() != "NONE" and len(line) > 10:
                    # 불필요한 마커 제거
                    line = re.sub(r'^[-*•]\s*', '', line)
                    if line:
                        claims.append(line)
            
            return claims
            
        except Exception as e:
            logger.error(f"Failed to extract claims from output: {str(e)}")
            return []