import asyncio
import logging
from typing import List, Dict, Any
from app.orchestrator.context import ExecutionContext
from app.core.schemas import ExampleInput
from app.core.config import settings

logger = logging.getLogger(__name__)

class RunStage:
    """프롬프트 실행 단계 - Runner 호출"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(
        self, 
        prompt: str, 
        example_inputs: List[ExampleInput], 
        recommended_model: str = None,
        repeat_count: int = 5
    ) -> Dict[str, Any]:
        """
        예시 입력들에 대해 프롬프트를 실행하고 결과 수집
        
        Returns:
            {
                'executions': [
                    {
                        'input_index': 0,
                        'input_content': '...',
                        'outputs': ['output1', 'output2', ...],
                        'model': 'model_name',
                        'token_usage': {...}
                    },
                    ...
                ]
            }
        """
        logger.info(f"Executing prompt with {len(example_inputs)} inputs, {repeat_count} repeats each")
        
        runner = self.context.get_runner()
        executions = []
        
        # 모델 선택
        model = recommended_model or self._get_default_model(example_inputs)
        
        for i, example_input in enumerate(example_inputs):
            logger.info(f"Processing input {i+1}/{len(example_inputs)}")
            
            # 프롬프트에 입력 삽입
            filled_prompt = self._fill_prompt(prompt, example_input.content)
            
            # 반복 실행
            outputs = []
            total_token_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
            
            for repeat in range(repeat_count):
                try:
                    result = await runner.invoke(
                        model=model,
                        prompt=filled_prompt,
                        input_type=example_input.input_type
                    )
                    
                    outputs.append(result['output'])
                    
                    # 토큰 사용량 누적
                    if 'token_usage' in result:
                        for key in total_token_usage:
                            total_token_usage[key] += result['token_usage'].get(key, 0)
                    
                except Exception as e:
                    logger.error(f"Failed to execute repeat {repeat+1} for input {i+1}: {str(e)}")
                    # 실패한 경우 빈 출력으로 처리
                    outputs.append("")
            
            executions.append({
                'input_index': i,
                'input_content': example_input.content,
                'input_type': example_input.input_type,
                'outputs': outputs,
                'model': model,
                'token_usage': total_token_usage
            })
        
        return {'executions': executions}
    
    def _get_default_model(self, example_inputs: List[ExampleInput]) -> str:
        """입력 타입에 따른 기본 모델 선택"""
        has_image = any(inp.input_type == "image" for inp in example_inputs)
        
        if has_image:
            return settings.default_models["type_b_image"]
        else:
            return settings.default_models["type_a"]
    
    def _fill_prompt(self, prompt: str, input_content: str) -> str:
        """프롬프트의 {{}} 플레이스홀더를 실제 입력으로 치환"""
        # 간단한 구현 - 실제로는 더 정교한 템플릿 엔진 필요
        return prompt.replace("{{}}", input_content).replace("{{input}}", input_content)