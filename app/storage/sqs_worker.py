import json
import os
import time
import traceback
import asyncio
from datetime import datetime
from pathlib import Path
import boto3

# .env 파일 직접 파싱 (dotenv 문제 우회)
def load_env_file():
    env_path = Path.cwd() / '.env'
    if not env_path.exists():
        env_path = Path(__file__).parent.parent.parent / '.env'
    
    if env_path.exists():
        print(f"[init] .env 파일 발견: {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        print(f"[init] .env 로드 완료")
    else:
        print(f"[init] .env 파일 없음")

load_env_file()

# 환경변수 읽기
AWS_REGION_SQS_DDB = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")  # SQS/DynamoDB용
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # 기본 AWS 리전
QUEUE_URL = os.getenv("SQS_QUEUE_URL")
DDB_TABLE = os.getenv("DDB_TABLE_NAME", "FromProm_Table")

print(f"[init] AWS_REGION (Bedrock): {AWS_REGION}")
print(f"[init] AWS_REGION_SQS_DDB: {AWS_REGION_SQS_DDB}")
print(f"[init] SQS_QUEUE_URL: {QUEUE_URL}")

# 이제 다른 모듈 import
from app.storage.fromprom_repo import save_prompt_record, save_error_record, upload_outputs_to_s3, update_status_processing
from app.core.schemas import JobCreateRequest, ExampleInput, PromptType, RecommendedModel
from app.orchestrator.pipeline import Orchestrator
from app.orchestrator.context import ExecutionContext

sqs = boto3.client(
    "sqs", 
    region_name=AWS_REGION_SQS_DDB,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)


def log(msg: str):
    """타임스탬프 포함 로그 출력"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def fix_json_format(body: str) -> str:
    """일반적인 JSON 형식 오류를 수정"""
    try:
        # 1. "final_score": "" "feedback" 패턴 수정 (쉼표 누락)
        import re
        body = re.sub(r'("final_score"\s*:\s*"[^"]*")\s*("feedback")', r'\1,\n    \2', body)
        
        # 2. 기타 일반적인 패턴들도 추가 가능
        # body = re.sub(r'(")\s*(")', r'\1,\n    \2', body)  # 연속된 문자열 사이 쉼표 추가
        
        return body
    except Exception:
        return body

def parse_payload(body: str) -> dict:
    try:
        data = json.loads(body)
        # SNS->SQS Raw delivery OFF면 envelope일 수 있음
        if isinstance(data, dict) and "Message" in data and isinstance(data["Message"], str):
            try:
                return json.loads(data["Message"])
            except json.JSONDecodeError as e:
                print(f"SNS Message JSON 파싱 실패: {e}")
                return {"pk": data["Message"]}
        return data
    except json.JSONDecodeError as e:
        print(f"SQS Body JSON 파싱 실패: {e}")
        print(f"Raw Body (처음 500자): {body[:500]}")
        
        # JSON 수정 시도
        try:
            print("JSON 형식 수정 시도...")
            fixed_body = fix_json_format(body)
            data = json.loads(fixed_body)
            print("✅ JSON 수정 성공!")
            return data
        except json.JSONDecodeError as e2:
            print(f"JSON 수정 실패: {e2}")
        
        # JSON 파싱 실패해도 PK 추출 시도
        try:
            import re
            pk_match = re.search(r'"PK"\s*:\s*"([^"]+)"', body)
            if pk_match:
                pk = pk_match.group(1)
                print(f"JSON 파싱 실패했지만 PK 추출 성공: {pk}")
                return {"PK": pk, "_json_parse_failed": True, "_raw_body": body}
        except Exception:
            pass
        
        # PK도 추출 못하면 빈 dict 반환
        return {}

def build_job_request_from_sqs(payload: dict) -> JobCreateRequest:
    """SQS 메시지(DynamoDB 구조) → JobCreateRequest 변환"""
    
    def parse_examples():
        """examples 필드에서 ExampleInput 리스트 추출 (DynamoDB 구조)"""
        ex = payload.get("examples", [])
        inputs = []
        for e in ex:  # 모든 예시 사용 (개수 제한 없음)
            inp = e.get("input", {})
            content = inp.get("content", "")
            input_type = inp.get("input_type", "text")
            inputs.append(ExampleInput(content=content, input_type=input_type))
        return inputs

    # prompt_type 변환
    prompt_type_str = payload.get("prompt_type") or "type_a"
    prompt_type = PromptType(prompt_type_str)

    # recommended_model 변환 (model 필드에서)
    recommended_model = None
    model_str = payload.get("model", "").strip()  # 빈 문자열 처리
    if model_str:
        try:
            recommended_model = RecommendedModel(model_str)
            log(f"  → 모델 설정 성공: {model_str}")
        except ValueError:
            log(f"  → 유효하지 않은 모델: {model_str}, 기본 모델 사용")
            pass  # 유효하지 않은 모델은 None으로
    else:
        log(f"  → 모델 필드가 비어있음, 기본 모델 사용")
    
    # 모델이 없으면 prompt_type에 따라 기본 모델 설정
    if not recommended_model:
        if prompt_type == PromptType.TYPE_A:
            recommended_model = RecommendedModel.CLAUDE_SONNET_4_5
        elif prompt_type == PromptType.TYPE_B_TEXT:
            recommended_model = RecommendedModel.CLAUDE_3_HAIKU
        elif prompt_type == PromptType.TYPE_B_IMAGE:
            recommended_model = RecommendedModel.NOVA_CANVAS
        log(f"  → 기본 모델 설정: {recommended_model.value if recommended_model else 'None'}")

    return JobCreateRequest(
        prompt=payload.get("prompt_content") or payload.get("content") or "",  # 두 필드 모두 확인
        example_inputs=parse_examples(),
        prompt_type=prompt_type,
        recommended_model=recommended_model,
        repeat_count=2,  # 5 → 2로 줄임 (테스트용)
        title=payload.get("title"),
        description=payload.get("prompt_description"),
        user_id=payload.get("create_user")
    )

async def process_message(pk: str, payload: dict) -> dict:
    """단일 메시지 처리 (async) - examples의 output도 채움"""
    try:
        # 1) JobCreateRequest 생성 (SQS 메시지에서 직접)
        log(f"  → JobCreateRequest 생성 시작...")
        job_request = build_job_request_from_sqs(payload)
        log(f"  → JobCreateRequest 생성 완료")
        log(f"     prompt: {job_request.prompt[:50]}..." if len(job_request.prompt) > 50 else f"     prompt: {job_request.prompt}")
        log(f"     prompt_type: {job_request.prompt_type}")
        log(f"     recommended_model: {job_request.recommended_model}")
        log(f"     examples: {len(job_request.example_inputs)}개")
        
        # 2) ExecutionContext 생성 및 파이프라인 실행
        log(f"  → ExecutionContext 생성...")
        context = ExecutionContext()
        log(f"  → Orchestrator 생성...")
        orchestrator = Orchestrator(context)
        log(f"  → 파이프라인 실행 시작...")
        result = await orchestrator.run(job_request)
        log(f"  → 파이프라인 실행 완료")
        
    except Exception as e:
        log(f"  ❌ 파이프라인 실행 중 에러 발생!")
        log(f"     에러 타입: {type(e).__name__}")
        log(f"     에러 메시지: {str(e)}")
        import traceback
        log(f"     스택 트레이스:")
        for line in traceback.format_exc().split('\n'):
            if line.strip():
                log(f"       {line}")
        raise  # 에러를 다시 발생시켜서 상위에서 처리
    
    # 3) 결과를 dict로 변환
    metrics = {
        "token_usage": result.token_usage.score if result.token_usage else 0,
        "information_density": result.information_density.score if result.information_density else 0,
        "consistency": result.consistency.score if result.consistency else 0,
        "model_variance": result.model_variance.score if result.model_variance else 0,
        "hallucination": result.hallucination.score if result.hallucination else 0,
        "relevance": result.relevance.score if result.relevance else 0,
        "final_score": 0,  # 추후 계산
        "feedback": result.feedback if hasattr(result, 'feedback') and result.feedback else {},
    }
    
    # 4) examples의 output 필드 채우기 + 실제 사용된 모델 저장
    execution_results = result.execution_results if hasattr(result, 'execution_results') else {}
    executions = execution_results.get('executions', [])
    
    # 실제 사용된 모델 추출 (첫 번째 실행에서)
    used_model = ""
    if executions and len(executions) > 0:
        used_model = executions[0].get('model', job_request.recommended_model.value if job_request.recommended_model else "")
    
    # payload의 examples 업데이트 (output 필드 채우기)
    examples = payload.get("examples", [])
    for i, example in enumerate(examples):
        if i < len(executions) and executions[i].get('outputs'):
            # 첫 번째 출력을 사용
            example["output"] = executions[i]['outputs'][0] if executions[i]['outputs'] else ""
        else:
            example["output"] = ""
    
    # payload의 model 필드 업데이트 (실제 사용된 모델)
    payload["model"] = used_model
    
    log(f"  → 평가 결과: {metrics}")
    log(f"  → examples output 채움 완료")
    log(f"  → 사용된 모델: {used_model}")
    
    return metrics, execution_results


def main():
    # 환경변수 체크
    log("=" * 50)
    log("SQS Worker 시작")
    log("=" * 50)
    log(f"AWS_REGION: {AWS_REGION}")
    log(f"SQS_QUEUE_URL: {QUEUE_URL}")
    
    if not QUEUE_URL:
        log("ERROR: SQS_QUEUE_URL 환경변수가 설정되지 않았습니다!")
        log(".env 파일에 SQS_QUEUE_URL을 설정해주세요.")
        return  # raise 대신 return으로 변경
    
    log("SQS 폴링 시작... (Ctrl+C로 종료)")
    log("-" * 50)

    poll_count = 0
    while True:
        poll_count += 1
        
        try:
            resp = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                VisibilityTimeout=60,
            )
        except Exception as e:
            log(f"SQS 연결 에러: {e}")
            time.sleep(5)
            continue

        msgs = resp.get("Messages", [])
        if not msgs:
            # 대기 중 표시 (점이 늘어남)
            dots = "." * ((poll_count % 10) + 1)
            print(f"\r[대기 중] SQS 메시지 대기{dots}        ", end="", flush=True)
            continue
        
        print()  # 줄바꿈 (대기 표시 끝)

        msg = msgs[0]
        receipt = msg["ReceiptHandle"]

        pk = None
        try:
            log("=" * 50)
            log("새 메시지 수신!")
            log(f"Raw Body: {msg['Body'][:200]}..." if len(msg['Body']) > 200 else f"Raw Body: {msg['Body']}")
            
            try:
                payload = parse_payload(msg["Body"])
                log(f"Parsed Payload: {payload}")
            except Exception as parse_error:
                log(f"ERROR: JSON 파싱 실패: {parse_error}")
                log(f"Raw Body 전체: {msg['Body']}")
                
                # JSON 파싱 실패도 에러로 기록
                try:
                    # 최소한의 payload 생성 (PK가 없으면 임시 PK 생성)
                    error_payload = {
                        "PK": f"ERROR#{int(time.time())}",
                        "SK": "METADATA",
                        "type": "PROMPT",
                        "title": "JSON 파싱 실패",
                        "prompt_content": "",
                        "prompt_description": "SQS 메시지 JSON 파싱 중 오류 발생",
                        "prompt_type": "type_a",
                        "examples": [],
                        "model": "",
                        "create_user": "SYSTEM",
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    save_error_record(error_payload, f"JSON 파싱 실패: {parse_error}")
                    log(f"  → DynamoDB에 JSON 파싱 에러 기록됨")
                except Exception as e2:
                    log(f"  → DynamoDB 에러 저장 실패: {e2}")
                
                # 메시지 삭제 (재처리 방지)
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
                continue
            
            # PK 추출 (대문자 PK 또는 소문자 pk)
            pk = payload.get("PK") or payload.get("pk")
            
            # JSON 파싱 실패한 경우 특별 처리
            if payload.get("_json_parse_failed"):
                log(f"JSON 파싱 실패 메시지 처리: PK={pk}")
                try:
                    error_payload = {
                        "PK": pk or f"JSON_ERROR#{int(time.time())}",
                        "SK": "METADATA",
                        "type": "PROMPT",
                        "title": "JSON 파싱 실패",
                        "content": "",
                        "prompt_description": "SQS 메시지 JSON 파싱 중 오류 발생",
                        "prompt_type": "type_a",
                        "examples": [],
                        "model": "",
                        "create_user": "SYSTEM",
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "PROMPT_INDEX_PK": "ERROR_PROMPT_LIST",
                        "PROMPT_INDEX_SK": f"JSON_ERROR#{int(time.time())}"
                    }
                    raw_body = payload.get("_raw_body", "")
                    save_error_record(error_payload, f"JSON 파싱 실패. Raw Body: {raw_body[:1000]}")
                    log(f"  → DynamoDB에 JSON 파싱 에러 기록됨")
                except Exception as e2:
                    log(f"  → DynamoDB 에러 저장 실패: {e2}")
                
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
                continue
            
            if not pk:
                log("ERROR: payload에 'PK' 필드가 없습니다!")
                
                # PK 없음도 에러로 기록
                try:
                    error_payload = {
                        "PK": f"ERROR#{int(time.time())}",
                        "SK": "METADATA",
                        "type": "PROMPT",
                        "title": "PK 필드 누락",
                        "prompt_content": "",
                        "prompt_description": "SQS 메시지에 PK 필드가 없음",
                        "prompt_type": "type_a",
                        "examples": [],
                        "model": "",
                        "create_user": "SYSTEM",
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    save_error_record(error_payload, "SQS 메시지에 PK 필드가 없습니다")
                    log(f"  → DynamoDB에 PK 누락 에러 기록됨")
                except Exception as e2:
                    log(f"  → DynamoDB 에러 저장 실패: {e2}")
                
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
                continue
            
            log(f"Processing PK: {pk}")

            # 1. 처리 시작 - status를 PROCESSING으로 업데이트
            log(f"  → Status를 PROCESSING으로 업데이트...")
            try:
                update_status_processing(pk)
                log(f"  → Status 업데이트 완료")
            except Exception as e:
                log(f"  → Status 업데이트 실패: {e}")
                # 계속 진행 (치명적이지 않음)

            # 2. SQS 메시지에 전체 데이터가 있으므로 DynamoDB 조회 불필요
            # 바로 파이프라인 실행
            metrics, execution_results = asyncio.run(process_message(pk, payload))

            # 3. S3에 출력 결과 업로드
            log(f"  → S3에 출력 결과 업로드 중...")
            prompt_type_str = payload.get("prompt_type", "type_a")
            s3_url = upload_outputs_to_s3(pk, execution_results, prompt_type_str)
            if s3_url:
                log(f"  → S3 업로드 완료: {s3_url}")
            else:
                log(f"  → S3 업로드 실패")

            # 4. COMPLETED 저장 (전체 레코드)
            log(f"  → DynamoDB 전체 레코드 저장 중...")
            save_prompt_record(payload, evaluation_metrics=metrics, outputs_s3_url=s3_url)
            log(f"  → DynamoDB 저장 완료 (Status: COMPLETED)")

            # 성공 → 메시지 삭제
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
            log(f"✅ 완료: {pk}")
            log("=" * 50)

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log(f"❌ 에러 발생: {err}")
            traceback.print_exc()

            if pk and payload:
                try:
                    save_error_record(payload, err)
                    log(f"  → DynamoDB에 에러 상태 저장됨")
                except Exception as e2:
                    log(f"  → DynamoDB 에러 저장 실패: {e2}")

            log("=" * 50)
            time.sleep(1)


if __name__ == "__main__":
    main()
