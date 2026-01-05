# Prompt Evaluation System

프롬프트 품질을 종합적으로 평가하는 FastAPI 기반 시스템입니다.

## 🚀 **빠른 시작**

### 1. 저장소 클론
```bash
git clone https://github.com/your-username/prompt-eval.git
cd prompt-eval
```

### 2. 가상환경 생성 및 활성화
```bash
# 가상환경 생성
python -m venv venv

# 활성화 (Windows)
venv\Scripts\activate

# 활성화 (Mac/Linux)
source venv/bin/activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
STORAGE_BACKEND=sqlite
MOCK_MODE=true
```

### 5. 서버 실행
```bash
python run.py
```

### 6. API 문서 확인
브라우저에서 http://localhost:8000/docs 접속

## 📊 **주요 기능**

### 평가 지표
- **토큰 사용량**: 고정 프롬프트의 효율성
- **정보 밀도**: n-gram 기반 중복률 분석
- **응답 일관성**: Centroid 기반 벡터 유사도
- **관련성**: 입력-출력 의미적 연관성
- **환각 탐지**: AI Judge 기반 사실성 검증
- **모델 편차**: 버전/모델 간 성능 차이

### 프롬프트 타입
- **TYPE_A (Information)**: 정답/사실/근거 요구 프롬프트
- **TYPE_B_TEXT (Creative Text)**: 창작/상상/스토리 텍스트
- **TYPE_B_IMAGE (Creative Image)**: 이미지 관련 창작

## ⚙️ **설정 옵션**

### 저장소 백엔드
```env
# 로컬 개발
STORAGE_BACKEND=sqlite

# 단순 프로덕션
STORAGE_BACKEND=s3

# 고성능 프로덕션
STORAGE_BACKEND=dynamodb_s3
```

### AI 모드
```env
# 테스트/개발 (무료)
MOCK_MODE=true

# 실제 AWS Bedrock 사용
MOCK_MODE=false
```

## 🧪 **API 사용 예시**

### 작업 생성
```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "다음 질문에 답하세요: {{}}",
    "example_inputs": [
      {"content": "파리의 인구는?", "input_type": "text"},
      {"content": "지구의 나이는?", "input_type": "text"},
      {"content": "광속은 얼마인가?", "input_type": "text"}
    ],
    "prompt_type": "type_a",
    "repeat_count": 5
  }'
```

## 🏗️ **아키텍처**

```
app/
├── main.py                 # FastAPI 엔트리포인트
├── api/routes/            # API 라우터
├── core/                  # 핵심 설정/스키마
├── orchestrator/          # 파이프라인 오케스트레이터
│   ├── pipeline.py        # 메인 파이프라인
│   └── stages/           # 각 평가 단계
├── adapters/             # 외부 서비스 어댑터
│   ├── runner/           # 모델 실행
│   ├── embedder/         # 임베딩 생성
│   └── judge/            # 환각 탐지
├── storage/              # 데이터 저장
└── cache/                # 캐싱
```

## 🤝 **기여하기**

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 **라이선스**

This project is licensed under the MIT License."# test-ai" 
"# test-ai" 
