import logging
import re
import random
from collections import Counter
from typing import Dict, Any, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore
from app.core.config import settings

logger = logging.getLogger(__name__)

class DensityStage:
    """정보 밀도 계산 단계"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(self, execution_results: Dict[str, Any]) -> MetricScore:
        """
        정보 밀도 점수 계산
        - 각 입력별로 5개 출력 중 랜덤하게 3개씩 선택
        - 총 9개 출력의 n-gram 중복률 기반 계산
        - 최종 가중치: (0.5 * unique_1gram_ratio) + (0.5 * unique_2gram_ratio)
        """
        logger.info("Calculating information density score")
        
        try:
            executions = execution_results['executions']
            selected_outputs = []
            
            # 각 입력별로 5개 출력 중 랜덤하게 3개씩 선택
            for exec_data in executions:
                outputs = exec_data['outputs']
                
                # 유효한 출력만 필터링 (빈 출력 제외)
                valid_outputs = [output for output in outputs if output.strip()]
                
                if len(valid_outputs) < 3:
                    # 3개 미만이면 있는 것만 사용
                    selected = valid_outputs
                    logger.warning(f"Input {exec_data['input_index']}: Only {len(valid_outputs)} valid outputs available")
                else:
                    # 랜덤하게 3개 선택
                    selected = random.sample(valid_outputs, 3)
                
                selected_outputs.extend(selected)
            
            # 선택된 출력들의 정보 밀도 계산
            density_scores = []
            for output in selected_outputs:
                density_score = self._calculate_density(output)
                density_scores.append(density_score)
            
            # 전체 평균 밀도 (100점 만점으로 변환)
            final_score = (sum(density_scores) / len(density_scores) * 100) if density_scores else 0
            
            details = {
                'selected_outputs_count': len(selected_outputs),
                'per_output_density': [score * 100 for score in density_scores],  # 100점 만점으로 표시
                'average_density': final_score,
                'unigram_weight': settings.density_weights['unigram'],
                'bigram_weight': settings.density_weights['bigram'],
                'note': 'Using 3 random outputs from each input (total 9 outputs), score out of 100'
            }
            
            logger.info(f"Information density score: {final_score:.3f}")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Density calculation failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    def _calculate_density(self, text: str) -> float:
        """단일 텍스트의 정보 밀도 계산"""
        # 텍스트 전처리
        cleaned_text = self._preprocess_text(text)
        words = cleaned_text.split()
        
        if len(words) < 2:
            return 0.0
        
        # 1-gram 밀도
        unigram_density = self._calculate_ngram_density(words, 1)
        
        # 2-gram 밀도
        bigram_density = self._calculate_ngram_density(words, 2)
        
        # 가중 평균
        final_density = (
            settings.density_weights['unigram'] * unigram_density +
            settings.density_weights['bigram'] * bigram_density
        )
        
        return final_density
    
    def _calculate_ngram_density(self, words: List[str], n: int) -> float:
        """n-gram 밀도 계산"""
        if len(words) < n:
            return 0.0
        
        # n-gram 생성
        ngrams = []
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i+n])
            ngrams.append(ngram)
        
        if not ngrams:
            return 0.0
        
        # 고유 n-gram 비율
        unique_ngrams = len(set(ngrams))
        total_ngrams = len(ngrams)
        
        return unique_ngrams / total_ngrams
    
    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리"""
        # 소문자 변환 (문장 시작 대문자, 일반적 중복 감지를 위해)
        text = text.lower()
        
        # 특수문자 제거 (단어 경계는 유지)
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # 연속된 공백 제거
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()