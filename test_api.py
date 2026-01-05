import requests
import json
import time

def test_api():
    url = "http://localhost:8000/api/v1/jobs"
    
    payload = {
        "prompt": "다음 질문에 대해 정확한 사실과 근거를 바탕으로 답변해주세요: {{question}}",
        "example_inputs": [
            {
                "content": "OpenAI는 언제 GPT-4를 발표했나요?",
                "input_type": "text"
            },
            {
                "content": "2024년 노벨 물리학상 수상자는 누구인가요?",
                "input_type": "text"
            },
            {
                "content": "한국의 현재 대통령은 누구이며 언제 취임했나요?",
                "input_type": "text"
            }
        ],
        "prompt_type": "type_a",
        "recommended_model": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "repeat_count": 5
    }
    
    print("API 호출 시작...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    start_time = time.time()
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        end_time = time.time()
        
        print(f"\n응답 시간: {end_time - start_time:.2f}초")
        print(f"상태 코드: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ 성공!")
            print(f"Job ID: {result.get('id')}")
            print(f"Status: {result.get('status')}")
            
            # Job 상태 확인
            if result.get('status') == 'completed':
                print("\n📊 결과:")
                if 'result' in result:
                    res = result['result']
                    print(f"최종 점수: {res.get('final_score', 'N/A')}")
                    print(f"토큰 사용량: {res.get('token_usage', {}).get('score', 'N/A')}")
                    print(f"정보 밀도: {res.get('information_density', {}).get('score', 'N/A')}")
                    print(f"일관성: {res.get('consistency', {}).get('score', 'N/A')}")
                    print(f"정확도: {res.get('relevance', {}).get('score', 'N/A')}")
                    print(f"환각 탐지: {res.get('hallucination', {}).get('score', 'N/A')}")
                    print(f"버전별 일관성: {res.get('model_variance', {}).get('score', 'N/A')}")
                    
                    # 실제 출력 확인
                    if 'execution_results' in res:
                        print("\n🤖 실제 AI 출력:")
                        exec_results = res['execution_results']
                        if 'executions' in exec_results:
                            for i, exec_data in enumerate(exec_results['executions']):
                                print(f"\n입력 {i+1}: {exec_data.get('input_content', 'N/A')}")
                                print(f"모델: {exec_data.get('model', 'N/A')}")
                                outputs = exec_data.get('outputs', [])
                                for j, output in enumerate(outputs):
                                    print(f"  출력 {j+1}: {output[:200]}{'...' if len(output) > 200 else ''}")
            else:
                print(f"Job이 아직 완료되지 않았습니다. 상태: {result.get('status')}")
                
        else:
            print(f"\n❌ 실패!")
            print(f"응답: {response.text}")
            
    except requests.exceptions.Timeout:
        print("\n⏰ 타임아웃 발생 (120초)")
    except requests.exceptions.ConnectionError:
        print("\n🔌 연결 오류 - 서버가 실행 중인지 확인하세요")
    except Exception as e:
        print(f"\n💥 오류 발생: {str(e)}")

if __name__ == "__main__":
    test_api()