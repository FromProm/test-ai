#!/usr/bin/env python3
"""
간단한 SQS 연결 테스트
"""

import boto3

# 직접 설정
SQS_QUEUE_URL = "https://sqs.ap-northeast-2.amazonaws.com/261595668962/testest"
AWS_REGION_SQS_DDB = "ap-northeast-2"

def test_sqs():
    print("📡 SQS 연결 테스트...")
    print(f"Queue URL: {SQS_QUEUE_URL}")
    print(f"Region: {AWS_REGION_SQS_DDB}")
    
    try:
        sqs = boto3.client("sqs", region_name=AWS_REGION_SQS_DDB)
        
        response = sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=['QueueArn', 'ApproximateNumberOfMessages']
        )
        
        print(f"✅ SQS 연결 성공!")
        print(f"   - Queue ARN: {response['Attributes'].get('QueueArn')}")
        print(f"   - 대기 중인 메시지: {response['Attributes'].get('ApproximateNumberOfMessages')}")
        return True
        
    except Exception as e:
        print(f"❌ SQS 연결 실패: {e}")
        return False

def test_dynamodb():
    print("\n🗄️ DynamoDB 연결 테스트...")
    
    try:
        ddb = boto3.client("dynamodb", region_name=AWS_REGION_SQS_DDB)
        
        response = ddb.describe_table(TableName="FromProm_Table")
        
        print(f"✅ DynamoDB 연결 성공!")
        print(f"   - Table: FromProm_Table")
        print(f"   - Region: {AWS_REGION_SQS_DDB}")
        print(f"   - Status: {response['Table']['TableStatus']}")
        print(f"   - Item Count: {response['Table']['ItemCount']}")
        return True
        
    except Exception as e:
        print(f"❌ DynamoDB 연결 실패: {e}")
        return False

if __name__ == "__main__":
    print("🧪 리전 분리 테스트")
    print("=" * 50)
    
    sqs_ok = test_sqs()
    ddb_ok = test_dynamodb()
    
    print("\n" + "=" * 50)
    if sqs_ok and ddb_ok:
        print("🎉 모든 연결 테스트 통과!")
        print("리전 분리가 정상적으로 작동합니다.")
    else:
        print("❌ 일부 테스트 실패")