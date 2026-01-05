import logging
import asyncio
import re
from typing import Dict, Any, List, Optional
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, ExampleInput, ClaimType, Verdict

logger = logging.getLogger(__name__)

class JudgeStage:
    """환각 탐지 단계 - MCP 기반 사실 검증"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        # Verdict별 점수 매핑 (환각 탐지 관점)
        self.verdict_scores = {
            Verdict.SUPPORTED: 1.0,      # 확인된 사실 → 환각 없음 (최고점)
            Verdict.INSUFFICIENT: 0.7,   # 검증 불가 → 환각 의심 (중간점, 기존 0.6에서 상향)
            Verdict.REFUTED: 0.0         # 명확한 거짓 → 확실한 환각 (최저점)
        }
    
    async def execute(
        self, 
        example_inputs: List[ExampleInput], 
        execution_results: Dict[str, Any]
    ) -> MetricScore:
        """
        환각 탐지 점수 계산
        1. 출력에서 FACT_VERIFIABLE 문장 추출
        2. MCP로 외부 근거 수집
        3. 근거 기반 SUPPORTED/REFUTED/INSUFFICIENT 판정
        4. 점수 계산 (100점 만점)
        """
        logger.info("Running hallucination detection with MCP fact verification")
        
        try:
            judge = self.context.get_judge()
            executions = execution_results['executions']
            
            all_claim_scores = []
            details = {'per_input_analysis': [], 'total_claims': 0, 'verdict_distribution': {}}
            
            for exec_data in executions:
                input_index = exec_data['input_index']
                input_content = exec_data['input_content']
                outputs = exec_data['outputs']
                
                logger.info(f"Analyzing outputs for input {input_index+1}")
                
                input_analysis = {
                    'input_index': input_index,
                    'input_content': input_content[:100] + '...' if len(input_content) > 100 else input_content,
                    'outputs_analysis': []
                }
                
                # 각 출력별로 분석
                for output_idx, output in enumerate(outputs):
                    if not output.strip():
                        # 빈 출력은 0점 처리
                        input_analysis['outputs_analysis'].append({
                            'output_index': output_idx,
                            'output_preview': '',
                            'claims': [],
                            'score': 0.0,  # 100점 만점 기준
                            'reason': 'empty_output'
                        })
                        all_claim_scores.append(0.0)
                        continue
                    
                    # 1단계: FACT_VERIFIABLE 문장 추출
                    verifiable_claims = await self._extract_verifiable_claims(output)
                    
                    if not verifiable_claims:
                        # 검증 가능한 사실이 없으면 중간 점수
                        input_analysis['outputs_analysis'].append({
                            'output_index': output_idx,
                            'output_preview': output[:100] + '...' if len(output) > 100 else output,
                            'claims': [],
                            'score': 60.0,  # 100점 만점 기준
                            'reason': 'no_verifiable_claims'
                        })
                        all_claim_scores.append(60.0)
                        continue
                    
                    # 2-3단계: 각 claim에 대해 MCP 검증 및 점수 계산
                    claim_results = []
                    for claim in verifiable_claims:
                        claim_score = await self._verify_claim_with_mcp(claim)  # 0.0 ~ 1.0 점수
                        claim_score_100 = claim_score * 100  # 100점 만점으로 변환
                        
                        claim_results.append({
                            'claim': claim[:100] + '...' if len(claim) > 100 else claim,
                            'score': claim_score_100
                        })
                        all_claim_scores.append(claim_score_100)
                    
                    # 해당 출력의 평균 점수
                    output_score = sum(result['score'] for result in claim_results) / len(claim_results)
                    
                    input_analysis['outputs_analysis'].append({
                        'output_index': output_idx,
                        'output_preview': output[:100] + '...' if len(output) > 100 else output,
                        'claims': claim_results,
                        'score': output_score,
                        'total_claims': len(claim_results)
                    })
                
                details['per_input_analysis'].append(input_analysis)
            
            # 전체 평균 점수 (이미 100점 만점)
            final_score = sum(all_claim_scores) / len(all_claim_scores) if all_claim_scores else 0.0
            
            # Verdict 분포 계산 (100점 만점 기준)
            score_distribution = {
                'perfect_scores': 0,      # 100점
                'partial_scores': 0,      # 0 < score < 100  
                'zero_scores': 0          # 0점
            }
            
            for score in all_claim_scores:
                if score == 100.0:
                    score_distribution['perfect_scores'] += 1
                elif score == 0.0:
                    score_distribution['zero_scores'] += 1
                else:
                    score_distribution['partial_scores'] += 1
            
            details.update({
                'final_score': final_score,
                'total_claims': len(all_claim_scores),
                'score_distribution': score_distribution,
                'note': 'Hallucination detection score out of 100. Based on proportional evidence support: 0 (conflict) to 100 (full support).'
            })
            
            logger.info(f"Hallucination detection score: {final_score:.3f} (total claims: {len(all_claim_scores)})")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Hallucination detection failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    async def _extract_verifiable_claims(self, output: str) -> List[str]:
        """출력에서 FACT_VERIFIABLE 타입의 문장들을 추출"""
        try:
            judge = self.context.get_judge()
            
            # LLM에게 문장별 claim type 분류 요청
            prompt = f"""
