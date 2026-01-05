import logging
import numpy as np
from typing import Dict, Any, Optional, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, ExampleInput, PromptType

logger = logging.getLogger(__name__)

class VarianceStage:
    """모델별 성능 편차 계산 단계 - 다중 모델 비교"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        # 비교할 모델들 정의 (각 계열의 확실한 Bedrock 지원 모델)
        self.comparison_models = {
            PromptType.TYPE_A: [
                "anthropic.claude-3-5-sonnet-20240620-v1:0",  # Claude 3.5 Sonnet
                "anthropic.claude-3-sonnet-20240229-v1:0",    # Claude 3 Sonnet
                "anthropic.claude-3-haiku-20240307-v1:0"      # Claude 3 Haiku
            ],
            PromptType.TYPE_B_TEXT: [
                "anthropic.claude-3-5-sonnet-20240620-v1:0",  # Claude 3.5 Sonnet
                "anthropic.claude-3-sonnet-20240229-v1:0",    # Claude 3 Sonnet
                "anthropic.claude-3-haiku-20240307-v1:0"      # Claude 3 Haiku
            ],
            PromptType.TYPE_B_IMAGE: [
                "amazon.nova-canvas-v1:0",                    # Nova Canvas
                "amazon.titan-image-generator-v1",            # Titan Image Generator v1
                "amazon.titan-image-generator-v2:0"           # Titan Image Generator v2
            ]
        }
    
    async def execute(
        self, 
        prompt: str, 
        example_inputs: List[ExampleInput], 
        prompt_type: PromptType,
        recommended_model: Optional[str] = None
    ) -> MetricScore:
        """
        모델별 성능 편차 계산
        - 3개 모델로 동일 입력 실행
        - 각 입력별로 3개 출력 생성 (총 9개)
        - 임베딩 기반 유사도 계산
        """
        logger.info(f"Calculating model variance score for {prompt_type}")
        
        try:
            models = self.comparison_models.get(prompt_type, [])
            if len(models) < 2:
                logger.warning(f"Not enough models for {prompt_type} comparison")
                return MetricScore(score=50.0, details={'error': 'insufficient_models'})
            
            runner = self.context.get_runner()
            embedder = self.context.get_embedder()
            
            all_variance_scores = []
            details = {'per_input_scores': [], 'models_used': models}
            
            # 각 예시 입력별로 처리
            for i, example_input in enumerate(example_inputs):
                logger.info(f"Processing input {i+1}/{len(example_inputs)} with {len(models)} models")
                
                # 프롬프트에 입력 삽입
                filled_prompt = self._fill_prompt(prompt, example_input.content)
                
                # 각 모델로 실행
                model_outputs = {}
                for model in models:
                    try:
                        result = await runner.invoke(
                            model=model,
                            prompt=filled_prompt,
                            input_type=example_input.input_type
                        )
                        model_outputs[model] = result['output']
                    except Exception as e:
                        logger.error(f"Failed to run {model}: {str(e)}")
                        model_outputs[model] = ""  # 실패시 빈 출력
                
                # 출력들을 임베딩으로 변환
                embeddings = {}
                for model, output in model_outputs.items():
                    if not output.strip():
                        embeddings[model] = None
                        continue
                    
                    try:
                        # 프롬프트 타입에 따라 적절한 임베딩 모델 선택
                        if prompt_type == PromptType.TYPE_B_IMAGE:
                            # 이미지 출력: Nova Multimodal 사용
                            embedding = await embedder.embed_multimodal(output)
                        else:
                            # 텍스트 출력: Titan Text 사용
                            embedding = await embedder.embed_text(output)
                        
                        embeddings[model] = embedding
                    except Exception as e:
                        logger.error(f"Failed to embed output from {model}: {str(e)}")
                        embeddings[model] = None
                
                # 유효한 임베딩만 필터링
                valid_embeddings = {k: v for k, v in embeddings.items() if v is not None}
                
                if len(valid_embeddings) < 2:
                    logger.warning(f"Not enough valid embeddings for input {i}")
                    all_variance_scores.append(0.0)
                    details['per_input_scores'].append({
                        'input_index': i,
                        'score': 0.0,
                        'reason': 'insufficient_valid_outputs',
                        'valid_models': list(valid_embeddings.keys())
                    })
                    continue
                
                # 모델 간 유사도 계산
                variance_score = self._calculate_model_variance(valid_embeddings)
                all_variance_scores.append(variance_score)
                
                details['per_input_scores'].append({
                    'input_index': i,
                    'score': variance_score,
                    'valid_models': list(valid_embeddings.keys()),
                    'model_outputs': model_outputs  # 전체 출력 저장 (자르지 않음)
                })
            
            # 전체 평균 점수 (100점 만점)
            final_score = (sum(all_variance_scores) / len(all_variance_scores) * 100) if all_variance_scores else 0.0
            
            details['final_score'] = final_score
            details['prompt_type'] = prompt_type.value
            details['note'] = 'Multi-model variance score out of 100. Higher score means more consistent across models.'
            
            logger.info(f"Model variance score: {final_score:.3f}")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Variance calculation failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    def _calculate_model_variance(self, embeddings: Dict[str, List[float]]) -> float:
        """모델 간 임베딩 유사도 기반 일관성 계산"""
        
        if len(embeddings) < 2:
            return 0.0
        
        # 모든 임베딩을 numpy 배열로 변환
        embedding_arrays = {}
        for model, embedding in embeddings.items():
            embedding_arrays[model] = np.array(embedding)
        
        # 모든 모델 쌍의 코사인 유사도 계산
        similarities = []
        models = list(embedding_arrays.keys())
        
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                model1, model2 = models[i], models[j]
                emb1, emb2 = embedding_arrays[model1], embedding_arrays[model2]
                
                # 코사인 유사도 계산
                similarity = self._cosine_similarity(emb1, emb2)
                similarities.append(similarity)
        
        # 평균 유사도 (높을수록 모델 간 일관성 높음)
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        
        # 0-1 범위를 0-1로 유지 (이미 코사인 유사도가 0-1 범위)
        return max(0.0, min(1.0, avg_similarity))
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """코사인 유사도 계산"""
        # 정규화
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)
        
        # 코사인 유사도
        similarity = np.dot(vec1_norm, vec2_norm)
        
        # 0-1 범위로 정규화 (cosine은 -1~1 범위)
        return (similarity + 1) / 2
    
    def _fill_prompt(self, prompt: str, input_content: str) -> str:
        """프롬프트에 입력 내용 삽입"""
        # 간단한 플레이스홀더 치환 (실제 구현에 맞게 수정 필요)
        return prompt.replace("{{input}}", input_content).replace("{{content}}", input_content)