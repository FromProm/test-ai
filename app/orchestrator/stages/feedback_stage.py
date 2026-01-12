import logging
from typing import Dict, Any, Optional
from app.orchestrator.context import ExecutionContext
from app.adapters.runner.bedrock_runner import BedrockRunner
from app.core.schemas import PromptType

logger = logging.getLogger(__name__)

class FeedbackStage:
    """프롬프트 개선 피드백 생성 단계"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        self.runner = BedrockRunner()
        # 피드백 생성용 모델 (저렴한 모델 사용)
        self.feedback_model = "anthropic.claude-3-haiku-20240307-v1:0"
    
    async def execute(
        self, 
        evaluation_result: Dict[str, Any],
        prompt: str = "",
        prompt_type: PromptType = PromptType.TYPE_A,
        example_inputs: list = None
    ) -> Dict[str, Any]:
        """
        평가 결과를 분석하여 프롬프트 개선 피드백 생성
        
        Args:
            evaluation_result: 평가 결과 (각 지표 점수 + details)
            prompt: 평가된 프롬프트
            prompt_type: 프롬프트 타입
            example_inputs: 예시 입력들
            
        Returns:
            피드백 결과 딕셔너리
        """
        logger.info("Generating prompt improvement feedback")
        
        if example_inputs is None:
            example_inputs = []
        
        try:
            # 1. 평가 결과에서 정보 추출
            metrics = self._extract_metrics(evaluation_result)
            outputs = self._extract_outputs(evaluation_result)
            
            # 2. LLM에게 피드백 요청
            feedback_prompt = self._build_feedback_prompt(
                prompt=prompt,
                prompt_type=prompt_type,
                example_inputs=example_inputs,
                outputs=outputs,
                metrics=metrics
            )
            
            response = await self.runner.invoke(
                model=self.feedback_model,
                prompt=feedback_prompt,
                max_tokens=2000,
                temperature=0.3
            )
            
            # 3. 응답 파싱
            feedback = self._parse_feedback_response(response['output'], metrics)
            
            logger.info("Feedback generation completed")
            return feedback
            
        except Exception as e:
            logger.error(f"Feedback generation failed: {str(e)}")
            return self._generate_fallback_feedback(evaluation_result)
    
    def _extract_metrics(self, evaluation_result: Dict[str, Any]) -> Dict[str, float]:
        """평가 결과에서 지표 점수 추출"""
        metrics = {}
        
        metric_keys = [
            'token_usage', 'information_density', 'consistency',
            'model_variance', 'hallucination', 'relevance'
        ]
        
        for key in metric_keys:
            if key in evaluation_result and evaluation_result[key]:
                score = evaluation_result[key].get('score', 0)
                metrics[key] = score
        
        return metrics
    
    def _extract_outputs(self, evaluation_result: Dict[str, Any]) -> list:
        """평가 결과에서 출력 샘플 추출"""
        outputs = []
        
        if 'execution_results' in evaluation_result:
            exec_results = evaluation_result['execution_results']
            if 'executions' in exec_results:
                for exec_data in exec_results['executions'][:3]:  # 최대 3개만
                    if 'outputs' in exec_data and exec_data['outputs']:
                        # 첫 번째 출력만 (너무 길면 자름)
                        output = exec_data['outputs'][0]
                        if len(output) > 500:
                            output = output[:500] + "..."
                        outputs.append(output)
        
        return outputs
    
    def _build_feedback_prompt(
        self,
        prompt: str,
        prompt_type: PromptType,
        example_inputs: list,
        outputs: list,
        metrics: Dict[str, float]
    ) -> str:
        """피드백 생성용 프롬프트 구성"""
        
        # 지표 설명
        metric_descriptions = {
            'token_usage': '토큰 사용량 (낮을수록 효율적)',
            'information_density': '정보 밀도 (높을수록 반복 적음)',
            'consistency': '일관성 (높을수록 출력이 일정)',
            'model_variance': '모델 편차 (높을수록 모델 간 차이 적음)',
            'hallucination': '환각 탐지 (높을수록 사실 정확)',
            'relevance': '관련성 (높을수록 입력-출력 연관성 높음)'
        }
        
        # 지표 점수 문자열 생성
        metrics_str = "\n".join([
            f"- {metric_descriptions.get(k, k)}: {v:.1f}점"
            for k, v in metrics.items()
        ])
        
        # 예시 입력 문자열
        inputs_str = "\n".join([
            f"- 입력 {i+1}: {getattr(inp, 'content', str(inp))[:100]}"
            for i, inp in enumerate(example_inputs[:3])
        ])
        
        # 출력 샘플 문자열
        outputs_str = "\n".join([
            f"- 출력 {i+1}: {out[:200]}..." if len(out) > 200 else f"- 출력 {i+1}: {out}"
            for i, out in enumerate(outputs[:3])
        ])
        
        prompt_type_str = {
            PromptType.TYPE_A: "정보/사실 요구형",
            PromptType.TYPE_B_TEXT: "창작 글 생성형",
            PromptType.TYPE_B_IMAGE: "이미지 생성형"
        }.get(prompt_type, "알 수 없음")
        
        return f"""당신은 프롬프트 엔지니어링 전문가입니다. 
아래 프롬프트의 평가 결과를 분석하고, 개선 방안을 제시해주세요.

## 프롬프트 정보
- 타입: {prompt_type_str}
- 프롬프트: "{prompt}"

## 예시 입력
{inputs_str}

## 출력 샘플
{outputs_str}

## 평가 점수 (100점 만점)
{metrics_str}

