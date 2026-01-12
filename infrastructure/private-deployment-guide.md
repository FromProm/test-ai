# AI 서버 프라이빗 구성 가이드

## 옵션 1: VPC + PrivateLink 구성

### 네트워크 아키텍처
```
Internet Gateway
    ↓
Public Subnet (ALB only)
    ↓
Private Subnet (AI Server)
    ↓
VPC Endpoints → AWS Services
```

### 필요한 VPC Endpoints
- Bedrock Runtime
- S3
- DynamoDB  
- SQS
- CloudWatch Logs

### 보안 그룹 설정
```yaml
AI-Server-SG:
  Inbound:
    - Port 8000 from ALB-SG only
  Outbound:
    - HTTPS to VPC Endpoints only
    - No direct internet access
```

## 옵션 2: 온프레미스 + AWS Direct Connect

### 하이브리드 구성
- AI 서버: 온프레미스 프라이빗 네트워크
- AWS 서비스: Direct Connect로 접근
- 데이터 주권 완전 보장

## 옵션 3: 완전 프라이빗 (Self-hosted Models)

### 오픈소스 모델 대체
- Claude → Llama 3.1/3.2
- Titan Embeddings → Sentence Transformers
- 완전 격리된 환경 구성 가능

### 성능 고려사항
- GPU 인프라 필요
- 모델 성능 차이 존재
- 운영 복잡도 증가