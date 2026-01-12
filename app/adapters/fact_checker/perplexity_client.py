import asyncio
import logging
import httpx
from typing import Dict, Any, Optional, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class PerplexityClient:
    """Perplexity API 클라이언트 (다중 키 지원)"""
    
    def __init__(self):
        self.api_keys = settings.perplexity_api_keys
        self.model = settings.perplexity_model
        self.base_url = "https://api.perplexity.ai"
        self.current_key_index = 0
        
        if not self.api_keys:
            logger.warning("No Perplexity API keys found in settings")
        else:
            logger.info(f"Initialized with {len(self.api_keys)} Perplexity API keys")
    
    def _get_current_key(self) -> str:
        """현재 사용할 API 키 반환"""
        if not self.api_keys:
            return ""
        return self.api_keys[self.current_key_index]
    
    def _rotate_key(self):
        """다음 API 키로 전환"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"Rotated to API key {self.current_key_index + 1}/{len(self.api_keys)}")
    
    def _get_headers(self) -> Dict[str, str]:
        """현재 키로 헤더 생성"""
        return {
            "Authorization": f"Bearer {self._get_current_key()}",
            "Content-Type": "application/json"
        }
    
    async def verify_claim(self, claim: str) -> float:
        """
        단일 claim을 검증하고 0-100 점수 반환 (다중 키 지원)
        
        Args:
            claim: 검증할 주장/사실
            
        Returns:
            float: 0-100 점수 (100이 완전히 검증됨)
        """
        max_retries = 2
        base_delay = 2.0
        
        # 모든 키를 시도
        for key_attempt in range(len(self.api_keys) if self.api_keys else 1):
            for retry_attempt in range(max_retries):
                try:
                    # Perplexity에 팩트체킹 요청
                    prompt = self._create_fact_check_prompt(claim)
                    response = await self._call_api(prompt)
                    
                    # 응답에서 점수 추출
                    score = self._parse_verification_score(response, claim)
                    
                    logger.debug(f"Claim verification: '{claim[:50]}...' -> {score:.1f} (key {self.current_key_index + 1})")
                    return score
                    
                except Exception as e:
                    error_msg = str(e)
                    
                    # Rate limit 에러인 경우
                    if "429" in error_msg or "rate limit" in error_msg.lower():
                        if retry_attempt < max_retries - 1:
                            delay = base_delay * (2 ** retry_attempt)
                            logger.warning(f"Rate limit hit for claim '{claim[:30]}...', retrying in {delay}s (key {self.current_key_index + 1}, attempt {retry_attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # 재시도 횟수 초과, 다른 키로 전환
                            if key_attempt < len(self.api_keys) - 1:
                                logger.warning(f"Key {self.current_key_index + 1} exhausted, switching to next key")
                                self._rotate_key()
                                break
                    
                    logger.error(f"Perplexity verification failed for claim '{claim[:50]}...': {error_msg}")
                    if key_attempt == len(self.api_keys) - 1:  # 마지막 키인 경우
                        return 0.0
                    break
        
        logger.error(f"All API keys exhausted for claim '{claim[:50]}...'")
        return 0.0
    
    async def verify_claims_batch(self, claims: list[str]) -> list[float]:
        """
        여러 claim을 배치로 검증 (Rate limit 고려)
        
        Args:
            claims: 검증할 주장들의 리스트
            
        Returns:
            list[float]: 각 claim의 점수 리스트
        """
        logger.info(f"Batch verifying {len(claims)} claims with Perplexity")
        
        # Rate limit을 고려한 배치 처리
        batch_size = 5  # 5개씩 배치 처리 (10->5로 감소)
        delay_between_batches = 3.0  # 배치 간 지연 (2->3초로 증가)
        
        all_scores = []
        
        for i in range(0, len(claims), batch_size):
            batch_claims = claims[i:i + batch_size]
            logger.debug(f"Processing batch {i//batch_size + 1}/{(len(claims) + batch_size - 1)//batch_size}")
            
            # 배치 내 병렬 처리
            batch_scores = []
            batch_tasks = [self.verify_claim(claim) for claim in batch_claims]
            
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                for j, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"Claim {i+j+1} verification failed: {str(result)}")
                        batch_scores.append(0.0)
                    else:
                        batch_scores.append(result)
            except Exception as e:
                logger.error(f"Batch processing failed: {str(e)}")
                batch_scores = [0.0] * len(batch_claims)
            
            all_scores.extend(batch_scores)
            
            # 다음 배치 전 지연 (마지막 배치가 아닌 경우)
            if i + batch_size < len(claims):
                await asyncio.sleep(delay_between_batches)
        
        return all_scores
    
    def _create_fact_check_prompt(self, claim: str) -> str:
        """팩트체킹용 프롬프트 생성 - 구조화된 JSON 응답 요청"""
        return f"""Analyze the following claim and extract factual elements to verify against evidence.

Claim: "{claim}"

Instructions:
1. Extract key factual elements from the claim (subject, time, event, numbers, location, etc.)
2. Search for reliable sources to find evidence for each element
3. Compare each claim element with the evidence found
4. Return the result in JSON format ONLY (no other text)