## 요청사항
다음 형식으로 피드백을 작성해주세요:

1. 전체 분석 (2-3문장으로 핵심 문제점 요약)

2. 지표별 개선 여지 (각 지표에 대해 한 줄씩):
- [지표명] ([현재점수]점): [개선 방안 및 예상 효과]

3. 개선된 프롬프트 제안 (실제 사용 가능한 형태로)

점수가 80점 이상인 지표는 "현재 양호" 정도로 간단히 언급하고,
점수가 낮은 지표에 집중해서 구체적인 개선 방안을 제시해주세요.
"""
    
    def _parse_feedback_response(self, response: str, metrics: Dict[str, float]) -> Dict[str, Any]:
        """LLM 응답을 구조화된 피드백으로 파싱"""
        
        # 기본 구조
        feedback = {
            'overall_analysis': '',
            'metric_improvements': [],
            'improved_prompt': '',
            'raw_feedback': response
        }
        
        lines = response.strip().split('\n')
        current_section = None
        section_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 섹션 감지
            if '전체 분석' in line or '핵심 문제점' in line:
                if current_section and section_content:
                    self._save_section(feedback, current_section, section_content)
                current_section = 'overall'
                section_content = []
            elif '지표별' in line or '개선 여지' in line:
                if current_section and section_content:
                    self._save_section(feedback, current_section, section_content)
                current_section = 'metrics'
                section_content = []
            elif '개선된 프롬프트' in line or '프롬프트 제안' in line:
                if current_section and section_content:
                    self._save_section(feedback, current_section, section_content)
                current_section = 'prompt'
                section_content = []
            elif current_section:
                section_content.append(line)
        
        # 마지막 섹션 저장
        if current_section and section_content:
            self._save_section(feedback, current_section, section_content)
        
        # 지표별 개선 여지 파싱
        if not feedback['metric_improvements']:
            feedback['metric_improvements'] = self._generate_metric_improvements(metrics)
        
        return feedback
    
    def _save_section(self, feedback: Dict, section: str, content: list):
        """섹션 내용 저장"""
        text = '\n'.join(content).strip()
        
        if section == 'overall':
            feedback['overall_analysis'] = text
        elif section == 'metrics':
            # 지표별 개선 여지 파싱
            improvements = []
            for line in content:
                if line.startswith('-') or line.startswith('•'):
                    improvements.append(line.lstrip('-•').strip())
            feedback['metric_improvements'] = improvements
        elif section == 'prompt':
            feedback['improved_prompt'] = text
    
    def _generate_metric_improvements(self, metrics: Dict[str, float]) -> list:
        """지표 점수 기반 기본 개선 제안 생성"""
        improvements = []
        
        suggestions = {
            'token_usage': {
                'low': '불필요한 지시사항 제거 시 효율성 개선 가능',
                'high': '현재 양호, 큰 변화 없을 것'
            },
            'information_density': {
                'low': '"간결하게 답변해줘" 지시 추가 시 개선 가능',
                'high': '현재 양호, 큰 변화 없을 것'
            },
            'consistency': {
                'low': '출력 형식 명시 시 상승 여지 높음',
                'high': '현재 양호, 큰 변화 없을 것'
            },
            'model_variance': {
                'low': '제약조건 명확화 시 상승 기대',
                'high': '현재 양호, 큰 변화 없을 것'
            },
            'hallucination': {
                'low': '"출처를 명시해줘" 또는 "확실한 정보만" 추가 시 개선 가능',
                'high': '현재 양호, 큰 변화 없을 것'
            },
            'relevance': {
                'low': '질문 범위를 좁히거나 구체화 시 개선 가능',
                'high': '현재 양호, 큰 변화 없을 것'
            }
        }
        
        metric_names = {
            'token_usage': '토큰 사용량',
            'information_density': '정보 밀도',
            'consistency': '일관성',
            'model_variance': '모델 편차',
            'hallucination': '환각 탐지',
            'relevance': '관련성'
        }
        
        for metric, score in metrics.items():
            if metric in suggestions:
                name = metric_names.get(metric, metric)
                level = 'high' if score >= 80 else 'low'
                suggestion = suggestions[metric][level]
                improvements.append(f"{name} ({score:.0f}점): {suggestion}")
        
        return improvements
    
    def _generate_fallback_feedback(self, evaluation_result: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 호출 실패 시 기본 피드백 생성"""
        metrics = self._extract_metrics(evaluation_result)
        
        return {
            'overall_analysis': '평가 결과를 기반으로 자동 생성된 피드백입니다.',
            'metric_improvements': self._generate_metric_improvements(metrics),
            'improved_prompt': '',
            'error': 'LLM 피드백 생성 실패, 기본 피드백 제공'
        }
    
    def format_feedback(self, feedback: Dict[str, Any]) -> str:
        """피드백을 사람이 읽기 좋은 형식으로 포맷팅"""
        
        output = []
        output.append("📊 프롬프트 평가 피드백")
        output.append("")
        
        # 전체 분석
        if feedback.get('overall_analysis'):
            output.append("🔍 전체 분석")
            output.append(feedback['overall_analysis'])
            output.append("")
        
        # 지표별 개선 여지
        if feedback.get('metric_improvements'):
            output.append("📈 지표별 개선 여지:")
            for improvement in feedback['metric_improvements']:
                output.append(f"- {improvement}")
            output.append("")
        
        # 개선된 프롬프트 제안
        if feedback.get('improved_prompt'):
            output.append("✨ 개선된 프롬프트 제안:")
            output.append(feedback['improved_prompt'])
        
        return '\n'.join(output)
