import os
import time
import json
import base64
from pathlib import Path
import boto3

# .env 파일 직접 파싱
def _load_env():
    possible_paths = [
        Path.cwd() / '.env',
        Path(__file__).parent.parent.parent / '.env',
    ]
    for env_path in possible_paths:
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = value.strip()
            break

_load_env()

# 리전 설정 분리
AWS_REGION_SQS_DDB = os.getenv("AWS_REGION_SQS_DDB", "ap-northeast-2")  # SQS/DynamoDB용
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # 기본 AWS 리전
TABLE = os.getenv("DDB_TABLE_NAME", "FromProm_Table")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "fromprom_s3")

ddb = boto3.client(
    "dynamodb", 
    region_name=AWS_REGION_SQS_DDB,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)
s3 = boto3.client(
    "s3", 
    region_name=AWS_REGION_SQS_DDB,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

def get_safe_prompt_index_sk(payload: dict) -> str:
    """PROMPT_INDEX_SK 값을 안전하게 반환 (빈 문자열 방지)"""
    value = payload.get("PROMPT_INDEX_SK", "")
    if not value or value.strip() == "":
        # 빈 문자열이면 기본값 생성
        return f"DEFAULT#{int(time.time())}"
    return value

def upload_outputs_to_s3(pk: str, execution_results: dict, prompt_type: str = "type_a") -> str:
    """
    실행 결과를 S3에 체계적인 구조로 업로드하고 URL 반환
    
    구조:
    s3://bucket/prompts/{pk}/
    ├── examples.json
    └── images/
        ├── output_0.png
        ├── output_1.png
        └── output_2.png
    """
    try:
        # 기본 경로 설정
        base_path = f"prompts/{pk.replace('PROMPT#', '')}"
        
        # 1. examples.json 업로드 (모든 타입)
        examples_data = {
            "prompt_id": pk,
            "execution_results": execution_results,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
        examples_key = f"{base_path}/examples.json"
        examples_json = json.dumps(examples_data, ensure_ascii=False, indent=2)
        
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=examples_key,
            Body=examples_json.encode('utf-8'),
            ContentType='application/json'
        )
        
        # 2. 이미지 파일 업로드 (type_b_image인 경우)
        if prompt_type == "type_b_image":
            executions = execution_results.get('executions', [])
            
            for i, execution in enumerate(executions):
                outputs = execution.get('outputs', [])
                if outputs and len(outputs) > 0:
                    # 첫 번째 출력에서 로컬 파일 경로 추출
                    first_output = outputs[0]
                    if isinstance(first_output, str) and "Generated 1 image(s):" in first_output:
                        try:
                            # 파일 경로 추출 (예: "Generated 1 image(s): outputs/images\\nova_canvas_20260108_193722_1.png")
                            file_path = first_output.split(": ", 1)[1].strip()
                            
                            # 로컬 파일 읽기
                            if os.path.exists(file_path):
                                with open(file_path, 'rb') as f:
                                    image_data = f.read()
                                
                                # S3에 업로드 (output_0.png, output_1.png, output_2.png 형식)
                                image_key = f"{base_path}/images/output_{i}.png"
                                s3.put_object(
                                    Bucket=S3_BUCKET,
                                    Key=image_key,
                                    Body=image_data,
                                    ContentType='image/png'
                                )
                                print(f"✅ 이미지 업로드 완료: {image_key}")
                            else:
                                print(f"❌ 로컬 이미지 파일 없음: {file_path}")
                                
                        except Exception as e:
                            print(f"❌ 이미지 {i} 업로드 실패: {e}")
        
        # 기본 S3 URL 반환 (examples.json)
        s3_url = f"s3://{S3_BUCKET}/{examples_key}"
        return s3_url
        
    except Exception as e:
        print(f"S3 업로드 실패: {e}")
        return ""


def update_status_processing(pk: str):
    """처리 시작 시 status를 PROCESSING으로 업데이트"""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ddb.update_item(
        TableName=TABLE,
        Key={"PK": {"S": pk}, "SK": {"S": "METADATA"}},
        UpdateExpression="SET #s=:s, updated_at=:u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": {"S": "processing"},  # 소문자로 변경
            ":u": {"S": now},
        },
    )


