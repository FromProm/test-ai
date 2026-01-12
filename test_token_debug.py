#!/usr/bin/env python3

import tiktoken
import re

def _remove_placeholders(prompt: str) -> str:
    """플레이스홀더 제거 - run_stage의 _fill_prompt와 동일한 패턴 사용"""
    
    # 1. {{key}} 형태의 플레이스홀더 제거
    result = re.sub(r'\{\{[^}]*\}\}', '', prompt)
    
    # 2. 연속된 공백과 줄바꿈 정리
    result = re.sub(r'\n\s*\n', '\n', result)  # 빈 줄 제거
    result = re.sub(r'\s+', ' ', result)  # 연속 공백을 하나로
    
    return result.strip()

# 테스트 프롬프트
test_prompt = "주어진 연구 주제에 대해 최신 학술 동향과 주요 연구 결과를 정리해줘. 인용 가능한 논문명과 저자, 발표 연도를 포함해서 설명해줘."

# 토크나이저
tokenizer = tiktoken.get_encoding("cl100k_base")

# 계산
fixed_prompt = _remove_placeholders(test_prompt)
token_count = len(tokenizer.encode(fixed_prompt))

print(f"원본 프롬프트: {test_prompt}")
print(f"플레이스홀더 제거 후: {fixed_prompt}")
print(f"토큰 수: {token_count}")

# 플레이스홀더가 있는 경우도 테스트
test_prompt_with_placeholder = "주어진 연구 주제에 대해 최신 학술 동향과 주요 연구 결과를 정리해줘. {{input}}에 대해 인용 가능한 논문명과 저자, 발표 연도를 포함해서 설명해줘."

fixed_prompt2 = _remove_placeholders(test_prompt_with_placeholder)
token_count2 = len(tokenizer.encode(fixed_prompt2))

print(f"\n플레이스홀더 있는 프롬프트: {test_prompt_with_placeholder}")
print(f"플레이스홀더 제거 후: {fixed_prompt2}")
print(f"토큰 수: {token_count2}")