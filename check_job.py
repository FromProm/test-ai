import requests
import json
import time

def check_job_status(job_id):
    url = f"http://localhost:8000/api/v1/jobs/{job_id}"
    
    while True:
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                
                print(f"[{time.strftime('%H:%M:%S')}] Job 상태: {status}")
                
                if status == 'completed':
                    print("\n🎉 Job 완료!")
                    
                    if 'result' in result:
                        res = result['result']
                        print(f"\n📊 최종 결과:")
                        print(f"최종 점수: {res.get('final_score', 'N/A')}")
                        print(f"토큰 사용량: {res.get('token_usage', {}).get('score', 'N/A')}")
                        print(f"정보 밀도: {res.get('information_density', {}).get('score', 'N/A')}")
                        print(f"일관성: {res.get('consistency', {}).get('score', 'N/A')}")
                        print(f"정확도: {res.get('relevance', {}).get('score', 'N/A')}")
                        print(f"환각 탐지: {res.get('hallucination', {}).get('score', 'N/A')}")
                        print(f"버전별 일관성: {res.get('model_variance', {}).get('score', 'N/A')}")
                        
                        # 실제 출력 확인
                        if 'execution_results' in res:
                            print(f"\n🤖 실제 AI 출력:")
                            exec_results = res['execution_results']
                            if 'executions' in exec_results:
                                for i, exec_data in enumerate(exec_results['executions']):
                                    print(f"\n입력 {i+1}: {exec_data.get('input_content', 'N/A')}")
                                    print(f"모델: {exec_data.get('model', 'N/A')}")
                                    outputs = exec_data.get('outputs', [])
                                    for j, output in enumerate(outputs):
                                        print(f"  출력 {j+1}: {output[:300]}{'...' if len(output) > 300 else ''}")
                    break
                    
                elif status == 'failed':
                    print(f"\n❌ Job 실패!")
                    print(f"오류: {result.get('error_message', 'Unknown error')}")
                    break
                    
                elif status in ['pending', 'running']:
                    print("   계속 진행 중...")
                    time.sleep(10)  # 10초마다 확인
                    
            else:
                print(f"API 오류: {response.status_code}")
                break
                
        except Exception as e:
            print(f"오류 발생: {str(e)}")
            time.sleep(5)

if __name__ == "__main__":
    job_id = "481ea0a5-562f-47f9-afc4-c619b84212fe"  # 위에서 생성된 Job ID
    check_job_status(job_id)