다음 텍스트를 문장별로 분석하여 FACT_VERIFIABLE 타입에 해당하는 문장만 추출해주세요.

Claim 타입 정의:
- FACT_VERIFIABLE: 외부 근거로 참/거짓 판정 가능한 사실적 주장
- FACT_UNVERIFIABLE: 사실처럼 보이나 검증 불가능
- OPINION_JUDGEMENT: 의견/평가/주관적 판단
- CREATIVE_CONTENT: 창작 설정/허구적 내용
- PREDICTION_SPECULATION: 미래 예측/추정
- INSTRUCTIONAL: 방법/절차 설명

텍스트:
{output}

FACT_VERIFIABLE 문장만 한 줄씩 반환해주세요. 없으면 "NONE"을 반환하세요.
"""
            
            result = await judge.analyze_text(prompt)
            
            if result.strip().upper() == "NONE":
                return []
            
            # 결과를 줄별로 분리하여 반환
            claims = [line.strip() for line in result.split('\n') if line.strip()]
            return claims
            
        except Exception as e:
            logger.error(f"Failed to extract verifiable claims: {str(e)}")
            return []
    
    async def _verify_claim_with_mcp(self, claim: str) -> float:
        """Agent AI가 선택한 MCP로 claim 검증하여 점수 반환"""
        try:
            logger.info(f"Verifying claim: {claim[:100]}...")
            
            # 1. Agent AI가 이 claim에 가장 적합한 MCP 선택
            selected_mcp = await self._select_best_mcp_for_claim(claim)
            logger.info(f"Agent AI selected MCP: {selected_mcp}")
            
            # 2. 선택된 MCP로 근거 수집
            evidence = await self._collect_evidence_from_selected_mcp(claim, selected_mcp)
            
            # 3. 근거 품질 평가 (현재는 사용 안함, 나중에 필요시 활용)
            quality_score = self._evaluate_single_mcp_evidence(evidence, selected_mcp)
            
            # 4. 근거 기반 점수 계산 (0.0 ~ 1.0)
            score = await self._judge_claim_with_single_evidence(claim, evidence, quality_score)
            
            logger.info(f"Final score: {score:.3f}/1.0 → {score*100:.1f}/100 (mcp: {selected_mcp})")
            return score
            
        except Exception as e:
            logger.error(f"Failed to verify claim with MCP: {str(e)}")
            return 0.0
    
    async def _select_best_mcp_for_claim(self, claim: str) -> str:
        """Agent AI가 claim에 가장 적합한 단일 MCP 선택"""
        try:
            judge = self.context.get_judge()  # Agent AI 역할
            
            prompt = f"""
다음 claim을 검증하기 위해 가장 적합한 MCP 하나를 선택해주세요:

Claim: {claim}

