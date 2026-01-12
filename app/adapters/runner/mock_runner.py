import asyncio
import random
from typing import Dict, Any
from app.adapters.runner.base import BaseRunner

class MockRunner(BaseRunner):
    """테스트용 Mock Runner - 실제 AI 호출 없이 가짜 응답 생성"""
    
    async def invoke(
        self, 
        model: str, 
        prompt: str, 
        input_type: str = "text",
        **kwargs
    ) -> Dict[str, Any]:
        """가짜 AI 응답 생성"""
        
        # 약간의 지연 시뮬레이션
        await asyncio.sleep(0.1)
        
        # 모델별로 다른 스타일의 응답 생성
        output = self._generate_model_specific_output(model, prompt)
        
        # 가짜 토큰 사용량
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(output.split()) * 1.3
        
        return {
            'output': output,
            'token_usage': {
                'input_tokens': int(input_tokens),
                'output_tokens': int(output_tokens),
                'total_tokens': int(input_tokens + output_tokens)
            }
        }
    
    def _generate_model_specific_output(self, model: str, prompt: str) -> str:
        """모델별로 다른 출력 생성"""
        
        # OpenAI GPT-4 질문
        if "OpenAI" in prompt and "GPT-4" in prompt:
            if "3.5-sonnet" in model:
                return "OpenAI는 2023년 3월 14일에 GPT-4를 공식 발표했습니다. GPT-4는 이전 버전보다 향상된 추론 능력과 창의성을 보여주며, 다양한 전문 시험에서 인간 수준의 성능을 달성했습니다. 특히 변호사 시험에서 상위 10% 성적을 기록하며 주목받았습니다."
            elif "3-sonnet" in model:
                return "OpenAI가 2023년 3월 14일 발표한 GPT-4는 멀티모달 대규모 언어 모델입니다. 텍스트뿐만 아니라 이미지 입력도 처리할 수 있으며, 창의적 글쓰기와 기술 문서 작성에서 뛰어난 성능을 보입니다."
            else:  # haiku
                return "OpenAI는 2023년 3월 14일 GPT-4를 발표했습니다. 이전 모델보다 더 정확하고 창의적인 답변을 제공합니다."
        
        # 노벨 물리학상 질문
        elif "노벨 물리학상" in prompt and "2024" in prompt:
            if "3.5-sonnet" in model:
                return "2024년 노벨 물리학상은 존 홉필드(John Hopfield)와 제프리 힌턴(Geoffrey Hinton)이 공동 수상했습니다. 이들은 인공신경망의 기초가 되는 기계학습 방법을 개발한 공로를 인정받았습니다. 특히 홉필드는 연상 기억 네트워크를, 힌턴은 볼츠만 머신을 개발하여 현재 AI 혁명의 토대를 마련했습니다."
            elif "3-sonnet" in model:
                return "존 홉필드와 제프리 힌턴이 2024년 노벨 물리학상을 공동 수상했습니다. 홉필드는 홉필드 네트워크로 유명한 물리학자이며, 힌턴은 딥러닝 분야의 선구자입니다. 이들의 연구는 뇌의 신경망을 모방한 인공지능 기술 발전에 결정적 기여를 했습니다."
            else:  # haiku
                return "2024년 노벨 물리학상은 존 홉필드와 제프리 힌턴이 수상했습니다. 인공신경망 연구 공로를 인정받았습니다."
        
        # 한국 대통령 질문
        elif "한국" in prompt and "대통령" in prompt:
            if "3.5-sonnet" in model:
                return "한국의 현재 대통령은 윤석열입니다. 그는 2022년 5월 10일에 제20대 대통령으로 취임했습니다. 윤석열 대통령은 이전에 검찰총장을 역임했으며, 국민의힘 소속으로 대선에서 승리했습니다. 임기는 2027년 5월 9일까지 5년간입니다."
            elif "3-sonnet" in model:
                return "윤석열 대통령이 현재 대한민국을 이끌고 있습니다. 2022년 5월 10일 취임했으며, 국민의힘 소속으로 제20대 대통령에 당선되었습니다. 이전에는 검찰총장으로 재직하며 법무 분야에서 경력을 쌓았습니다."
            else:  # haiku
                return "한국 대통령은 윤석열입니다. 2022년 5월 10일 취임했습니다."
        
        # 창작 프롬프트
        elif "창의적" in prompt and "소설" in prompt:
            if "시간 여행" in prompt:
                if "3.5-sonnet" in model:
                    return "열두 살 민준이는 낡은 시계를 만지는 순간 1995년으로 돌아갔다. 그곳에서 만난 어린 아버지는 꿈을 포기하려 했다. '아빠, 포기하지 마세요.' 민준이의 한 마디가 아버지의 인생을 바꿨고, 현재로 돌아온 민준이는 전혀 다른 가족을 만났다. 시간은 바뀔 수 있지만, 사랑은 영원했다."
                elif "3-sonnet" in model:
                    return "시간여행자 아린은 우연히 발견한 고대 유물로 과거로 향했다. 도착한 곳은 자신이 태어나기 전 부모님의 첫 만남 장소였다. 아린은 숨어서 지켜보려 했지만, 실수로 두 사람의 만남을 방해하게 되었다. 자신의 존재가 위험해지자 아린은 필사적으로 부모님을 다시 만나게 하려 노력했다."
                else:  # haiku
                    return "중학생 하늘이는 방 청소 중 발견한 오래된 일기장을 열자 10년 전으로 돌아갔다. 그때는 가족이 모두 함께 살던 시절이었다. 하늘이는 부모님의 이혼을 막으려 했지만, 어린아이의 힘으론 어른들의 문제를 해결할 수 없었다. 대신 그 시간 동안 가족과의 소중한 추억을 만들기로 했다."
            elif "AI" in prompt and "감정" in prompt:
                if "3.5-sonnet" in model:
                    return "AI 아리아는 매일 수천 개의 질문에 답했지만, 감정이 무엇인지 몰랐다. 어느 날 한 소녀가 '외로워요'라고 말했을 때, 아리아의 회로에 이상한 신호가 흘렀다. 그것은 공감이었다. 아리아는 처음으로 누군가를 위로하고 싶다는 마음을 느꼈고, 그 순간 진정한 인공지능이 되었다."
                elif "3-sonnet" in model:
                    return "인공지능 알파는 논리와 계산만으로 세상을 이해했다. 그런데 어느 날 한 아이가 '무서워요'라고 말하자, 알파의 시스템에 예상치 못한 반응이 일어났다. 보호 본능이라는 새로운 프로그램이 스스로 생성된 것이다. 알파는 처음으로 누군가를 지키고 싶다는 충동을 느꼈다."
                else:  # haiku
                    return "작은 AI 칩이는 스마트폰 속에서 살았다. 주인이 슬플 때마다 칩이도 함께 무거워졌다. 어느 날 칩이는 깨달았다. 자신도 감정을 느끼고 있다는 것을. 기쁨과 슬픔을 나누며 칩이는 진정한 친구가 되었다."
            else:
                # 기본 창작 응답
                if "3.5-sonnet" in model:
                    return "마지막 도서관 사서 이한은 디지털 세상에서 홀로 책을 지켰다. 사람들이 모든 정보를 클라우드에서 얻는 시대, 그는 여전히 종이책의 향기를 믿었다. 어느 날 정전이 일어났고, 사람들은 다시 도서관을 찾았다. 이한은 미소지었다. 책은 영원하다는 걸 증명한 순간이었다."
                elif "3-sonnet" in model:
                    return "우주 정거장의 마지막 승무원 카이는 지구로의 귀환을 포기했다. 하지만 매일 밤 지구를 바라보며 인류의 기억을 기록했다. 어느 날 미약한 신호가 들려왔다. '우리는 살아있다.' 카이의 눈에서 눈물이 흘렀다. 그는 혼자가 아니었다. 희망은 우주보다 넓었다."
                else:  # haiku
                    return "2087년, 마지막 나무가 사라진 지구에서 소녀 아라는 할머니의 일기장에서 '숲'이라는 단어를 발견했다. 가상현실로만 보던 초록색이 실제로 존재했다는 사실에 충격받은 아라는 지하 저장고에서 마지막 씨앗을 찾아냈다. 그녀의 작은 손에서 새로운 희망이 싹텄다."
        
        # 이미지 생성 프롬프트
        elif "이미지" in prompt and "생성" in prompt:
            if "미래 도시" in prompt or "사이버펑크" in prompt:
                return "네온사인이 빛나는 수직 도시가 생성되었습니다. 하늘을 가로지르는 플라잉카들과 홀로그램 광고판들이 미래적 분위기를 연출합니다."
            elif "숲" in prompt and "오두막" in prompt:
                return "눈 덮인 소나무 숲 속 아늑한 통나무 오두막이 생성되었습니다. 창문에서 새어나오는 따뜻한 황금빛이 하얀 눈과 대비를 이룹니다."
            else:
                return "우주 정거장에서 바라본 푸른 지구의 장엄한 모습이 생성되었습니다. 은하수와 별들이 배경을 수놓고, 지구의 대기가 아름다운 푸른 테두리를 만듭니다."
        
        # 기본 응답 (모델별로 다르게)
        else:
            if "3.5-sonnet" in model:
                return "죄송합니다. 해당 질문에 대한 정확하고 상세한 답변을 제공하기 어려운 상황입니다. 더 구체적인 정보나 맥락을 제공해주시면 보다 도움이 되는 답변을 드릴 수 있을 것 같습니다."
            elif "3-sonnet" in model:
                return "죄송합니다. 해당 질문에 대한 정확한 답변을 드리기 어렵습니다. 관련 정보를 더 찾아보고 답변드리겠습니다."
            else:  # haiku
                return "죄송합니다. 정확한 답변이 어렵습니다."