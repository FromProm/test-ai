# API 명세서

Base URL: `http://localhost:8000/api/v1`

---

## 📋 표 | ⭐ 엔드포인트

| No | 기능 | 카테고리 | Method | 파라미터 | URL | 설명 | AWS |
|----|------|----------|--------|----------|-----|------|-----|
| 1 | 평가 작업 생성 | Jobs | `POST` | prompt: `string`, example_inputs: `array`, prompt_type: `string`, title?: `string`, user_id?: `string` | /jobs | 프롬프트 평가 작업 생성 및 백그라운드 실행 | Bedrock, S3, DynamoDB |
| 2 | 작업 조회 | Jobs | `GET` | job_id: `string` | /jobs/{job_id} | 특정 작업의 상태 및 결과 조회 | |
| 3 | 작업 목록 조회 | Jobs | `GET` | page?: `int`, size?: `int` | /jobs | 작업 목록 페이징 조회 | |
| 4 | 작업 재실행 | Jobs | `POST` | job_id: `string` | /jobs/{job_id}/rerun | 기존 작업 동일 설정으로 재실행 | Bedrock |
| 5 | DynamoDB 형식 조회 | Jobs | `GET` | job_id: `string`, title: `string`, user_id?: `string` | /jobs/{job_id}/dynamodb | 완료된 작업을 DynamoDB 형식으로 변환 | |
| 6 | S3 예시 데이터 조회 | Jobs | `GET` | job_id: `string` | /jobs/{job_id}/s3-examples | S3 저장용 예시 데이터 반환 | |
| 7 | 모델 비교 | Compare | `POST` | model_a: `string`, model_b: `string`, prompt: `string`, example_inputs: `array` | /compare | 두 모델의 평가 결과 비교 | Bedrock |
| 8 | 헬스 체크 | Health | `GET` | | /health | 서버 상태 확인 | |
| 9 | 저장소 백엔드 확인 | Debug | `GET` | | /debug/storage/backend | 현재 저장소 설정 확인 | |
| 10 | S3 버킷 목록 | Debug | `GET` | | /debug/s3/buckets | S3 버킷 목록 조회 | S3 |
| 11 | S3 작업 목록 | Debug | `GET` | | /debug/s3/jobs | S3에 저장된 작업 목록 | S3 |
| 12 | S3 작업 파일 | Debug | `GET` | job_id: `string` | /debug/s3/jobs/{job_id} | 특정 작업의 S3 파일 목록 | S3 |
| 13 | 프롬프트 미리보기 | Debug | `POST` | prompt: `string`, example_input: `string` | /debug/prompt/preview | 프롬프트 변수 치환 미리보기 | |
| 14 | 실제 프롬프트 확인 | Debug | `GET` | job_id: `string` | /debug/jobs/{job_id}/prompts | LLM에 전달된 실제 프롬프트 확인 | |

---

## 상세 파라미터

### prompt_type
| 값 | 설명 | 평가 지표 |
|----|------|----------|
| type_a | Information (정답/사실 요구) | token_usage, information_density, consistency, model_variance, hallucination, relevance |
| type_b_text | Creative 글 | token_usage, information_density, model_variance, relevance |
| type_b_image | Creative 이미지 | token_usage, consistency, model_variance, relevance |

### recommended_model
| 모델 ID | 용도 |
|---------|------|
| anthropic.claude-3-5-sonnet-20240620-v1:0 | 텍스트 (고성능) |
| anthropic.claude-3-sonnet-20240229-v1:0 | 텍스트 (중간) |
| anthropic.claude-3-haiku-20240307-v1:0 | 텍스트 (빠름) |
| amazon.nova-canvas-v1:0 | 이미지 생성 |

### status
| 값 | 설명 |
|----|------|
| pending | 대기 중 |
| running | 실행 중 |
| completed | 완료 |
| failed | 실패 |
