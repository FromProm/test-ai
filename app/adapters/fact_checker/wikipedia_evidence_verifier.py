import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)

class WikipediaEvidenceVerifier:
    """Wikipedia 근거 기반 다중 LLM 교차 검증"""
    
    def __init__(self, context):
        self.context = context
        self.models = {
            'claude_sonnet_4_5': 'arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0',
            'gpt_oss_120b': 'openai.gpt-oss-120b-1:0',
            'claude_3_5_sonnet': 'anthropic.claude-3-5-sonnet-20240620-v1:0'
        }
        self.model_weights = {
            'claude_sonnet_4_5': 0.5,
            'gpt_oss_120b': 0.3,
            'claude_3_5_sonnet': 0.2
        }
    
    async def verify_claims_batch(self, claims: List[str]) -> List[float]:
        """
        Wikipedia 근거 기반 다중 LLM 교차 검증 (병렬 처리)
        
        Args:
            claims: 검증할 주장들의 리스트
            
        Returns:
            list[float]: 각 claim의 점수 리스트 (0-100)
        """
        logger.info(f"Wikipedia evidence-based verifying {len(claims)} claims (parallel)")
        
        if not claims:
            return []
        
        # 모든 claim을 병렬로 처리
        verification_tasks = [
            self._verify_single_claim(claim)
            for claim in claims
        ]
        
        results = await asyncio.gather(*verification_tasks, return_exceptions=True)
        
        # 결과 정리
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to verify claim '{claims[i][:50]}...': {str(result)}")
                all_results.append(50.0)  # 실패 시 중립 점수
            else:
                all_results.append(result)
        
        logger.info(f"Wikipedia evidence-based verification completed. Average score: {sum(all_results)/len(all_results):.1f}")
        return all_results
    
    async def _verify_single_claim(self, claim: str) -> float:
        """단일 claim 검증 (Wikipedia 근거 수집 + 다중 LLM 검증)"""
        try:
            # 1단계: Wikipedia에서 관련 근거 수집
            evidence_pool = await self._collect_wikipedia_evidence(claim)
            
            if not evidence_pool:
                logger.warning(f"No Wikipedia evidence found for claim: {claim[:50]}...")
                # Wikipedia 근거가 없으면 기존 LLM 내재 지식으로 폴백
                return await self._fallback_llm_verification(claim)
            
            # 2단계: 근거 기반 다중 LLM 검증 (병렬)
            verification_tasks = [
                self._verify_claim_with_evidence(claim, evidence_pool, model_name, model_id)
                for model_name, model_id in self.models.items()
            ]
            
            model_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
            
            # 예외 처리 및 결과 정리
            valid_results = []
            for i, result in enumerate(model_results):
                model_name = list(self.models.keys())[i]
                if isinstance(result, Exception):
                    logger.error(f"Model {model_name} failed for claim '{claim[:50]}...': {str(result)}")
                    valid_results.append({
                        'model': model_name,
                        'verdict': 'INSUFFICIENT',
                        'confidence': 0.5,
                        'score': 50.0
                    })
                else:
                    valid_results.append({
                        'model': model_name,
                        **result
                    })
            
            # 3단계: 근거 기반 합의 알고리즘
            consensus_score = self._calculate_evidence_based_consensus(valid_results, evidence_pool)
            
            logger.debug(f"Claim: '{claim[:50]}...' -> Score: {consensus_score:.1f}")
            return consensus_score
            
        except Exception as e:
            logger.error(f"Failed to verify claim '{claim[:50]}...': {str(e)}")
            return 50.0  # 실패 시 중립 점수
    
    async def _collect_wikipedia_evidence(self, claim: str) -> List[Dict[str, Any]]:
        """Wikipedia에서 claim 관련 근거 수집 (병렬화)"""
        try:
            # Claim에서 키워드 추출
            keywords = self._extract_keywords(claim)
            
            if not keywords:
                return []
            
            # Wikipedia 검색
            from app.adapters.fact_checker.wikipedia_mcp import WikipediaMCP
            wiki_mcp = WikipediaMCP()
            
            evidence_pool = []
            
            # 1. 모든 검색을 병렬로 실행 (전체 키워드 + 개별 키워드)
            main_keywords = keywords[:2]
            search_tasks = [
                wiki_mcp.search_wikipedia(query=" ".join(keywords), limit=5)
            ] + [
                wiki_mcp.search_wikipedia(query=keyword, limit=2)
                for keyword in main_keywords
            ]
            
            search_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # 검색 결과에서 고유한 문서 제목 수집
            all_titles = set()
            title_to_keywords = {}  # 제목 -> 관련 키워드 매핑
            
            for i, search_results in enumerate(search_results_list):
                if isinstance(search_results, Exception):
                    logger.warning(f"Search task {i} failed: {str(search_results)}")
                    continue
                
                related_keywords = keywords if i == 0 else [main_keywords[i-1]]
                
                for result in search_results.get('results', []):
                    title = result['title']
                    if title not in all_titles:
                        all_titles.add(title)
                        title_to_keywords[title] = {
                            'keywords': related_keywords,
                            'timestamp': result.get('timestamp', '')
                        }
            
            # 2. 모든 문서를 병렬로 가져오기
            article_tasks = [
                wiki_mcp.get_article(title=title)
                for title in all_titles
            ]
            
            articles = await asyncio.gather(*article_tasks, return_exceptions=True)
            
            # 3. 결과 처리
            for title, article in zip(all_titles, articles):
                if isinstance(article, Exception):
                    logger.warning(f"Failed to get article {title}: {str(article)}")
                    continue
                
                if article and 'text' in article:
                    info = title_to_keywords[title]
                    relevant_sections = self._extract_relevant_sections(
                        article['text'], claim, info['keywords']
                    )
                    
                    for section in relevant_sections:
                        evidence_pool.append({
                            'source': title,
                            'content': section,
                            'relevance_score': self._calculate_relevance(section, info['keywords']),
                            'timestamp': info['timestamp']
                        })
            
            # 관련성 점수로 정렬하고 상위 10개만 선택
            evidence_pool.sort(key=lambda x: x['relevance_score'], reverse=True)
            evidence_pool = evidence_pool[:10]
            
            logger.info(f"Collected {len(evidence_pool)} evidence pieces for claim: {claim[:50]}...")
            return evidence_pool
            
        except Exception as e:
            logger.error(f"Failed to collect Wikipedia evidence: {str(e)}")
            return []
    
    def _extract_keywords(self, claim: str) -> List[str]:
        """Claim에서 검색용 키워드 추출"""
        # 간단한 키워드 추출 (향후 NLP 라이브러리로 개선 가능)
        import re
        
        # 특수 문자 제거 및 단어 분리
        words = re.findall(r'\b\w+\b', claim.lower())
        
        # 불용어 제거
        stop_words = {'은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로', 
                     'the', 'is', 'are', 'was', 'were', 'a', 'an', 'and', 'or', 'but'}
        
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        # 숫자와 연도 우선 처리
        priority_keywords = []
        regular_keywords = []
        
        for word in keywords:
            if re.match(r'\d{4}', word) or re.match(r'\d+', word):  # 연도나 숫자
                priority_keywords.append(word)
            else:
                regular_keywords.append(word)
        
        # 우선순위 키워드 + 일반 키워드 (최대 8개)
        final_keywords = priority_keywords + regular_keywords[:8-len(priority_keywords)]
        
        return final_keywords[:8]
    
    def _extract_relevant_sections(self, article_text: str, claim: str, keywords: List[str]) -> List[str]:
        """문서에서 claim과 관련된 섹션 추출"""
        sections = []
        
        # 문단별로 분리
        paragraphs = article_text.split('\n\n')
        
        for paragraph in paragraphs:
            if len(paragraph.strip()) < 50:  # 너무 짧은 문단 제외
                continue
            
            # 키워드 포함 여부 확인
            paragraph_lower = paragraph.lower()
            keyword_count = sum(1 for keyword in keywords if keyword.lower() in paragraph_lower)
            
            if keyword_count >= 1:  # 최소 1개 키워드 포함
                # 문단을 문장 단위로 분리하여 관련성 높은 부분만 추출
                sentences = re.split(r'[.!?]+', paragraph)
                relevant_sentences = []
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 20:
                        sentence_lower = sentence.lower()
                        sentence_keyword_count = sum(1 for keyword in keywords if keyword.lower() in sentence_lower)
                        
                        if sentence_keyword_count >= 1:
                            relevant_sentences.append(sentence)
                
                if relevant_sentences:
                    sections.append('. '.join(relevant_sentences[:3]))  # 최대 3문장
        
        return sections[:5]  # 최대 5개 섹션
    
    def _calculate_relevance(self, text: str, keywords: List[str]) -> float:
        """텍스트와 키워드의 관련성 점수 계산"""
        text_lower = text.lower()
        
        # 키워드 매칭 점수
        keyword_score = sum(1 for keyword in keywords if keyword.lower() in text_lower)
        keyword_score = keyword_score / len(keywords) if keywords else 0
        
        # 텍스트 길이 점수 (너무 짧거나 길면 감점)
        length_score = 1.0
        if len(text) < 100:
            length_score = 0.7
        elif len(text) > 1000:
            length_score = 0.8
        
        # 숫자/날짜 포함 보너스
        number_bonus = 0.2 if re.search(r'\d+', text) else 0
        
        return min(1.0, keyword_score * length_score + number_bonus)
    
    async def _verify_claim_with_evidence(self, claim: str, evidence_pool: List[Dict], model_name: str, model_id: str) -> Dict[str, Any]:
        """근거를 바탕으로 단일 모델이 claim 검증"""
        try:
            prompt = self._create_evidence_based_prompt(claim, evidence_pool)
            
            runner = self.context.get_runner()
            
            # 결정적 출력을 위한 파라미터 설정
            model_params = {
                "temperature": 0.0,
                "max_tokens": 800
            }
            
            response = await runner.invoke(
                model=model_id,
                prompt=prompt,
                input_type="text",
                **model_params
            )
            
            output_text = response.get('output', '')
            result = self._parse_evidence_verification_response(output_text, claim, model_name)
            return result
            
        except Exception as e:
            logger.error(f"Model {model_name} evidence verification failed: {str(e)}")
            raise
    
    def _create_evidence_based_prompt(self, claim: str, evidence_pool: List[Dict]) -> str:
        """근거 기반 검증 프롬프트 생성"""
        
        # 근거들을 텍스트로 정리
        evidence_text = ""
        for i, evidence in enumerate(evidence_pool, 1):
            evidence_text += f"\n근거 {i} (출처: {evidence['source']}):\n{evidence['content']}\n"
        
        return f"""다음 주장을 제공된 Wikipedia 근거를 바탕으로 검증하세요:

주장: "{claim}"

Wikipedia 근거:{evidence_text}

검증 방법:
1. 주장의 각 요소를 근거와 정확히 대조하세요
2. 근거에서 직접 확인할 수 있는 사실만 VERIFIED로 판정
3. 근거와 모순되는 내용은 CONTRADICTED로 판정  
4. 근거에서 찾을 수 없는 내용은 NOT_FOUND로 판정
5. 반드시 제공된 근거만을 사용하여 판단하세요

JSON 형식으로만 응답:
{{
  "verdict": "SUPPORTED|REFUTED|INSUFFICIENT",
  "evidence_analysis": [
    {{
      "claim_element": "구체적 주장 요소",
      "supporting_evidence": "해당 근거 인용 (출처 포함)",
      "verification_status": "VERIFIED|CONTRADICTED|NOT_FOUND",
      "confidence": 0.0-1.0
    }}
  ],
  "overall_confidence": 0.0-1.0,
  "reasoning": "근거 기반 판단 과정 설명"
}}

중요: 
- 반드시 제공된 Wikipedia 근거만을 사용하여 판단하세요
- 자신의 지식이 아닌 근거에 기반한 객관적 판정을 하세요
- JSON 형식으로만 응답하세요"""
    
    def _parse_evidence_verification_response(self, response: str, claim: str, model_name: str) -> Dict[str, Any]:
        """근거 기반 검증 응답 파싱"""
        try:
            # JSON 추출 - 여러 패턴 시도
            import re
            
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if not json_match:
                json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
                if json_matches:
                    json_str = max(json_matches, key=len)
                else:
                    logger.warning(f"No JSON found in {model_name} response for claim: {claim[:50]}...")
                    return self._fallback_result()
            else:
                json_str = json_match.group(1)
            
            # JSON 정리
            json_str = json_str.strip()
            if not json_str.endswith('}'):
                last_brace = json_str.rfind('}')
                if last_brace > 0:
                    json_str = json_str[:last_brace + 1]
            
            data = json.loads(json_str)
            
            # 필수 필드 확인
            verdict = data.get('verdict', 'INSUFFICIENT')
            if verdict not in ['SUPPORTED', 'REFUTED', 'INSUFFICIENT']:
                verdict = 'INSUFFICIENT'
                
            overall_confidence = data.get('overall_confidence', 0.5)
            if not isinstance(overall_confidence, (int, float)) or not (0 <= overall_confidence <= 1):
                overall_confidence = 0.5
                
            evidence_analysis = data.get('evidence_analysis', [])
            if not isinstance(evidence_analysis, list):
                evidence_analysis = []
            
            # 점수 계산
            score = self._calculate_evidence_based_score(verdict, evidence_analysis, overall_confidence)
            
            return {
                'verdict': verdict,
                'confidence': overall_confidence,
                'score': score,
                'evidence_analysis': evidence_analysis,
                'reasoning': data.get('reasoning', '')
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed for {model_name}: {str(e)}")
            return self._analyze_text_response(response, claim, model_name)
        except Exception as e:
            logger.error(f"Response parsing failed for {model_name}: {str(e)}")
            return self._fallback_result()
    
    def _calculate_evidence_based_score(self, verdict: str, evidence_analysis: List[Dict], confidence: float) -> float:
        """근거 기반 점수 계산"""
        if not evidence_analysis:
            # 분석이 없으면 전체 판정과 확신도로만 계산
            if verdict == 'SUPPORTED':
                return confidence * 100
            elif verdict == 'REFUTED':
                return (1 - confidence) * 100
            else:  # INSUFFICIENT
                return 50.0
        
        # 요소별 점수 계산
        verified_count = 0
        contradicted_count = 0
        not_found_count = 0
        
        for element in evidence_analysis:
            status = element.get('verification_status', 'NOT_FOUND')
            if status == 'VERIFIED':
                verified_count += 1
            elif status == 'CONTRADICTED':
                contradicted_count += 1
            else:
                not_found_count += 1
        
        total_elements = len(evidence_analysis)
        if total_elements == 0:
            return 50.0
        
        # 기본 점수: 검증된 요소 비율
        base_score = (verified_count / total_elements) * 100
        
        # 모순 페널티 (더 강하게)
        contradiction_penalty = (contradicted_count / total_elements) * 60
        
        # 근거 부족 페널티
        no_evidence_penalty = (not_found_count / total_elements) * 30
        
        # 최종 점수
        final_score = max(0, min(100, base_score - contradiction_penalty - no_evidence_penalty))
        
        # 전체 확신도 반영
        final_score = final_score * confidence
        
        return final_score
    
    def _calculate_evidence_based_consensus(self, model_results: List[Dict[str, Any]], evidence_pool: List[Dict]) -> float:
        """근거 기반 합의 점수 계산"""
        if not model_results:
            return 50.0
        
        verdicts = [result['verdict'] for result in model_results]
        scores = [result['score'] for result in model_results]
        confidences = [result['confidence'] for result in model_results]
        
        # 판정 합의도 계산
        verdict_counts = Counter(verdicts)
        most_common_verdict = verdict_counts.most_common(1)[0]
        consensus_count = most_common_verdict[1]
        
        if consensus_count == 3:
            # 완전 합의 (3/3)
            reliability = 1.0
            consensus_type = 'unanimous'
        elif consensus_count == 2:
            # 다수 합의 (2/3)
            reliability = 0.8
            consensus_type = 'majority'
        else:
            # 합의 실패 (1/1/1)
            reliability = 0.3
            consensus_type = 'no_consensus'
        
        # 근거 품질 보너스
        evidence_quality_bonus = min(len(evidence_pool) * 0.05, 0.2)  # 최대 20% 보너스
        reliability = min(1.0, reliability + evidence_quality_bonus)
        
        # 가중 평균 점수 계산
        weighted_score = 0.0
        total_weight = 0.0
        
        for i, result in enumerate(model_results):
            model_name = result['model']
            weight = self.model_weights.get(model_name, 0.33)
            
            # 합의에 참여한 모델에 추가 가중치
            if result['verdict'] == most_common_verdict[0]:
                weight *= 1.2
            
            weighted_score += result['score'] * weight
            total_weight += weight
        
        if total_weight > 0:
            final_score = weighted_score / total_weight
        else:
            final_score = sum(scores) / len(scores)
        
        # 신뢰도 반영
        final_score = final_score * reliability + (1 - reliability) * 50.0
        
        logger.debug(f"Evidence-based consensus: {consensus_type} ({consensus_count}/3), "
                    f"Reliability: {reliability:.2f}, Evidence: {len(evidence_pool)}, Score: {final_score:.1f}")
        
        return final_score
    
    async def _fallback_llm_verification(self, claim: str) -> float:
        """Wikipedia 근거가 없을 때 다중 LLM 내재 지식으로 폴백"""
        try:
            logger.info(f"Fallback to multi-LLM verification for claim: {claim[:50]}...")
            
            # 다중 LLM 병렬 검증
            verification_tasks = [
                self._fallback_verify_with_model(claim, model_name, model_id)
                for model_name, model_id in self.models.items()
            ]
            
            model_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
            
            # 결과 정리
            valid_results = []
            for i, result in enumerate(model_results):
                model_name = list(self.models.keys())[i]
                if isinstance(result, Exception):
                    logger.error(f"Fallback model {model_name} failed: {str(result)}")
                    valid_results.append({
                        'model': model_name,
                        'verdict': 'INSUFFICIENT',
                        'confidence': 0.5,
                        'score': 50.0
                    })
                else:
                    valid_results.append({
                        'model': model_name,
                        **result
                    })
            
            # 합의 알고리즘 적용 (근거 없이)
            consensus_score = self._calculate_evidence_based_consensus(valid_results, [])
            
            logger.info(f"Fallback multi-LLM consensus score: {consensus_score:.1f}")
            return consensus_score
            
        except Exception as e:
            logger.error(f"Fallback LLM verification failed: {str(e)}")
            return 50.0
    
    async def _fallback_verify_with_model(self, claim: str, model_name: str, model_id: str) -> Dict[str, Any]:
        """폴백: 단일 모델이 내재 지식으로 claim 검증"""
        try:
            prompt = f"""다음 주장을 당신이 알고 있는 지식을 바탕으로 검증하세요:

주장: "{claim}"

JSON 형식으로만 응답:
{{
  "verdict": "SUPPORTED|REFUTED|INSUFFICIENT",
  "confidence": 0.0-1.0,
  "reasoning": "판단 근거 설명"
}}

중요:
- 확실히 아는 사실만 SUPPORTED/REFUTED로 판정
- 불확실하면 INSUFFICIENT 선택
- JSON 형식으로만 응답"""
            
            runner = self.context.get_runner()
            
            response = await runner.invoke(
                model=model_id,
                prompt=prompt,
                input_type="text",
                temperature=0.0,
                max_tokens=300
            )
            
            output_text = response.get('output', '')
            
            # JSON 파싱
            json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    verdict = data.get('verdict', 'INSUFFICIENT')
                    confidence = data.get('confidence', 0.5)
                    
                    if verdict == 'SUPPORTED':
                        score = confidence * 100
                    elif verdict == 'REFUTED':
                        score = (1 - confidence) * 100
                    else:
                        score = 50.0
                    
                    return {
                        'verdict': verdict,
                        'confidence': confidence,
                        'score': score,
                        'evidence_analysis': [],
                        'reasoning': data.get('reasoning', '')
                    }
                except json.JSONDecodeError:
                    pass
            
            return self._fallback_result()
            
        except Exception as e:
            logger.error(f"Fallback model {model_name} failed: {str(e)}")
            raise
    
    def _analyze_text_response(self, response: str, claim: str, model_name: str) -> Dict[str, Any]:
        """JSON 파싱 실패 시 텍스트 분석으로 폴백"""
        try:
            response_lower = response.lower()
            
            if any(word in response_lower for word in ['supported', 'verified', 'confirmed', 'true', 'correct']):
                verdict = 'SUPPORTED'
                confidence = 0.7
                score = 70.0
            elif any(word in response_lower for word in ['refuted', 'contradicted', 'false', 'incorrect', 'wrong']):
                verdict = 'REFUTED'
                confidence = 0.7
                score = 30.0
            else:
                verdict = 'INSUFFICIENT'
                confidence = 0.5
                score = 50.0
            
            logger.info(f"Text analysis fallback for {model_name}: {verdict} ({score:.1f})")
            
            return {
                'verdict': verdict,
                'confidence': confidence,
                'score': score,
                'evidence_analysis': [],
                'reasoning': f'Text analysis fallback: {response[:100]}...'
            }
            
        except Exception as e:
            logger.error(f"Text analysis fallback failed for {model_name}: {str(e)}")
            return self._fallback_result()
    
    def _fallback_result(self) -> Dict[str, Any]:
        """파싱 실패 시 기본 결과"""
        return {
            'verdict': 'INSUFFICIENT',
            'confidence': 0.5,
            'score': 50.0,
            'evidence_analysis': [],
            'reasoning': 'Response parsing failed'
        }