def get_prompt_metadata(pk: str) -> dict:
    """PK + SK=METADATA 단건 조회"""
    resp = ddb.get_item(
        TableName=TABLE,
        Key={
            "PK": {"S": pk},
            "SK": {"S": "METADATA"},
        },
        ConsistentRead=True,  # 개발/디버깅에 유리
    )
    item = resp.get("Item")
    if not item:
        raise KeyError(f"Item not found: PK={pk}, SK=METADATA")
    return item

def save_prompt_record(payload: dict, evaluation_metrics: dict, outputs_s3_url: str | None = None):
    """SQS payload + 평가 결과를 DynamoDB에 전체 저장 (DynamoDB 구조에 맞춤)"""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # examples를 DynamoDB 형식으로 변환 (output 포함)
    examples_ddb = []
    for ex in payload.get("examples", []):
        examples_ddb.append({
            "M": {
                "index": {"N": str(ex.get("index", 0))},
                "input": {"M": {
                    "content": {"S": ex.get("input", {}).get("content", "")},
                    "input_type": {"S": ex.get("input", {}).get("input_type", "text")}
                }},
                "output": {"S": ex.get("output", "")}  # 우리가 채운 output
            }
        })
    
    # evaluation_metrics를 DynamoDB 형식으로 변환
    metrics_ddb = {}
    for k, v in evaluation_metrics.items():
        if v is None or v == "":
            metrics_ddb[k] = {"S": ""}
        elif isinstance(v, (int, float)):
            metrics_ddb[k] = {"N": str(v)}
        elif isinstance(v, dict):
            metrics_ddb[k] = {"S": json.dumps(v, ensure_ascii=False)}
        else:
            metrics_ddb[k] = {"S": str(v)}
    
    # DynamoDB 구조에 맞춘 item 생성
    item = {
        "PK": {"S": payload.get("PK", "")},
        "SK": {"S": payload.get("SK", "METADATA")},
        "PROMPT_INDEX_PK": {"S": payload.get("PROMPT_INDEX_PK", "USER_PROMPT_LIST")},
        "PROMPT_INDEX_SK": {"S": get_safe_prompt_index_sk(payload)},
        "type": {"S": payload.get("type", "PROMPT")},
        "create_user": {"S": payload.get("create_user", "")},
        "title": {"S": payload.get("title", "")},
        "content": {"S": payload.get("content", "")},  # 실제 SQS 메시지는 content 필드 사용
        "prompt_description": {"S": payload.get("prompt_description", "")},
        "price": {"N": str(payload.get("price", 0) or 0)},  # price 필드 추가
        "prompt_type": {"S": payload.get("prompt_type", "type_a")},
        "examples": {"L": examples_ddb},
        "examples_s3_url": {"S": outputs_s3_url or payload.get("examples_s3_url", "")},
        "model": {"S": payload.get("model", "")},
        "evaluation_metrics": {"M": metrics_ddb},
        "status": {"S": "completed"},  # 소문자로 변경
        "created_at": {"S": payload.get("created_at") or now},
        "updated_at": {"S": now},
        "like_count": {"N": str(payload.get("like_count", 0) or 0)},
        "comment_count": {"N": str(payload.get("comment_count", 0) or 0)},
        "bookmark_count": {"N": str(payload.get("bookmark_count", 0) or 0)},
        "is_public": {"BOOL": payload.get("is_public", False)},
    }
    
    ddb.put_item(TableName=TABLE, Item=item)