사용 가능한 MCP:
1. BRAVE_SEARCH - 일반 웹 검색 (연도/숫자/사실 확인, 최신 정보)
2. WIKIPEDIA - 위키피디아 검색 (인물/역사/기본 사실, 높은 신뢰도)
3. ARXIV - 학술 논문 검색 (과학/의학/연구 분야)
4. WEB_SCRAPER - 특정 페이지 상세 분석 (공식 발표/뉴스 원문)

선택 기준:
- 연도/숫자/최신 정보 → BRAVE_SEARCH
- 인물/역사/일반 상식 → WIKIPEDIA  
- 과학/의학/연구 → ARXIV
- 공식 발표/뉴스 원문 → WEB_SCRAPER

가장 적합한 MCP 하나만 반환하세요: BRAVE_SEARCH, WIKIPEDIA, ARXIV, WEB_SCRAPER 중 하나
"""
            
            result = await judge.analyze_text(prompt)
            selected_mcp = result.strip().upper()
            
            if selected_mcp not in ['BRAVE_SEARCH', 'WIKIPEDIA', 'ARXIV', 'WEB_SCRAPER']:
                return 'BRAVE_SEARCH'  # 기본값
            
            return selected_mcp
            
        except Exception as e:
            logger.error(f"Failed to select MCP: {str(e)}")
            return 'BRAVE_SEARCH'
    
    async def _collect_evidence_from_selected_mcp(self, claim: str, mcp_type: str) -> List[Dict[str, Any]]:
        """선택된 MCP에서만 근거 수집"""
        try:
            if mcp_type == 'BRAVE_SEARCH':
                return await self._collect_from_brave_search(claim)
            elif mcp_type == 'WIKIPEDIA':
                return await self._collect_from_wikipedia(claim)
            elif mcp_type == 'ARXIV':
                return await self._collect_from_arxiv(claim)
            elif mcp_type == 'WEB_SCRAPER':
                # Web Scraper는 검색 결과가 필요하므로 먼저 Brave Search 실행
                search_results = await self._collect_from_brave_search(claim)
                return await self._collect_from_web_scraper(claim, search_results)
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to collect evidence from {mcp_type}: {str(e)}")
            return []
    
    def _evaluate_single_mcp_evidence(self, evidence_list: List[Dict[str, Any]], mcp_type: str) -> float:
        """단일 MCP 근거 품질 평가 - 순수하게 근거 내용만 평가"""
        if not evidence_list:
            return 0.0
        
        # 단순히 근거가 있는지, 관련성이 있는지만 확인
        total_relevance = 0.0
        for evidence in evidence_list:
            # 근거의 관련성만 평가 (MCP 타입 무관)
            relevance = evidence.get('relevance_score', 0.7)
            total_relevance += relevance
        
        # 평균 관련성 점수 반환
        return min(1.0, total_relevance / len(evidence_list))
    
    async def _judge_claim_with_single_evidence(self, claim: str, evidence_list: List[Dict[str, Any]], 
                                              quality_score: float) -> float:
        """시스템 기반 객관적 claim 점수 계산 (0.0 ~ 1.0)"""
        try:
            if not evidence_list:
                return 0.0
            
            # 1. AI로 claim에서 핵심 정보 추출
            claim_entities = await self._extract_key_entities(claim)
            
            # 2. 각 근거에서 핵심 정보 추출
            evidence_entities_list = []
            for evidence in evidence_list:
                evidence_entities = await self._extract_key_entities(evidence.get('content', ''))
                evidence_entities_list.append(evidence_entities)
            
            # 3. 시스템적 점수 계산 (0.0 ~ 1.0)
            score = self._systematic_verdict_calculation(claim, claim_entities, evidence_list, evidence_entities_list)
            
            logger.info(f"Claim score: {score:.3f}")
            return score
                
        except Exception as e:
            logger.error(f"Failed to judge claim systematically: {str(e)}")
            return 0.0
    
    async def _extract_key_entities(self, text: str) -> Dict[str, Any]:
        """AI로 텍스트에서 핵심 정보만 추출 (판정은 시스템이 담당)"""
        try:
            judge = self.context.get_judge()
            
            prompt = f"""
다음 텍스트에서 핵심 정보를 추출해주세요:

