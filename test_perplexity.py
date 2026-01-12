import asyncio
import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.adapters.fact_checker import PerplexityClient

async def test_perplexity():
    """Perplexity 클라이언트 테스트"""
    print("🧪 Testing Perplexity Client...")
    
    client = PerplexityClient()
    
    # 1. Health check
    print("1. Health check...")
    is_healthy = await client.health_check()
    print(f"   Health status: {'✅ OK' if is_healthy else '❌ Failed'}")
    
    if not is_healthy:
        print("❌ Perplexity client is not working. Check your API key.")
        return
    
    # 2. Single claim test
    print("\n2. Single claim verification...")
    test_claims = [
        "The sky is blue",
        "Python was created by Guido van Rossum",
        "The Earth is flat",
        "발표일: 2023년 7월 3일",
        "저자: Microsoft Research"
    ]
    
    for claim in test_claims:
        score = await client.verify_claim(claim)
        print(f"   '{claim}' -> {score:.1f}/100")
    
    # 3. Batch verification test
    print("\n3. Batch verification...")
    batch_scores = await client.verify_claims_batch(test_claims)
    
    print("   Batch results:")
    for claim, score in zip(test_claims, batch_scores):
        print(f"   '{claim}' -> {score:.1f}/100")
    
    print("\n🎉 Perplexity test completed!")

if __name__ == "__main__":
    asyncio.run(test_perplexity())