def save_error_record(payload: dict, error_msg: str):
    """에러 발생 시 DynamoDB에 에러 상태로 저장 (DynamoDB 구조에 맞춤)"""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # examples를 DynamoDB 형식으로 변환
    examples_ddb = []
    for ex in payload.get("examples", []):
        examples_ddb.append({
            "M": {
                "index": {"N": str(ex.get("index", 0))},
                "input": {"M": {
                    "content": {"S": ex.get("input", {}).get("content", "")},
                    "input_type": {"S": ex.get("input", {}).get("input_type", "text")}
                }},
                "output": {"S": ex.get("output", "")}
            }
        })
    
    item = {
        "PK": {"S": payload.get("PK", "")},
        "SK": {"S": payload.get("SK", "METADATA")},
        "PROMPT_INDEX_PK": {"S": payload.get("PROMPT_INDEX_PK", "USER_PROMPT_LIST")},
        "PROMPT_INDEX_SK": {"S": get_safe_prompt_index_sk(payload)},
        "type": {"S": payload.get("type", "PROMPT")},
        "create_user": {"S": payload.get("create_user", "")},
        "title": {"S": payload.get("title", "")},
        "content": {"S": payload.get("content", "")},  # 실제 SQS 메시지는 content 필드 사용
        "prompt_description": {"S": payload.get("prompt_description", "")},
        "price": {"N": str(payload.get("price", 0) or 0)},  # price 필드 추가
        "prompt_type": {"S": payload.get("prompt_type", "type_a")},
        "examples": {"L": examples_ddb},
        "examples_s3_url": {"S": payload.get("examples_s3_url", "")},
        "model": {"S": payload.get("model", "")},
        "evaluation_metrics": {"M": {}},
        "status": {"S": "failed"},  # 소문자로 변경
        "error": {"S": error_msg[:2000]},
        "created_at": {"S": payload.get("created_at") or now},
        "updated_at": {"S": now},
        "like_count": {"N": str(payload.get("like_count", 0) or 0)},
        "comment_count": {"N": str(payload.get("comment_count", 0) or 0)},
        "bookmark_count": {"N": str(payload.get("bookmark_count", 0) or 0)},
        "is_public": {"BOOL": payload.get("is_public", False)},
    }
    
    ddb.put_item(TableName=TABLE, Item=item)


def update_status_completed(pk: str, evaluation_metrics: dict, outputs_s3_url: str | None = None):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    expr = "SET #s=:s, updated_at=:u, evaluation_metrics=:m"
    names = {"#s": "status"}
    values = {
        ":s": {"S": "COMPLETED"},
        ":u": {"S": now},
        ":m": {"M": to_ddb_map(evaluation_metrics)},
    }
    if outputs_s3_url:
        expr += ", outputs_s3_url=:o"
        values[":o"] = {"S": outputs_s3_url}

    ddb.update_item(
        TableName=TABLE,
        Key={"PK": {"S": pk}, "SK": {"S": "METADATA"}},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )

def update_status_error(pk: str, error_msg: str):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ddb.update_item(
        TableName=TABLE,
        Key={"PK": {"S": pk}, "SK": {"S": "METADATA"}},
        UpdateExpression="SET #s=:s, updated_at=:u, error=:e",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": {"S": "ERROR"},
            ":u": {"S": now},
            ":e": {"S": error_msg[:2000]},
        },
    )

def to_ddb_map(obj: dict) -> dict:
    """파이썬 dict → DynamoDB AttributeValue(M) 변환(최소형)"""
    out = {}
    for k, v in obj.items():
        if isinstance(v, bool):
            out[k] = {"BOOL": v}
        elif isinstance(v, (int, float)):
            out[k] = {"N": str(v)}
        elif v is None:
            out[k] = {"NULL": True}
        elif isinstance(v, dict):
            out[k] = {"M": to_ddb_map(v)}
        elif isinstance(v, list):
            out[k] = {"L": [to_ddb_value(x) for x in v]}
        else:
            out[k] = {"S": str(v)}
    return out

def to_ddb_value(v):
    if isinstance(v, bool):
        return {"BOOL": v}
    if isinstance(v, (int, float)):
        return {"N": str(v)}
    if v is None:
        return {"NULL": True}
    if isinstance(v, dict):
        return {"M": to_ddb_map(v)}
    if isinstance(v, list):
        return {"L": [to_ddb_value(x) for x in v]}
    return {"S": str(v)}