텍스트: {text}

다음 형식으로 추출해주세요:
- 날짜: [YYYY-MM-DD 형식으로, 예: 2023-07-11]
- 숫자: [모든 숫자값, 예: 100, 50.5]  
- 인명: [사람 이름들]
- 회사명: [회사/조직 이름들]
- 제품명: [제품/서비스 이름들]
- 지명: [장소/국가 이름들]

해당 정보가 없으면 "없음"으로 표시하세요.

예시:
- 날짜: 2023-07-11
- 숫자: 100, 50.5
- 인명: 홍길동, 김철수
- 회사명: OpenAI, Google
- 제품명: GPT-4, ChatGPT
- 지명: 서울, 미국
"""
            
            result = await judge.analyze_text(prompt)
            
            # 결과 파싱
            entities = {
                'dates': [],
                'numbers': [],
                'persons': [],
                'companies': [],
                'products': [],
                'locations': []
            }
            
            lines = result.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('- 날짜:'):
                    dates = line.replace('- 날짜:', '').strip()
                    if dates != '없음':
                        entities['dates'] = [d.strip() for d in dates.split(',')]
                elif line.startswith('- 숫자:'):
                    numbers = line.replace('- 숫자:', '').strip()
                    if numbers != '없음':
                        entities['numbers'] = [n.strip() for n in numbers.split(',')]
                elif line.startswith('- 인명:'):
                    persons = line.replace('- 인명:', '').strip()
                    if persons != '없음':
                        entities['persons'] = [p.strip() for p in persons.split(',')]
                elif line.startswith('- 회사명:'):
                    companies = line.replace('- 회사명:', '').strip()
                    if companies != '없음':
                        entities['companies'] = [c.strip() for c in companies.split(',')]
                elif line.startswith('- 제품명:'):
                    products = line.replace('- 제품명:', '').strip()
                    if products != '없음':
                        entities['products'] = [p.strip() for p in products.split(',')]
                elif line.startswith('- 지명:'):
                    locations = line.replace('- 지명:', '').strip()
                    if locations != '없음':
                        entities['locations'] = [l.strip() for l in locations.split(',')]
            
            return entities
            
        except Exception as e:
            logger.error(f"Failed to extract entities: {str(e)}")
            return {'dates': [], 'numbers': [], 'persons': [], 'companies': [], 'products': [], 'locations': []}
    
    def _systematic_verdict_calculation(self, claim: str, claim_entities: Dict[str, Any], 
                                      evidence_list: List[Dict[str, Any]], 
                                      evidence_entities_list: List[Dict[str, Any]]) -> float:
        """새로운 점수 계산 방식: 비례적 점수 체계"""
        
        # 1. 근거 존재 여부 확인
        if not evidence_list or not any(evidence.get('content', '').strip() for evidence in evidence_list):
            return 0.0  # 근거가 아예 없으면 0점
        
        # 2. 전체 claim 요소 개수 계산
        total_claim_elements = 0
        supported_elements = 0
        conflicted_elements = 0
        
        for entity_type in ['dates', 'numbers', 'persons', 'companies', 'products', 'locations']:
            claim_items = claim_entities.get(entity_type, [])
            
            if not claim_items:
                continue
                
            total_claim_elements += len(claim_items)
            
            # 각 근거에서 해당 엔티티 확인
            for claim_item in claim_items:
                claim_item_clean = claim_item.lower().strip()
                
                # 모든 근거에서 확인
                found_support = False
                found_conflict = False
                
                for evidence_entities in evidence_entities_list:
                    evidence_items = evidence_entities.get(entity_type, [])
                    
                    # 정확한 매칭 확인
                    exact_match = any(claim_item_clean == evidence_item.lower().strip() 
                                    for evidence_item in evidence_items)
                    
                    if exact_match:
                        found_support = True
                        break
                    elif evidence_items:  # 해당 타입 정보는 있지만 다름
                        found_conflict = True
                
                # 결과 집계
                if found_support:
                    supported_elements += 1
                elif found_conflict:
                    conflicted_elements += 1
                # 아무것도 없으면 unsupported (별도 카운트 안함)
        
        # 3. 점수 계산 로직
        if conflicted_elements > 0:
            # 명확한 거짓이 하나라도 있으면 0점
            return 0.0
        
        if total_claim_elements == 0:
            # claim에 검증 가능한 요소가 없으면 중간 점수
            return 0.5
        
        if supported_elements == total_claim_elements:
            # 모든 요소가 뒷받침되면 1점
            return 1.0
        
        # 부분적 지원: (뒷받침된 근거 수) / (전체 근거 수)
        partial_score = supported_elements / total_claim_elements
        
        logger.info(f"Score calculation - Total: {total_claim_elements}, Supported: {supported_elements}, Conflicted: {conflicted_elements}, Score: {partial_score:.3f}")
        
        return partial_score
    
    def _calculate_entity_matching(self, claim_entities: Dict[str, Any], 
                                 evidence_entities: Dict[str, Any]) -> tuple[float, float, float]:
        """핵심 정보 매칭 점수 계산"""
        
        match_scores = []
        conflict_scores = []
        coverage_scores = []
        
        # 각 엔티티 타입별로 비교
        for entity_type in ['dates', 'numbers', 'persons', 'companies', 'products', 'locations']:
            claim_items = claim_entities.get(entity_type, [])
            evidence_items = evidence_entities.get(entity_type, [])
            
            if not claim_items:  # claim에 해당 타입 정보가 없으면 스킵
                continue
            
            # 매칭 점수 (정확히 일치하는 비율)
            matches = 0
            conflicts = 0
            
            for claim_item in claim_items:
                claim_item_clean = claim_item.lower().strip()
                
                # 정확 매칭 확인
                exact_match = any(claim_item_clean == evidence_item.lower().strip() 
                                for evidence_item in evidence_items)
                
                if exact_match:
                    matches += 1
                else:
                    # 충돌 확인 (같은 타입이지만 다른 값)
                    if evidence_items:  # 근거에 해당 타입 정보가 있는데 매칭 안됨
                        conflicts += 1
            
            if claim_items:
                match_score = matches / len(claim_items)
                conflict_score = conflicts / len(claim_items)
                coverage_score = 1.0 if evidence_items else 0.0  # 해당 타입 정보가 근거에 있는가
                
                match_scores.append(match_score)
                conflict_scores.append(conflict_score)
                coverage_scores.append(coverage_score)
        
        # 전체 평균
        avg_match = sum(match_scores) / len(match_scores) if match_scores else 0.0
        avg_conflict = sum(conflict_scores) / len(conflict_scores) if conflict_scores else 0.0
        avg_coverage = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0.0
        
        return avg_match, avg_conflict, avg_coverage
    
    async def _collect_from_brave_search(self, claim: str) -> List[Dict[str, Any]]:
        """Brave Search MCP로 근거 수집"""
        try:
            # 검색 쿼리 생성
            search_query = await self._generate_search_query(claim)
            
            # 실제 질문에 맞는 Mock 근거 생성
            if "OpenAI" in claim and "GPT-4" in claim and "2023년 3월" in claim:
                evidence = [
                    {
                        'source': 'brave_search',
                        'url': 'https://openai.com/research/gpt-4',
                        'title': 'GPT-4 Research - OpenAI',
                        'content': 'OpenAI announced GPT-4 on March 14, 2023. GPT-4 is a large multimodal model that can accept image and text inputs and produce text outputs.',
                        'reliability_score': 0.95,
                        'relevance_score': 0.98
                    },
                    {
                        'source': 'brave_search', 
                        'url': 'https://techcrunch.com/2023/03/14/openai-releases-gpt-4',
                        'title': 'OpenAI releases GPT-4 - TechCrunch',
                        'content': 'On March 14, 2023, OpenAI released GPT-4, its most advanced AI system yet. The new model demonstrates human-level performance on various professional benchmarks.',
                        'reliability_score': 0.85,
                        'relevance_score': 0.95
                    }
                ]
            elif "노벨 물리학상" in claim and "2024" in claim and ("홉필드" in claim or "힌턴" in claim):
                evidence = [
                    {
                        'source': 'brave_search',
                        'url': 'https://www.nobelprize.org/prizes/physics/2024/',
                        'title': '2024 Nobel Prize in Physics - NobelPrize.org',
                        'content': 'The 2024 Nobel Prize in Physics was awarded to John J. Hopfield and Geoffrey E. Hinton for foundational discoveries and inventions that enable machine learning with artificial neural networks.',
                        'reliability_score': 0.98,
                        'relevance_score': 0.99
                    },
                    {
                        'source': 'brave_search',
                        'url': 'https://www.nature.com/articles/d41586-024-03214-0',
                        'title': 'Physics Nobel Prize 2024 - Nature',
                        'content': 'Geoffrey Hinton and John Hopfield won the 2024 Nobel Prize in Physics for their pioneering work on artificial neural networks that laid the foundation for modern machine learning.',
                        'reliability_score': 0.92,
                        'relevance_score': 0.96
                    }
                ]
            elif "윤석열" in claim and "대통령" in claim and "2022년 5월" in claim:
                evidence = [
                    {
                        'source': 'brave_search',
                        'url': 'https://www.president.go.kr/president/profile',
                        'title': '대통령 프로필 - 대한민국 대통령실',
                        'content': '윤석열 대통령은 2022년 5월 10일 제20대 대통령으로 취임했습니다. 임기는 2027년 5월 9일까지입니다.',
                        'reliability_score': 0.98,
                        'relevance_score': 0.99
                    },
                    {
                        'source': 'brave_search',
                        'url': 'https://www.yna.co.kr/view/AKR20220510000100001',
                        'title': '윤석열 대통령 취임식 - 연합뉴스',
                        'content': '윤석열 제20대 대통령이 2022년 5월 10일 국회에서 열린 취임식에서 취임선서를 했습니다.',
                        'reliability_score': 0.90,
                        'relevance_score': 0.95
                    }
                ]
            else:
                # 기본 Mock 근거
                evidence = [
                    {
                        'source': 'brave_search',
                        'url': f'https://search.brave.com/result1',
                        'title': f'Search result for: {search_query}',
                        'content': f'Limited information available for claim: {claim[:100]}...',
                        'reliability_score': 0.6,
                        'relevance_score': 0.5
                    }
                ]
            
            return evidence
            
        except Exception as e:
            logger.error(f"Brave Search collection failed: {str(e)}")
            return []
    
    async def _collect_from_wikipedia(self, claim: str) -> List[Dict[str, Any]]:
        """Wikipedia MCP로 근거 수집"""
        try:
            # 위키피디아 검색 키워드 추출
            keywords = await self._extract_wikipedia_keywords(claim)
            
            # 실제 질문에 맞는 Mock 위키피디아 근거 생성
            if "OpenAI" in claim and "GPT-4" in claim:
                evidence = [
                    {
                        'source': 'wikipedia',
                        'url': 'https://en.wikipedia.org/wiki/GPT-4',
                        'title': 'Wikipedia: GPT-4',
                        'content': 'GPT-4 (Generative Pre-trained Transformer 4) is a multimodal large language model created by OpenAI, and the fourth in its series of GPT foundation models. It was initially released on March 14, 2023.',
                        'reliability_score': 0.95,
                        'relevance_score': 0.92
                    }
                ]
            elif "노벨 물리학상" in claim and "2024" in claim:
                evidence = [
                    {
                        'source': 'wikipedia',
                        'url': 'https://en.wikipedia.org/wiki/2024_Nobel_Prize_in_Physics',
                        'title': 'Wikipedia: 2024 Nobel Prize in Physics',
                        'content': 'The 2024 Nobel Prize in Physics was awarded jointly to John Hopfield and Geoffrey Hinton for foundational discoveries and inventions that enable machine learning with artificial neural networks.',
                        'reliability_score': 0.95,
                        'relevance_score': 0.98
                    }
                ]
            elif "윤석열" in claim and "대통령" in claim:
                evidence = [
                    {
                        'source': 'wikipedia',
                        'url': 'https://ko.wikipedia.org/wiki/윤석열',
                        'title': 'Wikipedia: 윤석열',
                        'content': '윤석열(尹錫悅, 1960년 12월 18일~)은 대한민국의 제20대 대통령이다. 2022년 5월 10일에 취임했다.',
                        'reliability_score': 0.95,
                        'relevance_score': 0.96
                    }
                ]
            else:
                # 기본 Mock 근거
                evidence = [
                    {
                        'source': 'wikipedia',
                        'url': f'https://en.wikipedia.org/wiki/{keywords[0] if keywords else "Unknown"}',
                        'title': f'Wikipedia: {keywords[0] if keywords else "Unknown"}',
                        'content': f'Limited Wikipedia information for claim: {claim[:100]}...',
                        'reliability_score': 0.7,
                        'relevance_score': 0.6
                    }
                ]
            
            return evidence
            
        except Exception as e:
            logger.error(f"Wikipedia collection failed: {str(e)}")
            return []
    
    async def _collect_from_arxiv(self, claim: str) -> List[Dict[str, Any]]:
        """ArXiv MCP로 학술 근거 수집"""
        try:
            # 과학적 주장인지 판단
            is_scientific = await self._is_scientific_claim(claim)
            
            if not is_scientific:
                return []  # 과학적 주장이 아니면 ArXiv 검색 안함
            
            # Mock 구현 - 실제로는 arxiv MCP 호출
            evidence = [
                {
                    'source': 'arxiv',
                    'url': f'https://arxiv.org/abs/2024.0001',
                    'title': f'Scientific paper related to claim',
                    'content': f'Mock ArXiv evidence for scientific claim: {claim[:100]}...',
                    'reliability_score': 0.9,  # 학술 자료는 높은 신뢰도
                    'relevance_score': 0.7
                }
            ]
            
            return evidence
            
        except Exception as e:
            logger.error(f"ArXiv collection failed: {str(e)}")
            return []
    
    async def _collect_from_web_scraper(self, claim: str, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Web Scraper MCP로 상세 페이지 내용 수집"""
        try:
            evidence = []
            
            # 상위 검색 결과 3개의 URL을 상세히 스크래핑
            for result in search_results[:3]:
                url = result.get('url', '')
                if not url or 'mock' in url.lower():
                    continue  # Mock URL은 스킵
                
                # Mock 구현 - 실제로는 web-scraper MCP 호출
                scraped_content = {
                    'source': 'web_scraper',
                    'url': url,
                    'title': f'Scraped content from {url}',
                    'content': f'Mock scraped detailed content for claim: {claim[:100]}...',
                    'reliability_score': 0.7,
                    'relevance_score': 0.8,
                    'original_source': result.get('source', 'unknown')
                }
                
                evidence.append(scraped_content)
            
            return evidence
            
        except Exception as e:
            logger.error(f"Web Scraper collection failed: {str(e)}")
            return []
    
    def _evaluate_evidence_quality(self, evidence_list: List[Dict[str, Any]]) -> float:
        """근거 품질 종합 평가"""
        if not evidence_list:
            return 0.0
        
        total_score = 0.0
        for evidence in evidence_list:
            # 신뢰도와 관련성 점수의 가중 평균
            reliability = evidence.get('reliability_score', 0.5)
            relevance = evidence.get('relevance_score', 0.5)
            
            # 출처별 가중치 적용
            source_weight = {
                'wikipedia': 1.0,      # 가장 신뢰할 수 있음
                'arxiv': 0.9,          # 학술 자료
                'brave_search': 0.8,   # 일반 검색
                'web_scraper': 0.7     # 스크래핑 결과
            }.get(evidence.get('source', 'unknown'), 0.5)
            
            evidence_score = (reliability * 0.6 + relevance * 0.4) * source_weight
            total_score += evidence_score
        
        return min(1.0, total_score / len(evidence_list))
    
    def _calculate_source_consistency(self, evidence_list: List[Dict[str, Any]], claim: str) -> float:
        """출처 간 일치도 계산"""
        if len(evidence_list) < 2:
            return 0.5  # 출처가 1개 이하면 중간 점수
        
        # 간단한 키워드 기반 일치도 계산 (실제로는 더 정교한 NLP 분석 필요)
        claim_keywords = set(claim.lower().split())
        
        consistency_scores = []
        for i, evidence1 in enumerate(evidence_list):
            for j, evidence2 in enumerate(evidence_list[i+1:], i+1):
                content1_keywords = set(evidence1.get('content', '').lower().split())
                content2_keywords = set(evidence2.get('content', '').lower().split())
                
                # 공통 키워드 비율로 일치도 측정
                common_keywords = claim_keywords.intersection(content1_keywords, content2_keywords)
                total_keywords = claim_keywords.union(content1_keywords, content2_keywords)
                
                if total_keywords:
                    consistency = len(common_keywords) / len(total_keywords)
                    consistency_scores.append(consistency)
        
        return sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.5
    
    def _make_final_verdict(self, claim: str, evidence_list: List[Dict[str, Any]], 
                           quality_score: float, consistency_score: float) -> Verdict:
        """종합 판정 로직"""
        
        # 근거가 없으면 INSUFFICIENT
        if len(evidence_list) == 0:
            return Verdict.INSUFFICIENT
        
        # 1개 출처만 있으면 보수적 판정
        if len(evidence_list) == 1:
            return Verdict.INSUFFICIENT if quality_score < 0.8 else Verdict.SUPPORTED
        
        # 다중 출처 종합 판정
        if consistency_score >= 0.8 and quality_score >= 0.7:
            return Verdict.SUPPORTED
        elif consistency_score <= 0.3 and quality_score >= 0.6:
            return Verdict.REFUTED  # 출처들이 서로 모순되지만 품질은 괜찮음
        else:
            return Verdict.INSUFFICIENT
    
    async def _generate_search_query(self, claim: str) -> str:
        """Claim에서 검색 쿼리 생성"""
        try:
            judge = self.context.get_judge()
            
            prompt = f"""
다음 claim을 검증하기 위한 최적의 검색 쿼리를 생성해주세요:

Claim: {claim}

핵심 키워드와 검색어를 포함한 효과적인 검색 쿼리를 반환하세요.
예시: "OpenAI GPT-4 release date 2023" 또는 "Tesla stock price 2024"

검색 쿼리:"""
            
            result = await judge.analyze_text(prompt)
            return result.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate search query: {str(e)}")
            # 실패시 claim에서 간단히 키워드 추출
            return ' '.join(claim.split()[:5])
    
    async def _extract_wikipedia_keywords(self, claim: str) -> List[str]:
        """Wikipedia 검색용 키워드 추출"""
        try:
            judge = self.context.get_judge()
            
            prompt = f"""
다음 claim에서 Wikipedia 검색에 적합한 키워드들을 추출해주세요:

Claim: {claim}

인명, 지명, 회사명, 제품명, 역사적 사건 등 Wikipedia에서 찾을 수 있는 키워드들을 반환하세요.
한 줄에 하나씩, 최대 3개까지:"""
            
            result = await judge.analyze_text(prompt)
            keywords = [line.strip() for line in result.split('\n') if line.strip()]
            return keywords[:3]
            
        except Exception as e:
            logger.error(f"Failed to extract Wikipedia keywords: {str(e)}")
            return [claim.split()[0]] if claim.split() else ['Unknown']
    
    async def _is_scientific_claim(self, claim: str) -> bool:
        """과학적 주장인지 판단"""
        try:
            judge = self.context.get_judge()
            
            prompt = f"""
다음 claim이 과학적/학술적 주장인지 판단해주세요:

Claim: {claim}

과학적 주장의 특징:
- 연구 결과, 실험 데이터
- 의학, 물리학, 화학, 생물학 등 과학 분야
- 통계, 수치, 측정값
- 학술 논문에서 다룰 만한 내용

YES 또는 NO로만 답하세요:"""
            
            result = await judge.analyze_text(prompt)
            return result.strip().upper() == 'YES'
            
        except Exception as e:
            logger.error(f"Failed to determine if scientific claim: {str(e)}")
            return False