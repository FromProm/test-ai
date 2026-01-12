#!/usr/bin/env python3
"""
키워드 추출 기반 캐시 테스트 스크립트
"""
import sys
import os
import hashlib
import re
from typing import List

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def extract_keywords(claim: str) -> List[str]:
    """Claim에서 핵심 키워드 추출"""
    # 1. 숫자 (연도, 금액, 수량 등)
    numbers = re.findall(r'\d+(?:[.,]\d+)*(?:조|억|만|천|원|달러|%|년|월|일|개|명|대)?', claim)
    
    # 2. 고유명사 (회사명, 인명, 지명 등) - 대문자로 시작하거나 한글 2글자 이상
    proper_nouns = re.findall(r'[A-Z][a-zA-Z]+|[가-힣]{2,}(?:전자|그룹|회사|기업|대학|병원|은행|카드|생명|화학|건설|통신|시스템|테크|랩스?)', claim)
    
    # 3. 핵심 동사/명사 (사실 관련)
    key_terms = []
    fact_keywords = [
        '설립', '창립', '출시', '발표', '발매', '개발', '인수', '합병', '상장',
        '매출', '수익', '손실', '투자', '자금', '펀딩', '계약', '협약',
        'CEO', '대표', '회장', '사장', '임원', '직원', '근무',
        '본사', '지사', '공장', '연구소', '센터',
        '제품', '서비스', '기술', '특허', '브랜드'
    ]
    
    for keyword in fact_keywords:
        if keyword in claim:
            key_terms.append(keyword)
    
    # 4. 영어 단어 (브랜드명, 제품명 등)
    english_words = re.findall(r'[A-Za-z]{2,}', claim)
    # 일반적인 영어 단어 제외
    common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    english_words = [word for word in english_words if word.lower() not in common_words]
    
    # 5. 모든 키워드 합치기
    all_keywords = numbers + proper_nouns + key_terms + english_words
    
    # 6. 중복 제거 및 정리
    unique_keywords = []
    seen = set()
    
    for keyword in all_keywords:
        keyword = keyword.strip()
        if keyword and len(keyword) >= 2 and keyword not in seen:
            unique_keywords.append(keyword)
            seen.add(keyword)
    
    # 7. 최대 10개 키워드만 사용 (성능 고려)
    return unique_keywords[:10]

def hash_claim(claim: str) -> str:
    """Claim을 키워드 기반으로 해시 생성"""
    keywords = extract_keywords(claim)
    if not keywords:
        # 키워드가 없으면 원본 텍스트 해시 사용
        return hashlib.sha256(claim.encode('utf-8')).hexdigest()
    
    # 키워드를 정렬해서 순서에 상관없이 같은 해시 생성
    keywords_str = "_".join(sorted(keywords))
    return hashlib.sha256(keywords_str.encode('utf-8')).hexdigest()

def test_keyword_extraction():
    """키워드 추출 테스트"""
    
    print("="*80)
    print("키워드 추출 기반 캐시 매칭 테스트")
    print("="*80)
    
    # 테스트 케이스들
    test_cases = [
        # 같은 의미, 다른 표현
        [
            "삼성전자는 2023년에 300조원의 매출을 기록했습니다",
            "삼성전자가 2023년 300조원 매출을 달성했다",
            "2023년 삼성전자 매출 300조원 기록"
        ],
        # 애플 관련
        [
            "애플은 2007년에 첫 번째 아이폰을 출시했습니다",
            "Apple이 2007년 아이폰을 발표했다",
            "2007년 애플 아이폰 출시"
        ],
        # 구글 관련
        [
            "구글은 1998년에 래리 페이지와 세르게이 브린에 의해 설립되었습니다",
            "Google이 1998년 설립되었다",
            "1998년 구글 창립"
        ]
    ]
    
    for i, case_group in enumerate(test_cases, 1):
        print(f"\n테스트 케이스 {i}:")
        print("-" * 50)
        
        hashes = []
        for claim in case_group:
            keywords = extract_keywords(claim)
            claim_hash = hash_claim(claim)
            
            print(f"원문: {claim}")
            print(f"키워드: {keywords}")
            print(f"해시: {claim_hash[:16]}...")
            print()
            
            hashes.append(claim_hash)
        
        # 해시 비교
        if len(set(hashes)) == 1:
            print("✅ 캐시 매칭 성공! (모든 해시가 동일)")
        else:
            print("❌ 캐시 매칭 실패 (해시가 다름)")
            for j, h in enumerate(hashes):
                print(f"  해시 {j+1}: {h[:16]}...")
        
        print("=" * 50)
    
    # 추가 테스트: 완전히 다른 내용
    print(f"\n다른 내용 테스트:")
    print("-" * 50)
    
    different_claims = [
        "삼성전자는 2023년에 300조원의 매출을 기록했습니다",
        "마이크로소프트는 1975년에 설립되었습니다"
    ]
    
    different_hashes = []
    for claim in different_claims:
        keywords = extract_keywords(claim)
        claim_hash = hash_claim(claim)
        
        print(f"원문: {claim}")
        print(f"키워드: {keywords}")
        print(f"해시: {claim_hash[:16]}...")
        print()
        
        different_hashes.append(claim_hash)
    
    if len(set(different_hashes)) == len(different_hashes):
        print("✅ 다른 내용은 다른 해시 생성 (정상)")
    else:
        print("❌ 다른 내용인데 같은 해시 생성 (문제)")

if __name__ == "__main__":
    test_keyword_extraction()