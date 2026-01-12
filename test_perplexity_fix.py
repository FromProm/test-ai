#!/usr/bin/env python3
"""
Test script to verify Perplexity API connection with correct model name
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.adapters.fact_checker.perplexity_client import PerplexityClient

async def test_perplexity_connection():
    """Test Perplexity API connection and fact-checking"""
    print("Testing Perplexity API connection...")
    
    client = PerplexityClient()
    
    # Test basic connection
    print(f"Using model: {client.model}")
    print(f"API key configured: {'Yes' if client.api_key else 'No'}")
    
    # Test simple fact-checking
    test_claims = [
        "The sky is blue.",
        "Python was created by Guido van Rossum.",
        "The Earth is flat.",
        "Microsoft was founded in 1975."
    ]
    
    print("\nTesting individual claims:")
    for claim in test_claims:
        try:
            score = await client.verify_claim(claim)
            print(f"✓ '{claim}' -> Score: {score:.1f}")
        except Exception as e:
            print(f"✗ '{claim}' -> Error: {str(e)}")
    
    # Test batch processing
    print("\nTesting batch processing:")
    try:
        scores = await client.verify_claims_batch(test_claims)
        print(f"✓ Batch scores: {[f'{s:.1f}' for s in scores]}")
    except Exception as e:
        print(f"✗ Batch processing failed: {str(e)}")
    
    # Test health check
    print("\nTesting health check:")
    try:
        is_healthy = await client.health_check()
        print(f"✓ Health check: {'PASS' if is_healthy else 'FAIL'}")
    except Exception as e:
        print(f"✗ Health check failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_perplexity_connection())