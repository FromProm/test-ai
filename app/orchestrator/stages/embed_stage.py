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
        """입력 임베딩 생성"""
        input_embeddings = []
        
        for i, example_input in enumerate(example_inputs):
            logger.info(f"Embedding input {i+1}/{len(example_inputs)}")
            
            # 텍스트와 이미지에 따라 다른 모델 사용
            if example_input.input_type == "image":
                # 이미지 임베딩 (Nova Multimodal + Cohere v4)
                nova_emb = await embedder.embed_multimodal(example_input.content)
                cohere_emb = await embedder.embed_cohere_v4(example_input.content)
                
                input_embeddings.append({
                    'index': i,
                    'content': example_input.content,
                    'type': example_input.input_type,
                    'nova_embedding': nova_emb,
                    'cohere_embedding': cohere_emb
                })
            else:
                # 텍스트 임베딩 (Titan Text + Cohere Multilingual)
                titan_emb = await embedder.embed_text(example_input.content)
                cohere_emb = await embedder.embed_multilingual(example_input.content)
                
                input_embeddings.append({
                    'index': i,
                    'content': example_input.content,
                    'type': example_input.input_type,
                    'titan_embedding': titan_emb,
                    'cohere_embedding': cohere_emb
                })
        
        return input_embeddings
    
    async def _embed_outputs(self, embedder, executions: List[Dict], prompt_type: PromptType) -> List[Dict[str, Any]]:
        """출력 임베딩 생성"""
        output_embeddings = []
        
        for exec_data in executions:
            input_index = exec_data['input_index']
            outputs = exec_data['outputs']
            
            logger.info(f"Embedding outputs for input {input_index+1}")
            
            exec_embeddings = []
            for output_idx, output in enumerate(outputs):
                if not output.strip():
                    # 빈 출력은 제로 벡터로 처리
                    exec_embeddings.append({
                        'output_index': output_idx,
                        'content': output,
                        'titan_embedding': None,
                        'cohere_embedding': None
                    })
                    continue
                
                # 출력은 항상 텍스트로 처리
                titan_emb = await embedder.embed_text(output)
                cohere_emb = await embedder.embed_multilingual(output)
                
                exec_embeddings.append({
                    'output_index': output_idx,
                    'content': output,
                    'titan_embedding': titan_emb,
                    'cohere_embedding': cohere_emb
                })
            
            output_embeddings.append({
                'input_index': input_index,
                'embeddings': exec_embeddings
            })
        
        return output_embeddings