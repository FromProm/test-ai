import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from collections import Counter
from app.core.config import settings

logger = logging.getLogger(__name__)

class MultiLLMVerifier:
    """다중 LLM 교차 검증 기반 사실 검증"""
    
    def __init__(self, context):
        self.context = context
        self.models = {
            'claude_sonnet_4_5': 'arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0',
            'gpt_oss_120b': 'openai.gpt-oss-120b-1:0',
            'claude_3_5_sonnet': 'anthropic.claude-3-5-sonnet-20240620-v1:0'  # Gemma 대신 Claude 3.5 Sonnet 사용
        }
        self.model_weights = {
            'claude_sonnet_4_5': 0.5,  # 가장 높은 가중치
            'gpt_oss_120b': 0.3,
            'claude_3_5_sonnet': 0.2
        }
    
    async def verify_claims_batch(self, claims: List[str]) -> List[float]:
        """
        여러 claim을 다중 LLM으로 교차 검증
        
        Args:
            claims: 검증할 주장들의 리스트
            
        Returns:
            list[float]: 각 claim의 점수 리스트 (0-100)
        """
        logger.info(f"Multi-LLM verifying {len(claims)} claims")
        
        if not claims:
            return []
        
        # 모든 claim에 대해 3개 모델로 병렬 검증
        all_results = []
        
        for claim in claims:
            try:
                # 3개 모델 병렬 검증
                verification_tasks = [
                    self._verify_with_model(claim, model_name, model_id)
                    for model_name, model_id in self.models.items()
                ]
                
                model_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
                
                # 예외 처리 및 결과 정리
                valid_results = []
                for i, result in enumerate(model_results):
                    model_name = list(self.models.keys())[i]
                    if isinstance(result, Exception):
                        logger.error(f"Model {model_name} failed for claim '{claim[:50]}...': {str(result)}")
                        # 실패한 모델은 중립 점수로 처리
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
                
                # 합의 알고리즘 적용
                consensus_score = self._calculate_consensus_score(valid_results)
                all_results.append(consensus_score)
                
                logger.debug(f"Claim: '{claim[:50]}...' -> Score: {consensus_score:.1f}")
                
            except Exception as e:
                logger.error(f"Failed to verify claim '{claim[:50]}...': {str(e)}")
                all_results.append(50.0)  # 실패 시 중립 점수
        
        logger.info(f"Multi-LLM verification completed. Average score: {sum(all_results)/len(all_results):.1f}")
        return all_results
    
    async def _verify_with_model(self, claim: str, model_name: str, model_id: str) -> Dict[str, Any]:
        """단일 모델로 claim 검증"""
        try:
            prompt = self._create_verification_prompt(claim)
            
            # 모델별 runner 가져오기
            runner = self.context.get_runner()
            
            # 결정적 출력을 위한 파라미터 설정
            model_params = {
                "temperature": 0.0,
                "max_tokens": 500
            }
            
            # 모델 실행
            response = await runner.invoke(
                model=model_id,
                prompt=prompt,
                input_type="text",
                **model_params
            )
            
            # 응답에서 텍스트 추출
            output_text = response.get('output', '')
            
            # JSON 응답 파싱
            result = self._parse_verification_response(output_text, claim, model_name)
            return result
            
        except Exception as e:
            logger.error(f"Model {model_name} verification failed: {str(e)}")
            raise
    
    def _create_verification_prompt(self, claim: str) -> str:
        """구조화된 검증 프롬프트 생성"""
        return f"""다음 주장을 검증하고 정확히 이 JSON 형식으로만 응답하세요:

주장: "{claim}"

{{
  "verdict": "SUPPORTED|REFUTED|INSUFFICIENT",
  "factual_elements": [
    {{
      "element": "구체적 사실 요소",
      "verification_status": "VERIFIED|CONTRADICTED|NOT_FOUND",
      "confidence": 0.0-1.0
    }}
  ],
  "overall_confidence": 0.0-1.0,
  "reasoning": "객관적 근거만 서술"
}}

검증 규칙:
1. 주장을 구체적 요소들로 분해하여 각각 검증
2. 내재된 지식만 사용 (웹 검색 금지)
3. 주관적 해석 금지, 객관적 사실만 확인
4. 확신할 수 없으면 INSUFFICIENT 선택
5. 각 요소별로 구체적 근거 제시

IMPORTANT: JSON 형식으로만 응답하세요."""
    
    def _parse_verification_response(self, response: str, claim: str, model_name: str) -> Dict[str, Any]:
        """모델 응답을 파싱하여 점수 계산"""
        try:
            # JSON 추출 - 여러 패턴 시도
            import re
            
            # 패턴 1: ```json ... ``` 형태
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if not json_match:
                # 패턴 2: { ... } 형태 (가장 큰 JSON 객체 찾기)
                json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
                if json_matches:
                    # 가장 긴 JSON 문자열 선택
                    json_str = max(json_matches, key=len)
                else:
                    logger.warning(f"No JSON found in {model_name} response for claim: {claim[:50]}...")
                    return self._fallback_result()
            else:
                json_str = json_match.group(1)
            
            # JSON 정리 (불완전한 JSON 수정 시도)
            json_str = json_str.strip()
            
            # 불완전한 JSON 수정
            if not json_str.endswith('}'):
                # 마지막 완전한 } 찾기
                last_brace = json_str.rfind('}')
                if last_brace > 0:
                    json_str = json_str[:last_brace + 1]
            
            data = json.loads(json_str)
            
            # 필수 필드 확인 및 기본값 설정
            verdict = data.get('verdict', 'INSUFFICIENT')
            if verdict not in ['SUPPORTED', 'REFUTED', 'INSUFFICIENT']:
                verdict = 'INSUFFICIENT'
                
            overall_confidence = data.get('overall_confidence', 0.5)
            if not isinstance(overall_confidence, (int, float)) or not (0 <= overall_confidence <= 1):
                overall_confidence = 0.5
                
            factual_elements = data.get('factual_elements', [])
            if not isinstance(factual_elements, list):
                factual_elements = []
            
            # 점수 계산
            score = self._calculate_score_from_elements(verdict, factual_elements, overall_confidence)
            
            return {
                'verdict': verdict,
                'confidence': overall_confidence,
                'score': score,
                'elements': factual_elements,
                'reasoning': data.get('reasoning', '')
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed for {model_name}: {str(e)}")
            # 간단한 텍스트 분석으로 폴백
            return self._analyze_text_response(response, claim, model_name)
        except Exception as e:
            logger.error(f"Response parsing failed for {model_name}: {str(e)}")
            return self._fallback_result()
    
    def _analyze_text_response(self, response: str, claim: str, model_name: str) -> Dict[str, Any]:
        """JSON 파싱 실패 시 텍스트 분석으로 폴백"""
        try:
            response_lower = response.lower()
            
            # 키워드 기반 판정
            if any(word in response_lower for word in ['supported', 'true', 'correct', 'accurate', 'verified']):
                verdict = 'SUPPORTED'
                confidence = 0.7
                score = 70.0
            elif any(word in response_lower for word in ['refuted', 'false', 'incorrect', 'wrong', 'contradicted']):
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
                'elements': [],
                'reasoning': f'Text analysis fallback: {response[:100]}...'
            }
            
        except Exception as e:
            logger.error(f"Text analysis fallback failed for {model_name}: {str(e)}")
            return self._fallback_result()
    
    def _calculate_score_from_elements(self, verdict: str, elements: List[Dict], confidence: float) -> float:
        """요소별 검증 결과로부터 점수 계산"""
        if not elements:
            # 요소가 없으면 전체 판정과 확신도로만 계산
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
        
        for element in elements:
            status = element.get('verification_status', 'NOT_FOUND')
            if status == 'VERIFIED':
                verified_count += 1
            elif status == 'CONTRADICTED':
                contradicted_count += 1
            else:
                not_found_count += 1
        
        total_elements = len(elements)
        if total_elements == 0:
            return 50.0
        
        # 기본 점수: 검증된 요소 비율
        base_score = (verified_count / total_elements) * 100
        
        # 모순 페널티
        contradiction_penalty = (contradicted_count / total_elements) * 50
        
        # 최종 점수 (0-100 범위)
        final_score = max(0, min(100, base_score - contradiction_penalty))
        
        # 전체 확신도 반영
        final_score = final_score * confidence
        
        return final_score
    
    def _fallback_result(self) -> Dict[str, Any]:
        """파싱 실패 시 기본 결과"""
        return {
            'verdict': 'INSUFFICIENT',
            'confidence': 0.5,
            'score': 50.0,
            'elements': [],
            'reasoning': 'Response parsing failed'
        }
    
    def _calculate_consensus_score(self, model_results: List[Dict[str, Any]]) -> float:
        """3개 모델 결과로부터 합의 점수 계산"""
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
        
        logger.debug(f"Consensus: {consensus_type} ({consensus_count}/3), "
                    f"Reliability: {reliability:.2f}, Score: {final_score:.1f}")
        
        return final_score