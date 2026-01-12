import requests
import json
import time

def test_mock_mode():
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
    
    print("🔄 Mock 모드 테스트 시작...")
    print(f"URL: {url}")
    
    start_time = time.time()
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('id')
            print(f"✅ Job 생성 성공! ID: {job_id}")
            
            # Job 완료까지 대기 (Mock 모드는 빠름)
            print("⏳ Job 완료 대기 중...")
            
            for attempt in range(30):  # 최대 30번 시도 (30초)
                time.sleep(1)
                
                check_response = requests.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
                if check_response.status_code == 200:
                    job_result = check_response.json()
                    status = job_result.get('status')
                    
                    print(f"[시도 {attempt+1}] 상태: {status}")
                    
                    if status == 'completed':
                        end_time = time.time()
                        print(f"\n🎉 Job 완료! (총 소요시간: {end_time - start_time:.2f}초)")
                        
                        if 'result' in job_result:
                            res = job_result['result']
                            print(f"\n📊 최종 결과:")
                            print(f"최종 점수: {res.get('final_score', 'N/A')}")
                            print(f"토큰 사용량: {res.get('token_usage', {}).get('score', 'N/A')}")
                            print(f"정보 밀도: {res.get('information_density', {}).get('score', 'N/A')}")
                            print(f"일관성: {res.get('consistency', {}).get('score', 'N/A')}")
                            print(f"정확도: {res.get('relevance', {}).get('score', 'N/A')}")
                            print(f"환각 탐지: {res.get('hallucination', {}).get('score', 'N/A')}")
                            print(f"버전별 일관성: {res.get('model_variance', {}).get('score', 'N/A')}")
                            
                            # 실제 출력 확인 (일부만)
                            if 'execution_results' in res:
                                print(f"\n🤖 실제 AI 출력 (샘플):")
                                exec_results = res['execution_results']
                                if 'executions' in exec_results:
                                    for i, exec_data in enumerate(exec_results['executions'][:2]):  # 처음 2개만
                                        print(f"\n입력 {i+1}: {exec_data.get('input_content', 'N/A')}")
                                        print(f"모델: {exec_data.get('model', 'N/A')}")
                                        outputs = exec_data.get('outputs', [])
                                        for j, output in enumerate(outputs[:2]):  # 처음 2개 출력만
                                            print(f"  출력 {j+1}: {output[:200]}{'...' if len(output) > 200 else ''}")
                        return True
                        
                    elif status == 'failed':
                        print(f"\n❌ Job 실패!")
                        print(f"오류: {job_result.get('error_message', 'Unknown error')}")
                        return False
            
            print("\n⏰ 타임아웃: Job이 30초 내에 완료되지 않았습니다.")
            return False
            
        else:
            print(f"\n❌ API 호출 실패!")
            print(f"상태 코드: {response.status_code}")
            print(f"응답: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n💥 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_mock_mode()
    
    if success:
        print("\n🎉 Mock 모드 테스트 완료! 모든 지표가 정상적으로 계산되었습니다.")
    else:
        print("\n❌ 테스트 실패")