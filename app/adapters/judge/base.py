from abc import ABC, abstractmethod

class BaseJudge(ABC):
    """Judge 기본 인터페이스"""
    
    @abstractmethod
    async def judge_factuality(self, question: str, answer: str) -> bool:
        """
        사실성 판별
        
        Returns:
            True: 사실적/근거 있음
            False: 환각/근거 없음
        """
        pass
    
    @abstractmethod
    async def analyze_text(self, prompt: str) -> str:
        """
        텍스트 분석용 범용 메서드
        
        Args:
            prompt: 분석 요청 프롬프트
            
        Returns:
            분석 결과 텍스트
        """
        pass