JSON Format:
{{
  "verdict": "supported" | "partially_supported" | "refuted" | "no_evidence",
  "elements": [
    {{
      "type": "subject|time|event|number|location|other",
      "claim_value": "what the claim states",
      "evidence_value": "what the evidence shows (or null if not found)",
      "match": true | false | null
    }}
  ],
  "source_count": number,
  "sources": ["source1 title/url", "source2 title/url"]
}}

Rules:
- Extract at least 2-5 key elements from the claim
- "match": true if claim and evidence semantically agree
- "match": false if claim and evidence contradict
- "match": null if no evidence found for this element
- "verdict": "supported" if all elements match
- "verdict": "partially_supported" if some elements match
- "verdict": "refuted" if key elements contradict
- "verdict": "no_evidence" if no reliable sources found

IMPORTANT: Respond with ONLY the JSON object, no additional text."""
    
    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """Perplexity API 호출 (현재 키 사용)"""
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a fact-checking expert. Provide accurate verification scores based on reliable sources."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1,
            "top_p": 0.9,
            "return_citations": True,
            "search_domain_filter": ["perplexity.ai"],
            "return_images": False,
            "return_related_questions": False
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code != 200:
                raise Exception(f"Perplexity API error: {response.status_code} - {response.text}")
            
            return response.json()
    
    def _parse_verification_score(self, response: Dict[str, Any], claim: str) -> float:
        """API 응답에서 JSON 파싱 후 점수 계산"""
        try:
            import json
            import re
            
            # 응답에서 텍스트 추출
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                logger.warning(f"Empty response from Perplexity for claim: {claim[:50]}...")
                return 0.0
            
            # JSON 추출 (```json ... ``` 또는 순수 JSON)
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 순수 JSON 찾기
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    logger.warning(f"No JSON found in response for claim: {claim[:50]}...")
                    return self._fallback_score(content)
            
            # JSON 파싱
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error: {e}, falling back to text analysis")
                return self._fallback_score(content)
            
            # 점수 계산
            score = self._calculate_score_from_json(data, claim)
            return score
            
        except Exception as e:
            logger.error(f"Error parsing Perplexity response: {str(e)}")
            return 0.0
    
    def _calculate_score_from_json(self, data: Dict[str, Any], claim: str) -> float:
        """JSON 데이터에서 점수 계산 (공식 기반)"""
        try:
            elements = data.get("elements", [])
            verdict = data.get("verdict", "no_evidence")
            source_count = data.get("source_count", 0)
            
            if not elements:
                # 요소가 없으면 verdict 기반 점수
                verdict_scores = {
                    "supported": 90.0,
                    "partially_supported": 60.0,
                    "refuted": 20.0,
                    "no_evidence": 30.0
                }
                return verdict_scores.get(verdict, 50.0)
            
            # 요소별 점수 계산
            total_elements = len(elements)
            matched = 0
            contradicted = 0
            no_evidence = 0
            
            for elem in elements:
                match_status = elem.get("match")
                if match_status is True:
                    matched += 1
                elif match_status is False:
                    contradicted += 1
                else:  # None
                    no_evidence += 1
            
            # 기본 점수: 일치 비율 × 100
            if total_elements > 0:
                base_score = (matched / total_elements) * 100
            else:
                base_score = 50.0
            
            # 페널티: 모순된 요소가 있으면 감점
            contradiction_penalty = (contradicted / total_elements) * 30 if total_elements > 0 else 0
            
            # 보너스: 출처가 많으면 신뢰도 가산 (최대 10점)
            source_bonus = min(source_count * 2, 10)
            
            # 최종 점수
            final_score = base_score - contradiction_penalty + source_bonus
            
            # 0-100 범위로 제한
            final_score = max(0.0, min(100.0, final_score))
            
            logger.debug(f"Score calculation: matched={matched}/{total_elements}, "
                        f"contradicted={contradicted}, sources={source_count}, "
                        f"final={final_score:.1f}")
            
            return final_score
            
        except Exception as e:
            logger.error(f"Score calculation error: {str(e)}")
            return 50.0
    
    def _fallback_score(self, content: str) -> float:
        """JSON 파싱 실패 시 텍스트 기반 점수 추정"""
        import re
        
        content_lower = content.lower()
        
        # 숫자 점수 찾기
        score_match = re.search(r'score[:\s]*(\d+)', content_lower)
        if score_match:
            score = float(score_match.group(1))
            if 0 <= score <= 100:
                return score
        
        # 키워드 기반
        if any(word in content_lower for word in ['false', 'incorrect', 'wrong', 'refuted']):
            return 20.0
        elif any(word in content_lower for word in ['partially', 'mixed', 'some']):
            return 50.0
        elif any(word in content_lower for word in ['accurate', 'correct', 'true', 'supported']):
            return 80.0
        
        return 50.0
    
    async def health_check(self) -> bool:
        """Perplexity API 연결 상태 확인"""
        try:
            test_claim = "The sky is blue."
            score = await self.verify_claim(test_claim)
            return score > 0
        except Exception as e:
            logger.error(f"Perplexity health check failed: {str(e)}")
            return False