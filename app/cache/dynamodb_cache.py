import json
import boto3
import logging
import hashlib
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError
from decimal import Decimal
from app.core.config import settings

logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    """DynamoDB Decimal 타입을 JSON으로 변환"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class DynamoDBFactCheckCache:
    """DynamoDB 기반 분산 캐시 (환각탐지용)"""
    
    def __init__(self, table_name: str = None, region_name: str = None):
        self.table_name = table_name or getattr(settings, 'dynamodb_cache_table', 'fact-check-cache')
        self.region_name = region_name or getattr(settings, 'aws_region_sqs_ddb', 'ap-northeast-2')
        self.ttl = getattr(settings, 'cache_fact_check_ttl', 30 * 24 * 3600)  # 설정에서 TTL 가져오기
        
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name=self.region_name)
            self.table = self.dynamodb.Table(self.table_name)
            logger.info(f"DynamoDB cache initialized: table={self.table_name}, region={self.region_name}")
            
            # 테이블 존재 확인 및 생성
            self._ensure_table_exists()
            
        except NoCredentialsError:
            logger.warning("AWS credentials not found, DynamoDB cache disabled")
            self.dynamodb = None
            self.table = None
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB client: {str(e)}")
            self.dynamodb = None
            self.table = None
    
    def _ensure_table_exists(self):
        """테이블 존재 확인 및 생성"""
        if not self.dynamodb:
            return
        
        try:
            # 테이블 존재 확인
            self.table.load()
            logger.info(f"DynamoDB table '{self.table_name}' exists")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info(f"Creating DynamoDB table '{self.table_name}'...")
                self._create_table()
            else:
                logger.error(f"Error checking table existence: {str(e)}")
                raise
    
    def _create_table(self):
        """DynamoDB 테이블 생성"""
        try:
            table = self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {
                        'AttributeName': 'claim_hash',
                        'KeyType': 'HASH'  # Partition key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'claim_hash',
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST',  # On-demand 요금제
                TimeToLiveSpecification={
                    'AttributeName': 'ttl',
                    'Enabled': True
                },
                Tags=[
                    {
                        'Key': 'Purpose',
                        'Value': 'FactCheckCache'
                    },
                    {
                        'Key': 'Environment',
                        'Value': 'Production'
                    }
                ]
            )
            
            # 테이블 생성 완료 대기
            table.wait_until_exists()
            logger.info(f"DynamoDB table '{self.table_name}' created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create DynamoDB table: {str(e)}")
            raise
    
    def _hash_claim(self, claim: str) -> str:
        """Claim을 키워드 기반으로 해시 생성"""
        keywords = self._extract_keywords(claim)
        if not keywords:
            # 키워드가 없으면 원본 텍스트 해시 사용
            return hashlib.sha256(claim.encode('utf-8')).hexdigest()
        
        # 키워드를 정렬해서 순서에 상관없이 같은 해시 생성
        keywords_str = "_".join(sorted(keywords))
        return hashlib.sha256(keywords_str.encode('utf-8')).hexdigest()
    
    def _extract_keywords(self, claim: str) -> List[str]:
        """Claim에서 핵심 키워드 추출"""
        import re
        
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
    
    def _convert_floats_to_decimal(self, obj):
        """float를 Decimal로 변환 (DynamoDB 호환성)"""
        if isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(v) for v in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        else:
            return obj
    
    def _convert_decimals_to_float(self, obj):
        """Decimal을 float로 변환"""
        if isinstance(obj, dict):
            return {k: self._convert_decimals_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals_to_float(v) for v in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        else:
            return obj
    
    async def get_fact_check(self, claim: str) -> Optional[Dict[str, Any]]:
        """DynamoDB에서 fact check 결과 조회"""
        if not self.table:
            return None
        
        try:
            claim_hash = self._hash_claim(claim)
            
            response = self.table.get_item(
                Key={'claim_hash': claim_hash},
                ConsistentRead=False  # Eventually consistent read (더 빠름)
            )
            
            if 'Item' in response:
                item = response['Item']
                
                # TTL 확인 (DynamoDB TTL은 자동이지만 추가 확인)
                current_timestamp = int(datetime.utcnow().timestamp())
                if item.get('ttl', 0) > current_timestamp:
                    result = self._convert_decimals_to_float(item.get('result', {}))
                    logger.debug(f"DynamoDB cache hit for claim: {claim[:50]}...")
                    return result
                else:
                    # 만료된 항목 (DynamoDB TTL이 아직 삭제하지 않은 경우)
                    logger.debug(f"DynamoDB cache expired for claim: {claim[:50]}...")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get fact check from DynamoDB: {str(e)}")
            return None
    
    async def set_fact_check(self, claim: str, result: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """DynamoDB에 fact check 결과 저장"""
        if not self.table:
            return False
        
        try:
            claim_hash = self._hash_claim(claim)
            current_time = datetime.utcnow()
            expires_at = current_time + timedelta(seconds=ttl or self.ttl)
            
            # DynamoDB 아이템 구성
            item = {
                'claim_hash': claim_hash,
                'claim_text': claim,
                'result': self._convert_floats_to_decimal(result),
                'created_at': current_time.isoformat(),
                'expires_at': expires_at.isoformat(),
                'ttl': int(expires_at.timestamp())  # DynamoDB TTL용
            }
            
            # DynamoDB에 저장
            self.table.put_item(Item=item)
            
            logger.debug(f"Cached fact check to DynamoDB: {claim[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set fact check cache to DynamoDB: {str(e)}")
            return False
    
    async def batch_set_fact_checks(self, claims_results: List[Dict[str, Any]]) -> int:
        """배치로 여러 fact check 결과를 DynamoDB에 저장"""
        if not self.table or not claims_results:
            return 0
        
        success_count = 0
        batch_size = 25  # DynamoDB batch_writer 최대 크기
        
        try:
            # 배치를 25개씩 나누어 처리
            for i in range(0, len(claims_results), batch_size):
                batch = claims_results[i:i + batch_size]
                
                with self.table.batch_writer() as batch_writer:
                    for item in batch:
                        try:
                            claim = item.get('claim', '')
                            result = item.get('result', {})
                            ttl = item.get('ttl')
                            
                            if claim and result:
                                claim_hash = self._hash_claim(claim)
                                current_time = datetime.utcnow()
                                expires_at = current_time + timedelta(seconds=ttl or self.ttl)
                                
                                dynamodb_item = {
                                    'claim_hash': claim_hash,
                                    'claim_text': claim,
                                    'result': self._convert_floats_to_decimal(result),
                                    'created_at': current_time.isoformat(),
                                    'expires_at': expires_at.isoformat(),
                                    'ttl': int(expires_at.timestamp())
                                }
                                
                                batch_writer.put_item(Item=dynamodb_item)
                                success_count += 1
                                
                        except Exception as e:
                            logger.error(f"Batch item failed: {str(e)}")
                            continue
            
            logger.info(f"DynamoDB batch set completed: {success_count}/{len(claims_results)} successful")
            return success_count
            
        except Exception as e:
            logger.error(f"DynamoDB batch set failed: {str(e)}")
            return success_count
    
    async def cleanup_expired(self) -> int:
        """만료된 DynamoDB 캐시 정리 (DynamoDB TTL이 자동 처리하므로 수동 정리는 선택적)"""
        if not self.table:
            return 0
        
        try:
            # DynamoDB TTL이 자동으로 만료된 항목을 삭제하므로
            # 여기서는 통계 목적으로만 만료된 항목 수를 계산
            current_timestamp = int(datetime.utcnow().timestamp())
            
            # 스캔으로 만료된 항목 찾기 (비용이 많이 들므로 주의)
            response = self.table.scan(
                FilterExpression='#ttl < :current_time',
                ExpressionAttributeNames={'#ttl': 'ttl'},
                ExpressionAttributeValues={':current_time': current_timestamp},
                Select='COUNT'
            )
            
            expired_count = response.get('Count', 0)
            
            if expired_count > 0:
                logger.info(f"Found {expired_count} expired entries (will be auto-deleted by DynamoDB TTL)")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Failed to check expired DynamoDB cache: {str(e)}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """DynamoDB 캐시 통계"""
        if not self.table:
            return {'status': 'disabled', 'reason': 'DynamoDB client not available'}
        
        try:
            # 테이블 정보 조회
            table_info = self.table.describe()
            
            stats = {
                'table_name': self.table_name,
                'region': self.region_name,
                'ttl_days': self.ttl // (24 * 3600),
                'table_status': table_info['Table']['TableStatus'],
                'billing_mode': table_info['Table']['BillingModeSummary']['BillingMode'],
                'item_count': table_info['Table']['ItemCount'],
                'table_size_bytes': table_info['Table']['TableSizeBytes'],
                'creation_date': table_info['Table']['CreationDateTime'].isoformat(),
                'status': 'active'
            }
            
            # TTL 설정 확인
            if 'TimeToLiveDescription' in table_info['Table']:
                ttl_info = table_info['Table']['TimeToLiveDescription']
                stats['ttl_enabled'] = ttl_info.get('TimeToLiveStatus') == 'ENABLED'
                stats['ttl_attribute'] = ttl_info.get('AttributeName')
            
            # 테이블 크기를 MB로 변환
            stats['table_size_mb'] = round(stats['table_size_bytes'] / (1024 * 1024), 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get DynamoDB cache stats: {str(e)}")
            return {'status': 'error', 'error': str(e)}
    
    async def clear_all(self) -> bool:
        """전체 캐시 삭제 (테이블 스캔 후 배치 삭제)"""
        if not self.table:
            return False
        
        try:
            logger.warning("Clearing all DynamoDB cache entries...")
            
            # 모든 항목 스캔
            response = self.table.scan(ProjectionExpression='claim_hash')
            
            # 배치 삭제
            with self.table.batch_writer() as batch:
                for item in response['Items']:
                    batch.delete_item(Key={'claim_hash': item['claim_hash']})
            
            # 페이지네이션 처리
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    ProjectionExpression='claim_hash',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                
                with self.table.batch_writer() as batch:
                    for item in response['Items']:
                        batch.delete_item(Key={'claim_hash': item['claim_hash']})
            
            logger.info("All DynamoDB cache entries cleared")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear DynamoDB cache: {str(e)}")
            return False
    
    async def get_item_by_hash(self, claim_hash: str) -> Optional[Dict[str, Any]]:
        """해시로 직접 조회 (디버깅용)"""
        if not self.table:
            return None
        
        try:
            response = self.table.get_item(Key={'claim_hash': claim_hash})
            
            if 'Item' in response:
                return self._convert_decimals_to_float(dict(response['Item']))
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get item by hash: {str(e)}")
            return None