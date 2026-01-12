import logging
import json
import asyncio
from typing import Dict, Any, List
from app.orchestrator.context import ExecutionContext
from app.core.schemas import MetricScore, ExampleInput, PromptType
from app.core.config import settings

logger = logging.getLogger(__name__)

class RelevanceStage:
    """정확도 계산 단계 - AI 기반 조건 준수 평가"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
    
    async def execute(
        self, 
        prompt: str,
        example_inputs: List[ExampleInput],
        execution_results: Dict[str, Any],
        prompt_type: PromptType
    ) -> MetricScore:
        """
        정확도 점수 계산 (병렬 처리)
        1. 입력 프롬프트에서 명시적 조건과 방향성 추출
        2. AI 판단을 통한 조건 준수 여부 평가
        3. 100점 만점 점수 계산
        """
        logger.info("Calculating accuracy score using AI-based evaluation (parallel)")
        
        try:
            judge = self.context.get_judge()
            executions = execution_results['executions']
            
            # 모든 입력에 대해 병렬로 처리
            logger.info(f"Processing {len(example_inputs)} inputs in parallel")
            
            async def process_single_input(i: int, example_input: ExampleInput):
                """단일 입력 처리"""
                # 1. 입력 프롬프트에서 조건과 방향성 추출
                conditions = await self._extract_conditions(judge, prompt, example_input.content)
                
                if not conditions.get('explicit_conditions') and not conditions.get('direction'):
                    logger.warning(f"No conditions extracted for input {i}")
                    return {
                        'input_index': i,
                        'score': 50.0,
                        'conditions': conditions,
                        'evaluation_details': []
                    }
                
                # 해당 입력의 출력들 찾기
                exec_data = next((e for e in executions if e['input_index'] == i), None)
                if not exec_data:
                    logger.warning(f"No execution data for input {i}")
                    return {
                        'input_index': i,
                        'score': 0.0,
                        'conditions': conditions,
                        'evaluation_details': []
                    }
                
                # 2. 각 출력에 대해 조건 준수 평가 (병렬)
                async def evaluate_single_output(j: int, output: str):
                    if not output.strip():
                        return {'output_index': j, 'score': 0.0, 'evaluation': None}
                    
                    evaluation = await self._evaluate_compliance(
                        judge, conditions, output, example_input.input_type, prompt_type
                    )
                    score = self._calculate_compliance_score(evaluation)
                    return {'output_index': j, 'score': score, 'evaluation': evaluation}
                
                # 출력들 병렬 평가
                output_tasks = [
                    evaluate_single_output(j, output) 
                    for j, output in enumerate(exec_data['outputs'])
                ]
                output_results = await asyncio.gather(*output_tasks, return_exceptions=True)
                
                # 결과 처리
                output_scores = []
                evaluation_details = []
                for result in output_results:
                    if isinstance(result, Exception):
                        logger.error(f"Output evaluation failed: {str(result)}")
                        output_scores.append(0.0)
                    else:
                        output_scores.append(result['score'])
                        evaluation_details.append(result)
                
                input_score = sum(output_scores) / len(output_scores) if output_scores else 0.0
                
                return {
                    'input_index': i,
                    'score': input_score,
                    'conditions': conditions,
                    'evaluation_details': evaluation_details,
                    'output_count': len(output_scores)
                }
            
            # 모든 입력 병렬 처리
            import asyncio
            input_tasks = [
                process_single_input(i, example_input)
                for i, example_input in enumerate(example_inputs)
            ]
            input_results = await asyncio.gather(*input_tasks, return_exceptions=True)
            
            # 결과 집계
            all_accuracy_scores = []
            details = {'per_input_scores': [], 'extracted_conditions': []}
            
            for result in input_results:
                if isinstance(result, Exception):
                    logger.error(f"Input processing failed: {str(result)}")
                    all_accuracy_scores.append(0.0)
                else:
                    all_accuracy_scores.append(result['score'])
                    details['extracted_conditions'].append({
                        'input_index': result['input_index'],
                        'conditions': result['conditions']
                    })
                    details['per_input_scores'].append({
                        'input_index': result['input_index'],
                        'score': result['score'],
                        'output_count': result.get('output_count', 0),
                        'evaluation_details': result['evaluation_details']
                    })
            
            # 전체 평균 점수 (100점 만점)
            final_score = sum(all_accuracy_scores) / len(all_accuracy_scores) if all_accuracy_scores else 0.0
            
            details['final_score'] = final_score
            details['note'] = 'AI-based accuracy evaluation (parallel), score out of 100'
            
            logger.info(f"Accuracy score: {final_score:.3f}")
            return MetricScore(score=final_score, details=details)
            
        except Exception as e:
            logger.error(f"Accuracy calculation failed: {str(e)}")
            return MetricScore(score=0.0, details={'error': str(e)})
    
    async def _extract_conditions(self, judge, prompt: str, input_content: str) -> Dict[str, Any]:
        """입력 프롬프트에서 명시적 조건과 방향성 추출"""
        
        extraction_prompt = f"""
다음 프롬프트를 분석하여 명시적 조건과 방향성을 추출해주세요.

