import logging
import asyncio
from typing import Dict, Any, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import ExampleInput, PromptType

logger = logging.getLogger(__name__)

class EmbedStage:
    """임베딩 생성 단계"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(
        self, 
        execution_results: Dict[str, Any], 
        example_inputs: List[ExampleInput],
        prompt_type: PromptType
    ) -> Dict[str, Any]:
        """
        임베딩 생성
        - 입력과 출력을 각각 임베딩
        - 텍스트/이미지 타입에 따라 적절한 모델 선택
        """
        logger.info("Generating embeddings for inputs and outputs")
        
        try:
            embedder = self.context.get_embedder()
            executions = execution_results['executions']
            
            # 입력 임베딩 생성
            input_embeddings = await self._embed_inputs(embedder, example_inputs)
            
            # 출력 임베딩 생성
            output_embeddings = await self._embed_outputs(embedder, executions, prompt_type)
            
            return {
                'inputs': input_embeddings,
                'outputs': output_embeddings
            }
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise
    
    async def _embed_inputs(self, embedder, example_inputs: List[ExampleInput]) -> List[Dict[str, Any]]:
        """입력 임베딩 생성 - 배치 처리"""
        logger.info(f"Embedding {len(example_inputs)} inputs using batch processing")
        
        # 텍스트와 이미지 입력 분리
        text_inputs = []
        image_inputs = []
        text_indices = []
        image_indices = []
        
        for i, example_input in enumerate(example_inputs):
            if example_input.input_type == "image":
                image_inputs.append(example_input.content)
                image_indices.append(i)
            else:
                text_inputs.append(example_input.content)
                text_indices.append(i)
        
        # 배치 임베딩 실행
        results = [None] * len(example_inputs)
        
        # 텍스트 배치 처리
        if text_inputs:
            logger.info(f"Batch embedding {len(text_inputs)} text inputs")
            titan_embeddings, cohere_embeddings = await asyncio.gather(
                embedder.embed_text_batch(text_inputs),
                embedder.embed_multilingual_batch(text_inputs),
                return_exceptions=True
            )
            
            # 결과 매핑
            for i, text_idx in enumerate(text_indices):
                titan_emb = titan_embeddings[i] if not isinstance(titan_embeddings, Exception) and i < len(titan_embeddings) else None
                cohere_emb = cohere_embeddings[i] if not isinstance(cohere_embeddings, Exception) and i < len(cohere_embeddings) else None
                
                results[text_idx] = {
                    'index': text_idx,
                    'content': example_inputs[text_idx].content,
                    'type': example_inputs[text_idx].input_type,
                    'titan_embedding': titan_emb if not isinstance(titan_emb, Exception) else None,
                    'cohere_embedding': cohere_emb if not isinstance(cohere_emb, Exception) else None
                }
        
        # 이미지 개별 처리 (배치 지원 안함)
        if image_inputs:
            logger.info(f"Individual embedding {len(image_inputs)} image inputs")
            for i, img_idx in enumerate(image_indices):
                example_input = example_inputs[img_idx]
                nova_task = embedder.embed_multimodal(example_input.content)
                cohere_task = embedder.embed_cohere_v4(example_input.content)
                
                nova_emb, cohere_emb = await asyncio.gather(nova_task, cohere_task, return_exceptions=True)
                
                results[img_idx] = {
                    'index': img_idx,
                    'content': example_input.content,
                    'type': example_input.input_type,
                    'nova_embedding': nova_emb if not isinstance(nova_emb, Exception) else None,
                    'cohere_embedding': cohere_emb if not isinstance(cohere_emb, Exception) else None
                }
        
        return results

    async def _embed_single_input(self, embedder, index: int, example_input: ExampleInput) -> Dict[str, Any]:
        """단일 입력 임베딩 - Cohere와 Nova/Titan 병렬 처리"""
        logger.info(f"Embedding input {index+1}")
        
        if example_input.input_type == "image":
            # 이미지: Nova + Cohere 병렬 처리
            nova_task = embedder.embed_multimodal(example_input.content)
            cohere_task = embedder.embed_cohere_v4(example_input.content)
            
            nova_emb, cohere_emb = await asyncio.gather(nova_task, cohere_task, return_exceptions=True)
            
            return {
                'index': index,
                'content': example_input.content,
                'type': example_input.input_type,
                'nova_embedding': nova_emb if not isinstance(nova_emb, Exception) else None,
                'cohere_embedding': cohere_emb if not isinstance(cohere_emb, Exception) else None
            }
        else:
            # 텍스트: Titan + Cohere 병렬 처리
            titan_task = embedder.embed_text(example_input.content)
            cohere_task = embedder.embed_multilingual(example_input.content)
            
            titan_emb, cohere_emb = await asyncio.gather(titan_task, cohere_task, return_exceptions=True)
            
            return {
                'index': index,
                'content': example_input.content,
                'type': example_input.input_type,
                'titan_embedding': titan_emb if not isinstance(titan_emb, Exception) else None,
                'cohere_embedding': cohere_emb if not isinstance(cohere_emb, Exception) else None
            }
    
    async def _embed_outputs(self, embedder, executions: List[Dict], prompt_type: PromptType) -> List[Dict[str, Any]]:
        """출력 임베딩 생성 - 배치 처리"""
        logger.info(f"Embedding outputs for {len(executions)} inputs using batch processing")
        
        # 모든 출력 텍스트 수집
        all_outputs = []
        output_mapping = []  # (execution_idx, output_idx) 매핑
        
        for exec_idx, exec_data in enumerate(executions):
            outputs = exec_data['outputs']
            for output_idx, output in enumerate(outputs):
                if output.strip():  # 빈 출력 제외
                    all_outputs.append(output)
                    output_mapping.append((exec_idx, output_idx))
        
        if not all_outputs:
            logger.warning("No valid outputs to embed")
            return []
        
        logger.info(f"Batch embedding {len(all_outputs)} outputs")
        
        # 배치 임베딩 실행
        titan_embeddings, cohere_embeddings = await asyncio.gather(
            embedder.embed_text_batch(all_outputs),
            embedder.embed_multilingual_batch(all_outputs),
            return_exceptions=True
        )
        
        # 결과를 execution별로 재구성
        results = []
        for exec_idx, exec_data in enumerate(executions):
            input_index = exec_data['input_index']
            outputs = exec_data['outputs']
            
            exec_embeddings = []
            for output_idx, output in enumerate(outputs):
                if not output.strip():
                    # 빈 출력
                    exec_embeddings.append({
                        'output_index': output_idx,
                        'content': output,
                        'titan_embedding': None,
                        'cohere_embedding': None
                    })
                else:
                    # 배치 결과에서 찾기
                    batch_idx = None
                    for i, (e_idx, o_idx) in enumerate(output_mapping):
                        if e_idx == exec_idx and o_idx == output_idx:
                            batch_idx = i
                            break
                    
                    if batch_idx is not None:
                        titan_emb = None
                        cohere_emb = None
                        
                        if not isinstance(titan_embeddings, Exception) and batch_idx < len(titan_embeddings):
                            titan_emb = titan_embeddings[batch_idx] if not isinstance(titan_embeddings[batch_idx], Exception) else None
                        
                        if not isinstance(cohere_embeddings, Exception) and batch_idx < len(cohere_embeddings):
                            cohere_emb = cohere_embeddings[batch_idx] if not isinstance(cohere_embeddings[batch_idx], Exception) else None
                        
                        exec_embeddings.append({
                            'output_index': output_idx,
                            'content': output,
                            'titan_embedding': titan_emb,
                            'cohere_embedding': cohere_emb
                        })
                    else:
                        logger.error(f"Failed to find batch result for execution {exec_idx}, output {output_idx}")
                        exec_embeddings.append({
                            'output_index': output_idx,
                            'content': output,
                            'titan_embedding': None,
                            'cohere_embedding': None
                        })
            
            results.append({
                'input_index': input_index,
                'embeddings': exec_embeddings
            })
        
        return results

    async def _embed_single_execution_outputs(self, embedder, exec_data: Dict) -> Dict[str, Any]:
        """단일 입력의 모든 출력 임베딩 - 병렬 처리"""
        input_index = exec_data['input_index']
        outputs = exec_data['outputs']
        
        logger.info(f"Embedding {len(outputs)} outputs for input {input_index+1} in parallel")
        
        # 모든 출력을 병렬로 처리
        output_tasks = []
        for output_idx, output in enumerate(outputs):
            task = self._embed_single_output(embedder, output_idx, output)
            output_tasks.append(task)
        
        # 병렬 실행
        exec_embeddings = await asyncio.gather(*output_tasks, return_exceptions=True)
        
        # 예외 처리
        valid_exec_embeddings = []
        for output_idx, result in enumerate(exec_embeddings):
            if isinstance(result, Exception):
                logger.error(f"Output {output_idx+1} embedding failed: {str(result)}")
                # 실패시 기본값
                valid_exec_embeddings.append({
                    'output_index': output_idx,
                    'content': outputs[output_idx],
                    'titan_embedding': None,
                    'cohere_embedding': None
                })
            else:
                valid_exec_embeddings.append(result)
        
        return {
            'input_index': input_index,
            'embeddings': valid_exec_embeddings
        }

    async def _embed_single_output(self, embedder, output_idx: int, output: str) -> Dict[str, Any]:
        """단일 출력 임베딩 - Titan과 Cohere 병렬 처리"""
        if not output.strip():
            # 빈 출력은 제로 벡터로 처리
            return {
                'output_index': output_idx,
                'content': output,
                'titan_embedding': None,
                'cohere_embedding': None
            }
        
        # Titan + Cohere 병렬 처리
        titan_task = embedder.embed_text(output)
        cohere_task = embedder.embed_multilingual(output)
        
        titan_emb, cohere_emb = await asyncio.gather(titan_task, cohere_task, return_exceptions=True)
        
        return {
            'output_index': output_idx,
            'content': output,
            'titan_embedding': titan_emb if not isinstance(titan_emb, Exception) else None,
            'cohere_embedding': cohere_emb if not isinstance(cohere_emb, Exception) else None
        }