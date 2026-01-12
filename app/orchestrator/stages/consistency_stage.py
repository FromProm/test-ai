import logging
import numpy as np
from typing import Dict, Any, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore
from app.core.config import settings

logger = logging.getLogger(__name__)

class ConsistencyStage:
    """일관성 계산 단계 - Centroid 방식"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(self, output_embeddings: List[Dict[str, Any]]) -> MetricScore:
        """
        출력 일관성 점수 계산
        - Centroid 기반 거리 계산
        - 앙상블 평균 (Titan + Cohere)
        """
        logger.info("Calculating consistency score using centroid method")
        
        try:
            all_consistency_scores = []
            details = {'per_input_scores': [], 'ensemble_details': []}
            
            for output_group in output_embeddings:
                input_index = output_group['input_index']
                embeddings = output_group['embeddings']
                
                # 유효한 임베딩만 필터링 (빈 출력 제외)
                valid_embeddings = []
                for emb in embeddings:
                    # 이미지 타입이면 nova_embedding, 텍스트 타입이면 titan_embedding 확인
                    if 'nova_embedding' in emb and emb['nova_embedding'] is not None:
                        valid_embeddings.append(emb)
                    elif 'titan_embedding' in emb and emb['titan_embedding'] is not None:
                        valid_embeddings.append(emb)
                
                if len(valid_embeddings) < 3:
                    # 3개 미만이면 centroid 방식 사용 불가
                    logger.warning(f"Input {input_index}: Not enough valid outputs for centroid ({len(valid_embeddings)})")
                    all_consistency_scores.append(0.0)
                    details['per_input_scores'].append({
                        'input_index': input_index,
                        'score': 0.0,
                        'valid_outputs': len(valid_embeddings),
                        'reason': 'insufficient_outputs'
                    })
                    continue
                
                # Nova/Titan과 Cohere 각각 계산
                # 첫 번째 모델 (Nova 또는 Titan)
                first_embeddings = []
                for emb in valid_embeddings:
                    if 'nova_embedding' in emb and emb['nova_embedding'] is not None:
                        first_embeddings.append(emb['nova_embedding'])
                    elif 'titan_embedding' in emb and emb['titan_embedding'] is not None:
                        first_embeddings.append(emb['titan_embedding'])
                
                # Cohere 임베딩 필터링 (None 제외)
                cohere_embeddings = [emb['cohere_embedding'] for emb in valid_embeddings 
                                     if emb.get('cohere_embedding') is not None]
                
                # 첫 번째 모델 점수 계산
                first_score = 0.0
                if len(first_embeddings) >= 2:
                    first_score = self._calculate_centroid_consistency(first_embeddings)
                
                # Cohere 점수 계산
                cohere_score = 0.0
                if len(cohere_embeddings) >= 2:
                    cohere_score = self._calculate_centroid_consistency(cohere_embeddings)
                
                # 앙상블 평균 (유효한 점수만)
                valid_scores = [s for s in [first_score, cohere_score] if s > 0]
                ensemble_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
                all_consistency_scores.append(ensemble_score)
                
                details['per_input_scores'].append({
                    'input_index': input_index,
                    'score': ensemble_score,
                    'first_model_score': first_score,  # Nova 또는 Titan
                    'cohere_score': cohere_score,
                    'valid_outputs': len(valid_embeddings)
                })
            
            # 전체 평균 (100점 만점)
            final_score = sum(all_consistency_scores) / len(all_consistency_scores) if all_consistency_scores else 0
            
            details['final_score'] = final_score
            details['alpha'] = settings.alpha
            details['note'] = 'Consistency score out of 100, negative scores clipped to 0. Using Nova Multimodal for images, Titan Text for text.'
            
            logger.info(f"Consistency score: {final_score:.3f}")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Consistency calculation failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    def _calculate_centroid_consistency(self, embeddings: List[List[float]]) -> float:
        """단일 모델의 centroid 기반 일관성 계산"""
        embeddings = np.array(embeddings)  # (N, D)
        
        # 1. 중심 벡터 계산
        centroid = np.mean(embeddings, axis=0)
        
        # 2. 정규화
        centroid_norm = centroid / np.linalg.norm(centroid)
        emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # 3. 중심으로부터의 cosine distance 계산
        distances = 1 - np.dot(emb_norm, centroid_norm)
        
        # 4. 평균 거리와 최대 거리
        mean_d = np.mean(distances)
        max_d = np.max(distances)
        
        # 5. 일관성 점수 (alpha로 최대 거리 패널티) - 음수 방지 및 100점 만점 변환
        consistency = 1 - (mean_d + settings.alpha * max_d)
        
        # 0-1 범위로 클리핑 후 100점 만점으로 변환
        consistency_score = max(0.0, min(1.0, consistency)) * 100
        
        return consistency_score