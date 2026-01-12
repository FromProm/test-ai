from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseRunner(ABC):
    """Runner 기본 인터페이스"""
    
    @abstractmethod
    async def invoke(
        self, 
        model: str, 
        prompt: str, 
        input_type: str = "text",
        **kwargs
    ) -> Dict[str, Any]:
        """
        모델 호출
        
        Returns:
            {
                'output': str,
                'token_usage': {
                    'input_tokens': int,
                    'output_tokens': int,
                    'total_tokens': int
                }
            }
        """
        pass