프롬프트: {prompt}
입력 내용: {input_content}

다음 형식으로 JSON 응답해주세요:
{{
    "explicit_conditions": [
        "조건1: 구체적인 요구사항",
        "조건2: 형식이나 길이 제한",
        "조건3: 포함해야 할 내용"
    ],
    "direction": "프롬프트가 지시하는 핵심 방향성과 목적"
}}

명시적 조건은 구체적으로 언급된 요구사항만 포함하고, 방향성은 전체적인 의도를 요약해주세요.
"""
        
        try:
            result = await judge.evaluate(extraction_prompt, "condition_extraction")
            # JSON 파싱 시도
            if result.startswith('{') and result.endswith('}'):
                return json.loads(result)
            else:
                # JSON이 아닌 경우 기본 구조 반환
                return {
                    "explicit_conditions": ["조건 추출 실패"],
                    "direction": result[:200]  # 처음 200자만
                }
        except Exception as e:
            logger.error(f"Condition extraction failed: {str(e)}")
            return {
                "explicit_conditions": [],
                "direction": "방향성 추출 실패"
            }
    
    async def _evaluate_compliance(
        self, 
        judge, 
        conditions: Dict[str, Any], 
        output: str, 
        input_type: str,
        prompt_type: PromptType
    ) -> Dict[str, str]:
        """AI를 통한 조건 준수 평가"""
        
        # 이미지 출력인 경우 VLM 사용 고려
        model_note = ""
        if input_type == "image" or prompt_type == PromptType.TYPE_B_IMAGE:
            model_note = "(이미지 분석 가능한 모델 사용)"
        
        evaluation_prompt = f"""
다음 조건들이 출력에서 얼마나 잘 지켜졌는지 평가해주세요. {model_note}

명시적 조건들:
{chr(10).join(f"- {cond}" for cond in conditions.get('explicit_conditions', []))}

방향성/핵심 과정:
{conditions.get('direction', '없음')}

출력 내용:
{output}

각 조건에 대해 다음 중 하나로 평가해주세요:
- "지킴": 조건을 명확히 준수함
- "안지킴": 조건을 명확히 위반함  
- "애매함": 판단하기 어렵거나 부분적으로만 준수

다음 JSON 형식으로 응답해주세요:
{{
    "explicit_conditions_compliance": [
        {{"condition": "조건1", "status": "지킴|안지킴|애매함", "reason": "판단 근거"}},
        {{"condition": "조건2", "status": "지킴|안지킴|애매함", "reason": "판단 근거"}}
    ],
    "direction_compliance": {{"status": "지킴|안지킴|애매함", "reason": "방향성 준수 여부와 근거"}},
    "overall_assessment": "전체적인 평가 요약"
}}
"""
        
        try:
            result = await judge.evaluate(evaluation_prompt, "compliance_evaluation")
            if result.startswith('{') and result.endswith('}'):
                return json.loads(result)
            else:
                # JSON 파싱 실패시 기본 응답
                return {
                    "explicit_conditions_compliance": [],
                    "direction_compliance": {"status": "애매함", "reason": "평가 실패"},
                    "overall_assessment": result[:200]
                }
        except Exception as e:
            logger.error(f"Compliance evaluation failed: {str(e)}")
            return {
                "explicit_conditions_compliance": [],
                "direction_compliance": {"status": "애매함", "reason": f"평가 오류: {str(e)}"},
                "overall_assessment": "평가 실패"
            }
    
    def _calculate_compliance_score(self, evaluation: Dict[str, Any]) -> float:
        """평가 결과를 100점 만점 점수로 변환 (동적 가중치)"""
        
        # 명시적 조건 점수 계산
        explicit_conditions = evaluation.get('explicit_conditions_compliance', [])
        condition_count = len(explicit_conditions)
        
        # 동적 가중치 결정
        if condition_count == 0:
            # 조건 없음 → 방향성 100%
            explicit_weight = 0.0
            direction_weight = 1.0
        elif condition_count <= 3:
            # 조건 1-3개 → 70:30
            explicit_weight = 0.7
            direction_weight = 0.3
        else:
            # 조건 4개+ → 80:20
            explicit_weight = 0.8
            direction_weight = 0.2
        
        total_score = 0.0
        
        # 명시적 조건 점수
        if explicit_conditions and explicit_weight > 0:
            condition_scores = []
            for cond_eval in explicit_conditions:
                status = cond_eval.get('status', '애매함')
                if status == '지킴':
                    condition_scores.append(100.0)
                elif status == '안지킴':
                    condition_scores.append(0.0)
                else:  # 애매함
                    condition_scores.append(50.0)
            
            if condition_scores:
                avg_condition_score = sum(condition_scores) / len(condition_scores)
                total_score += avg_condition_score * explicit_weight
        
        # 방향성 점수
        direction_compliance = evaluation.get('direction_compliance', {})
        direction_status = direction_compliance.get('status', '애매함')
        
        if direction_status == '지킴':
            direction_score = 100.0
        elif direction_status == '안지킴':
            direction_score = 0.0
        else:  # 애매함
            direction_score = 50.0
        
        total_score += direction_score * direction_weight
        
        return total_score