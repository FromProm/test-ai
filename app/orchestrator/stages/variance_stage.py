import logging
import asyncio
import numpy as np
from typing import Dict, Any, Optional, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, ExampleInput, PromptType
from app.core.config import settings

logger = logging.getLogger(__name__)

class VarianceStage:
    """모델별 성능 편차 계산 단계 - Run Stage에서 사전 계산된 결과 사용"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    def _get_comparison_models(self, selected_model: str) -> List[str]:
        """선택된 모델에 대한 비교 모델 목록 반환"""
        # config에서 모델 패밀리 매핑 가져오기
        comparison_models = settings.model_families.get(selected_model, [])
        
        if not comparison_models:
            logger.warning(f"No comparison models found for {selected_model}")
        
        return comparison_models
    
    def _get_model_short_name(self, model_id: str) -> str:
        """모델 ID를 짧은 이름으로 변환"""
        short_names = {
            "arn:aws:bedrock:us-east-1:261595668962:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude 4.5",
            "anthropic.claude-3-5-sonnet-20240620-v1:0": "Claude 3.5",
            "anthropic.claude-3-haiku-20240307-v1:0": "Claude Haiku",
            "openai.gpt-oss-120b-1:0": "GPT OSS 120B",
            "openai.gpt-oss-20b-1:0": "GPT OSS 20B",
            "google.gemma-3-27b-it-v1:0": "Gemma 27B",
            "google.gemma-3-12b-it-v1:0": "Gemma 12B",
            "google.gemma-3-4b-it-v1:0": "Gemma 4B",
            "amazon.titan-image-generator-v2:0": "Titan Image v2",
            "amazon.nova-canvas-v1:0": "Nova Canvas"
        }
        return short_names.get(model_id, model_id.split("/")[-1].split(":")[0])
    
    async def execute(
        self, 
        prompt: str, 
        example_inputs: List[ExampleInput], 
        prompt_type: PromptType,
        recommended_model: Optional[str] = None,
        existing_outputs: Optional[Dict[str, Any]] = None
    ) -> MetricScore:
        """
        모델별 성능 편차 계산 (Run Stage에서 이미 실행된 결과 사용)
        - Run Stage에서 받은 variance_outputs 사용
        - LLM 호출 없이 임베딩 + 계산만 수행
        """
        logger.info(f"Calculating model variance score for {prompt_type} (using pre-computed outputs)")
        
        try:
            # 선택된 모델에 대한 비교 모델 가져오기
            if not recommended_model:
                logger.warning("No recommended model specified")
                return MetricScore(score=50.0, details={'error': 'no_model_specified'})
            
            # RecommendedModel enum을 문자열로 변환
            if hasattr(recommended_model, 'value'):
                model_str = recommended_model.value
            else:
                model_str = recommended_model
            
            comparison_models = self._get_comparison_models(model_str)
            # 선택된 모델 + 비교 모델들
            all_models = [model_str] + comparison_models
            
            if len(all_models) < 2:
                logger.warning(f"Not enough models for comparison: {all_models}")
                return MetricScore(score=50.0, details={'error': 'insufficient_models'})
            
            logger.info(f"Comparing models: {all_models}")
            
            embedder = self.context.get_embedder()
            
            # existing_outputs에서 variance_outputs 추출
            if not existing_outputs or 'variance_outputs' not in existing_outputs:
                logger.warning("No variance outputs found from Run Stage")
                return MetricScore(score=50.0, details={'error': 'no_variance_outputs'})
            
            variance_outputs = existing_outputs['variance_outputs']
            details = {'per_input_scores': [], 'models_used': all_models, 'used_precomputed': True}
            
            # 결과를 입력별로 처리
            input_results = []
            for i, example_input in enumerate(example_inputs):
                logger.info(f"Processing results for input {i+1}/{len(example_inputs)}")
                
                # 모델별 출력 수집 (이미 Run Stage에서 실행됨)
                model_outputs = {}
                for model in all_models:
                    if model in variance_outputs and i < len(variance_outputs[model]):
                        model_outputs[model] = variance_outputs[model][i]
                    else:
                        logger.warning(f"Missing output for {model}, input {i+1}")
                        model_outputs[model] = ""
                
                # 임베딩 생성 (병렬)
                embedding_tasks = []
                valid_models = []
                for model, output in model_outputs.items():
                    if output.strip():
                        embedding_tasks.append(self._embed_single_output(embedder, output, prompt_type))
                        valid_models.append(model)
                
                embeddings = {}
                if embedding_tasks:
                    embedding_results = await asyncio.gather(*embedding_tasks, return_exceptions=True)
                    for model, result in zip(valid_models, embedding_results):
                        if isinstance(result, Exception):
                            logger.error(f"Failed to embed output from {model}: {str(result)}")
                            embeddings[model] = None
                        else:
                            embeddings[model] = result
                
                # 유효한 임베딩만 필터링
                valid_embeddings = {k: v for k, v in embeddings.items() if v is not None}
                
                if len(valid_embeddings) < 2:
                    logger.warning(f"Not enough valid embeddings for input {i}")
                    input_results.append({
                        'input_index': i,
                        'score': 0.0,
                        'reason': 'insufficient_valid_outputs',
                        'valid_models': list(valid_embeddings.keys()),
                        'model_outputs': {k: v[:100] + "..." if len(v) > 100 else v for k, v in model_outputs.items()}
                    })
                    continue
                
                # 선택된 모델과 각 비교 모델 간 쌍별 유사도 계산
                pairwise_scores = []
                model_names = list(valid_embeddings.keys())
                
                # 선택된 모델의 임베딩
                if recommended_model in valid_embeddings:
                    main_embedding = valid_embeddings[recommended_model]
                    
                    for comp_model in comparison_models:
                        if comp_model in valid_embeddings:
                            comp_embedding = valid_embeddings[comp_model]
                            similarity = self._cosine_similarity(main_embedding, comp_embedding)
                            pairwise_scores.append({
                                'model_pair': f"{self._get_model_short_name(recommended_model)} vs {self._get_model_short_name(comp_model)}",
                                'main_model': recommended_model,
                                'comparison_model': comp_model,
                                'similarity': similarity,
                                'score': similarity * 100
                            })
                
                # 전체 유사도도 계산 (기존 로직)
                all_similarities = []
                embedding_list = list(valid_embeddings.values())
                
                for i_emb in range(len(embedding_list)):
                    for j_emb in range(i_emb + 1, len(embedding_list)):
                        similarity = self._cosine_similarity(embedding_list[i_emb], embedding_list[j_emb])
                        all_similarities.append(similarity)
                
                if all_similarities:
                    avg_similarity = sum(all_similarities) / len(all_similarities)
                    variance_score = avg_similarity * 100
                else:
                    variance_score = 0.0
                
                input_results.append({
                    'input_index': i,
                    'score': variance_score,
                    'pairwise_scores': pairwise_scores,
                    'average_similarity': avg_similarity if all_similarities else 0.0,
                    'valid_models': model_names,
                    'model_outputs': {k: v[:100] + "..." if len(v) > 100 else v for k, v in model_outputs.items()}
                })
            
            # 전체 평균 점수 계산
            valid_scores = [result['score'] for result in input_results if result['score'] > 0]
            if valid_scores:
                final_score = sum(valid_scores) / len(valid_scores)
            else:
                final_score = 0.0
            
            # 쌍별 점수 집계
            pairwise_summary = {}
            for result in input_results:
                for pair_score in result.get('pairwise_scores', []):
                    pair_name = pair_score['model_pair']
                    if pair_name not in pairwise_summary:
                        pairwise_summary[pair_name] = []
                    pairwise_summary[pair_name].append(pair_score['score'])
            
            # 쌍별 평균 점수
            pairwise_averages = []
            for pair_name, scores in pairwise_summary.items():
                avg = sum(scores) / len(scores) if scores else 0.0
                pairwise_averages.append({
                    'model_pair': pair_name,
                    'average_score': round(avg, 1),
                    'sample_count': len(scores)
                })
            
            details['per_input_scores'] = input_results
            details['pairwise_comparison'] = pairwise_averages
            
            logger.info(f"Model variance score: {final_score:.3f}")
            logger.info(f"Pairwise scores: {pairwise_averages}")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Variance calculation failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    async def _embed_single_output(self, embedder, output: str, prompt_type: PromptType):
        """단일 출력에 대한 임베딩 생성"""
        try:
            if prompt_type == PromptType.TYPE_B_IMAGE:
                # 이미지 타입의 경우 텍스트 임베딩 사용
                return await embedder.embed_text(output)  # 단일 문자열 전달
            else:
                # 텍스트 타입
                return await embedder.embed_text(output)  # 단일 문자열 전달
        except Exception as e:
            logger.error(f"Embedding failed for output: {str(e)}")
            raise e
    
    def _cosine_similarity(self, vec1, vec2):
        """코사인 유사도 계산"""
        try:
            # 벡터가 리스트의 리스트 형태인 경우 첫 번째 요소 사용
            if isinstance(vec1, list) and len(vec1) > 0 and isinstance(vec1[0], list):
                vec1 = vec1[0]
            if isinstance(vec2, list) and len(vec2) > 0 and isinstance(vec2[0], list):
                vec2 = vec2[0]
            
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        except Exception as e:
            logger.error(f"Cosine similarity calculation failed: {str(e)}")
            return 0.0
    
    def _fill_prompt(self, prompt: str, input_content: str) -> str:
        """프롬프트의 {{변수명}} 플레이스홀더를 실제 입력으로 치환"""
        import json
        import re
        
        result = prompt
        has_placeholder = bool(re.search(r'\{\{.*?\}\}', prompt))
        
        # 1. input_content가 JSON인 경우 파싱해서 각 키별로 치환
        try:
            data = json.loads(input_content)
            if isinstance(data, dict):
                for key, value in data.items():
                    # {{key}} 형태를 value로 치환
                    result = result.replace(f"{{{{{key}}}}}", str(value))
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 2. 기본 플레이스홀더 치환 (JSON이 아닌 경우)
        result = result.replace("{{}}", input_content).replace("{{input}}", input_content)
        
        # 3. 플레이스홀더가 없었으면 맨 뒤에 입력 추가
        if not has_placeholder:
            result = f"{result}\n\n{input_content}"
        
        return result