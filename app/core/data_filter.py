"""
데이터 필터링 - AI 출력 제거 및 개인정보 보호
"""
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class DataFilter:
    """AI 출력 및 민감 데이터 필터링"""
    
    @staticmethod
    def filter_execution_results(execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        실행 결과에서 AI 출력 제거
        - 프롬프트와 입력은 유지
        - AI 생성 출력은 제거
        - 토큰 사용량과 메타데이터는 유지
        """
        filtered_results = {
            'executions': []
        }
        
        for exec_data in execution_results.get('executions', []):
            filtered_exec = {
                'input_index': exec_data.get('input_index'),
                'input_content': exec_data.get('input_content'),
                'input_type': exec_data.get('input_type'),
                'model': exec_data.get('model'),
                'token_usage': exec_data.get('token_usage'),
                # AI 출력 제거
                'outputs_count': len(exec_data.get('outputs', [])),
                'outputs_removed': True,
                'removal_reason': 'Privacy and storage efficiency'
            }
            filtered_results['executions'].append(filtered_exec)
        
        logger.info(f"Filtered AI outputs from {len(execution_results.get('executions', []))} executions")
        return filtered_results
    
    @staticmethod
    def filter_embeddings(embeddings: Dict[str, Any]) -> Dict[str, Any]:
        """
        임베딩에서 원본 텍스트 제거
        - 벡터 차원 정보만 유지
        - 실제 임베딩 벡터는 제거
        """
        filtered_embeddings = {
            'inputs': [],
            'outputs': []
        }
        
        # 입력 임베딩 필터링
        for input_emb in embeddings.get('inputs', []):
            filtered_input = {
                'index': input_emb.get('index'),
                'type': input_emb.get('type'),
                'titan_embedding_dim': len(input_emb.get('titan_embedding', [])),
                'cohere_embedding_dim': len(input_emb.get('cohere_embedding', [])),
                'embeddings_removed': True
            }
            filtered_embeddings['inputs'].append(filtered_input)
        
        # 출력 임베딩 필터링
        for output_group in embeddings.get('outputs', []):
            filtered_group = {
                'input_index': output_group.get('input_index'),
                'embeddings_count': len(output_group.get('embeddings', [])),
                'embeddings_removed': True
            }
            filtered_embeddings['outputs'].append(filtered_group)
        
        return filtered_embeddings
    
    @staticmethod
    def should_store_ai_outputs() -> bool:
        """AI 출력 저장 여부 결정"""
        # 환경 변수나 설정으로 제어 가능
        return False  # 기본적으로 저장하지 않음