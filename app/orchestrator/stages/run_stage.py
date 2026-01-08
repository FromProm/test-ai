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
        recommended_model = None,  # RecommendedModel enum 또는 str
        repeat_count: int = 5,
        prompt_type = None  # PromptType enum 또는 str
    ) -> Dict[str, Any]:
        """
        예시 입력들에 대해 프롬프트를 병렬 실행하고 결과 수집
        Variance 계산을 위한 추가 모델들도 함께 실행
        
        Returns:
            {
                'executions': [...],  # 기존 실행 결과
                'variance_outputs': {  # Variance용 추가 출력
                    'model1': ['output1', 'output2', 'output3'],
                    'model2': ['output1', 'output2', 'output3'],
                    ...
                }
            }
        """
        logger.info(f"Executing prompt with {len(example_inputs)} inputs, {repeat_count} repeats each (parallel)")
        
        runner = self.context.get_runner()
        
        # 모델 선택 - RecommendedModel enum을 문자열로 변환
        if recommended_model:
            if hasattr(recommended_model, 'value'):
                # RecommendedModel enum인 경우
                model = recommended_model.value
                logger.info(f"Using recommended model: {model}")
            else:
                # 이미 문자열인 경우
                model = recommended_model
                logger.info(f"Using model string: {model}")
        else:
            model = self._get_default_model(example_inputs)
            logger.info(f"Using default model: {model}")
        
        # prompt_type을 문자열로 변환
        if prompt_type and hasattr(prompt_type, 'value'):
            prompt_type_str = prompt_type.value
        else:
            prompt_type_str = prompt_type or "type_a"
        
        # Variance 계산용 추가 모델들 가져오기
        variance_models = self._get_variance_models(prompt_type_str, model)
        
        # 모든 실행 태스크 생성
        all_tasks = []
        task_info = []
        
        # 1. 기본 실행 태스크 (기존 로직)
        for i, example_input in enumerate(example_inputs):
            filled_prompt = self._fill_prompt(prompt, example_input.content)
            
            # 각 입력에 대해 repeat_count만큼 태스크 생성
            for repeat in range(repeat_count):
                task = runner.invoke(
                    model=model,
                    prompt=filled_prompt,
                    input_type=example_input.input_type
                )
                all_tasks.append(task)
                task_info.append({
                    'type': 'main',
                    'input_index': i,
                    'repeat_index': repeat,
                    'model': model,
                    'input_content': example_input.content
                })
        
        # 2. Variance 계산용 추가 태스크
        for i, example_input in enumerate(example_inputs):
            filled_prompt = self._fill_prompt(prompt, example_input.content)
            
            for variance_model in variance_models:
                if variance_model != model:  # 기본 모델과 다른 경우만
                    task = runner.invoke(
                        model=variance_model,
                        prompt=filled_prompt,
                        input_type=example_input.input_type
                    )
                    all_tasks.append(task)
                    task_info.append({
                        'type': 'variance',
                        'input_index': i,
                        'model': variance_model,
                        'input_content': example_input.content
                    })
        
        logger.info(f"Running {len(all_tasks)} LLM calls in parallel (including variance models)")
        
        # 모든 태스크 병렬 실행
        logger.info("Starting parallel LLM execution...")
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        logger.info(f"Parallel LLM execution completed. Got {len(results)} results")
        
        # 결과를 분류하여 정리
        logger.info("Processing execution results...")
        executions = []
        variance_outputs = {}
        
        # 기본 실행 결과 처리
        for i in range(len(example_inputs)):
            outputs = []
            total_token_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
            
            # 해당 입력의 기본 실행 결과들 수집
            for j, (result, info) in enumerate(zip(results, task_info)):
                if info['type'] == 'main' and info['input_index'] == i:
                    if isinstance(result, Exception):
                        logger.error(f"Failed execution for input {i+1}, repeat {info['repeat_index']+1}: {str(result)}")
                        outputs.append("")
                    else:
                        outputs.append(result['output'])
                        
                        if 'token_usage' in result:
                            for key in total_token_usage:
                                total_token_usage[key] += result['token_usage'].get(key, 0)
            
            executions.append({
                'input_index': i,
                'input_content': example_inputs[i].content,
                'input_type': example_inputs[i].input_type,
                'outputs': outputs,
                'model': model,
                'token_usage': total_token_usage
            })
        
        # Variance 결과 처리
        for variance_model in variance_models:
            variance_outputs[variance_model] = []
            
            for i in range(len(example_inputs)):
                # 해당 입력의 variance 결과 찾기
                variance_output = ""
                for j, (result, info) in enumerate(zip(results, task_info)):
                    if (info['type'] == 'variance' and 
                        info['input_index'] == i and 
                        info['model'] == variance_model):
                        if isinstance(result, Exception):
                            logger.error(f"Failed variance execution for {variance_model}, input {i+1}: {str(result)}")
                            variance_output = ""
                        else:
                            variance_output = result['output']
                        break
                    elif (info['type'] == 'main' and 
                          info['input_index'] == i and 
                          info['repeat_index'] == 0 and  # 첫 번째 반복만
                          info['model'] == variance_model):
                        # 기본 모델과 variance 모델이 같은 경우
                        if isinstance(result, Exception):
                            variance_output = ""
                        else:
                            variance_output = result['output']
                        break
                
                variance_outputs[variance_model].append(variance_output)
        
        logger.info(f"Parallel execution completed: {len(executions)} inputs processed with variance models")
        return {
            'executions': executions,
            'variance_outputs': variance_outputs
        }
    
    def _get_variance_models(self, prompt_type: str, main_model: str) -> List[str]:
        """Variance 계산용 모델들 반환 - config의 model_families 사용 (테스트용으로 1개만)"""
        # config에서 비교 모델 가져오기
        comparison_models = settings.model_families.get(main_model, [])
        
        # 테스트용으로 첫 번째 비교 모델만 사용
        if comparison_models:
            comparison_models = comparison_models[:1]
        
        # 선택된 모델 + 비교 모델들
        all_models = [main_model] + comparison_models
        
        logger.info(f"Variance models for {main_model}: {all_models}")
        return all_models
    
    def _get_default_model(self, example_inputs: List[ExampleInput]) -> str:
        """입력 타입에 따른 기본 모델 선택"""
        has_image = any(inp.input_type == "image" for inp in example_inputs)
        
        if has_image:
            return settings.default_models["type_b_image"]
        else:
            return settings.default_models["type_a"]
    
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