# Prompt Evaluation API

AI 프롬프트 평가를 위한 고성능 병렬 처리 API

## 🚀 주요 기능

- **병렬 파이프라인**: 6개 지표 동시 계산
- **환각 탐지**: MCP 기반 실시간 사실 검증
- **다중 모델 지원**: Claude, Cohere, Nova 임베딩
- **배치 최적화**: AI Agent + MCP 병렬 호출

## 📊 성능

- **기존**: 10분 (순차 처리)
- **현재**: 2분 40초 (병렬 최적화)
- **개선율**: 73% 단축

## 🛠️ 설치 및 실행

### 1. 환경 설정

```bash
# Python 3.10+ 필요
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux  
source venv/bin/activate
```

### 2. 의존성 설치

```bash
pip install -e .
```

### 3. 환경 변수 설정

`.env.example`을 복사해서 `.env` 파일 생성:
```bash
cp .env.example .env
```

`.env` 파일에서 필수 값들 설정:
```env
# AWS Bedrock 사용을 위한 필수 설정
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here

# 개발/테스트시에는 Mock 모드 사용 가능
MOCK_MODE=false  # true로 설정하면 AWS 없이 테스트 가능
```

**AWS 설정 방법**:
1. AWS 콘솔에서 IAM 사용자 생성
2. Bedrock 서비스 권한 부여
3. Access Key 생성 후 `.env`에 입력

### 4. MCP 서버 설치 (선택사항)

```bash
# uv 설치 (https://docs.astral.sh/uv/getting-started/installation/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# MCP 서버들 설치
uvx wikipedia-mcp
uvx duckduckgo-mcp-server
uvx arxiv-mcp-server  
uvx mcp-server-fetch
```

### 5. 서버 실행

```bash
python run.py
```

## 📝 API 사용법

### 평가 작업 생성

```bash
curl -X POST "http://localhost:8000/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "다음 질문에 대해 정확하고 상세한 답변을 제공해주세요.",
    "example_inputs": [
      {"content": "OpenAI가 GPT-4를 언제 발표했나요?"},
      {"content": "지구에서 태양까지의 거리는?"},
      {"content": "물의 화학식은 무엇인가요?"}
    ],
    "prompt_type": "TYPE_A",
    "repeat_count": 5
  }'
```

### 결과 조회

```bash
curl "http://localhost:8000/jobs/{job_id}"
```

## 🔧 아키텍처

### 병렬 파이프라인
```
출력 생성 (15개 LLM 호출 병렬)
    ↓
6개 지표 동시 계산
├── 토큰 수 계산
├── 정보 밀도 
├── 임베딩 (Cohere+Nova 병렬)
├── 정확도 계산  
├── 환각탐지 (MCP 배치 병렬)
└── 모델 편차
```

### 환각탐지 최적화
- **배치 MCP 선택**: AI Agent 1번 호출로 모든 claim 처리
- **병렬 검증**: 40개 claim 동시 검증
- **캐싱**: 중복 claim 재검증 방지

## 📋 지표 설명

1. **토큰 사용량**: tiktoken 기반 토큰 수 계산
2. **정보 밀도**: n-gram 기반 정보량 측정  
3. **일관성**: 임베딩 유사도 기반 응답 일관성
4. **정확도**: AI 기반 프롬프트 요구사항 충족도
5. **환각탐지**: MCP 기반 사실 검증 (0-100점)
6. **모델 편차**: 다중 모델 간 응답 차이

## 🌐 MCP 서버

환각탐지에 사용되는 무료 MCP 서버들:
- **Wikipedia**: 위키피디아 검색
- **DuckDuckGo**: 웹 검색
- **ArXiv**: 학술 논문 검색
- **Web Scraper**: 웹 페이지 스크래핑

## 🔍 문제 해결

### AWS 권한 오류
```
AWS_ACCESS_KEY_ID와 AWS_SECRET_ACCESS_KEY 확인
Bedrock 서비스 권한 필요
```

### MCP 서버 오류
```
uv 설치 확인: https://docs.astral.sh/uv/
MCP 서버들이 정상 설치되었는지 확인
```

## 📄 라이선스

MIT License