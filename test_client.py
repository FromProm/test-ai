import requests
import json
import time

def test_prompt_evaluation():
    base_url = "http://localhost:8000"
    
    # 1. 처리 상태 확인
    try:
        status_response = requests.get(f"{base_url}/api/v1/jobs/status")
        status = status_response.json()
        print(f"📊 Current status: {status['message']}")
        
        if status['processing']:
            print("⚠️  Another job is processing. Please wait...")
            return
    except:
        print("⚠️  Could not check status, proceeding...")
    
    # 2. 테스트 데이터 로드
    with open('test_request.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("🚀 Creating job...")
    start_time = time.time()
    
    # 3. 작업 생성
    response = requests.post(f"{base_url}/api/v1/jobs", json=data)
    
    if response.status_code == 429:
        print("⚠️  Server is busy (429). Another job is processing.")
        return
    elif response.status_code != 200:
        print(f"❌ Failed to create job: {response.status_code}")
        print(response.text)
        return
    
    result = response.json()
    job_id = result.get('request_id')
    print(f"✅ Job created: {job_id}")
    
    # 4. 진행 상황 모니터링
    print("⏳ Monitoring progress...")
    last_status = None
    
    while True:
        time.sleep(10)  # 10초마다 확인
        
        try:
            # 상태 확인
            job_response = requests.get(f"{base_url}/api/v1/jobs/{job_id}")
            if job_response.status_code != 200:
                print(f"❌ Failed to get job status: {job_response.status_code}")
                break
                
            job = job_response.json()
            status = job.get('status')
            
            if status != last_status:
                print(f"📈 Status: {status}")
                last_status = status
            
            if status == 'completed':
                end_time = time.time()
                print(f"🎉 Job completed in {end_time - start_time:.1f} seconds!")
                
                # 결과 출력
                result = job.get('result', {})
                if result:
                    print(f"📊 Final score: {result.get('final_score', 'N/A')}")
                    
                    metrics = result.get('metrics', {})
                    if metrics:
                        print("📈 Metrics:")
                        for metric, data in metrics.items():
                            if isinstance(data, dict) and 'score' in data:
                                print(f"  - {metric}: {data['score']:.2f}")
                break
                
            elif status == 'failed':
                print(f"❌ Job failed: {job.get('error_message')}")
                break
                
        except Exception as e:
            print(f"❌ Error checking job status: {str(e)}")
            break

if __name__ == "__main__":
    test_prompt_evaluation()