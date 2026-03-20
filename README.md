# AutoGenie

AI 기반 워크플로우를 활용하여 Databricks Genie Space를 생성하고 개선하는 통합 Databricks Apps 플랫폼입니다.

## 개요

AutoGenie는 두 가지 핵심 워크플로우를 하나의 탭 기반 애플리케이션으로 통합합니다:

- **Lamp** (생성): 자연어 요구사항 문서로부터 새로운 Genie Space를 자동 생성
- **Enhancer** (개선): 벤치마크 기반 반복 최적화를 통해 기존 Genie Space 성능 향상

FastAPI 백엔드와 Next.js 프론트엔드로 구성된 Databricks App이며, Databricks Foundation Models를 활용하여 지능적인 설정 생성 및 최적화를 수행합니다.

## 주요 기능

### Lamp 워크플로우 - 새 Genie Space 생성

요구사항 문서를 완전히 구성된 Genie Space로 변환합니다:

| 단계 | 설명 |
|------|------|
| **업로드 & 파싱** | PDF/Markdown 요구사항 업로드, LLM을 활용한 메트릭 및 비즈니스 로직 추출 |
| **생성** | AI가 완전한 Genie Space 설정(테이블, 조인, 인스트럭션) 자동 생성 |
| **검증** | Unity Catalog 대비 테이블 참조 검증, 불일치 대화형 수정 |
| **벤치마크** | 요구사항에서 벤치마크 SQL 쿼리 추출 및 검증 |
| **배포** | 구성된 Genie Space를 Databricks 워크스페이스에 배포 |

### Enhancer 워크플로우 - 기존 Space 개선

벤치마크를 활용한 반복적 Genie Space 성능 최적화:

| 단계 | 설명 |
|------|------|
| **설정** | 대상 Genie Space, SQL Warehouse 선택 및 벤치마크 업로드 |
| **점수 측정** | Space에 벤치마크 실행, 통과/실패율 측정 |
| **계획** | AI가 실패 원인 분석 및 수정안 제안 (인스트럭션, 샘플 쿼리, 조인 등) |
| **적용** | 승인된 수정안을 Genie Space 설정에 적용 |

**개선 모드:**
- **수동 모드**: 점수 측정 → 계획 → 적용 각 단계에서 승인 후 진행
- **자동 루프 모드**: 목표 점수 달성 또는 최대 반복 횟수까지 자동 반복

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│  ┌─────────────────┐              ┌─────────────────────────┐   │
│  │   Lamp 탭       │              │    Enhancer 탭          │   │
│  │  - ParseStep    │              │  - ConfigureStep        │   │
│  │  - GenerateStep │              │  - ScoreStep            │   │
│  │  - ValidateStep │              │  - PlanStep             │   │
│  │  - BenchmarkStep│              │  - ApplyStep            │   │
│  │  - DeployStep   │              │  - AutoLoopStep         │   │
│  └─────────────────┘              └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   /api/lamp │  │/api/enhancer│  │     공유 서비스          │  │
│  │  - /parse   │  │ - /jobs/*   │  │  - SessionStore (SQLite)│  │
│  │  - /generate│  │ - /sessions │  │  - JobManager           │  │
│  │  - /validate│  │ - /workspace│  │  - FileStorage          │  │
│  │  - /deploy  │  │ - /iterations│  │  - Auth Middleware      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    핵심 모듈                                     │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐   │
│  │       genie/            │  │       enhancer/             │   │
│  │  - parsing/ (PDF, MD)   │  │  - scoring/ (벤치마크)      │   │
│  │  - pipeline/ (생성/검증) │  │  - enhancement/ (수정)      │   │
│  │  - api/ (Genie 클라이언트)│  │  - api/ (Space 운영)       │   │
│  │  - llm/ (Databricks)    │  │  - llm/ (분석)              │   │
│  │  - validation/          │  │  - utils/                   │   │
│  └─────────────────────────┘  └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Databricks 플랫폼                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│  │Unity Catalog│  │Genie Spaces│  │SQL Warehouse│  │Foundation │  │
│  │  (테이블)   │  │   (API)    │  │  (컴퓨트)   │  │  Models   │  │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 기술 스택

### 백엔드
- **Python 3.11+**
- **FastAPI** - 비동기 웹 프레임워크
- **SQLite** - 세션 및 작업 영속화
- **Databricks SDK** - 워크스페이스 연동
- **PyJWT** - 토큰 처리

### 프론트엔드
- **Next.js 14** - React 프레임워크 (정적 내보내기)
- **TypeScript** - 타입 안전 개발
- **Tailwind CSS** - 유틸리티 우선 스타일링
- **React Markdown** - 마크다운 렌더링

### AI/ML
- **Databricks Foundation Models** - 생성 및 분석용 LLM
- **databricks-gpt-5-2** - 기본 모델 엔드포인트

## 설치

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- Databricks CLI 설정 완료
- Databricks 워크스페이스 접근 권한

### 설정 방법

1. **저장소 클론**
   ```bash
   git clone <repository-url>
   cd AutoGenie
   ```

2. **Python 가상환경 생성**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # 또는
   .venv\Scripts\activate     # Windows
   ```

3. **Python 의존성 설치**
   ```bash
   pip install -r requirements.txt
   ```

4. **프론트엔드 의존성 설치**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

환경 설정 및 구동 방법은 아래 [구동 방법](#구동-방법) 섹션을 참고하세요.

## 구동 방법

AutoGenie는 두 가지 방법으로 구동할 수 있습니다.

---

### 방법 1: Databricks Apps 배포

Databricks 워크스페이스에 앱으로 배포하여 운영하는 방법입니다. 인증은 OBO(On Behalf Of) 방식으로 사용자 토큰이 자동 주입됩니다.

#### 1-1. databricks.yml 설정

`databricks.yml` 파일의 `targets.default` 섹션에서 아래 3개 플레이스홀더를 실제 값으로 교체합니다:

```yaml
targets:
  default:
    workspace:
      host: https://<your-workspace>.cloud.databricks.com/   # ① 워크스페이스 URL
      profile: <your-profile>                                  # ② CLI 프로필명
    resources:
      apps:
        autogenie_app:
          resources:
            - name: "validation-warehouse"
              sql_warehouse:
                id: "<your-warehouse-id>"                      # ③ SQL Warehouse ID
```

| 플레이스홀더 | 설명 | 확인 방법 |
|-------------|------|----------|
| `<your-workspace>` | 워크스페이스 도메인 (예: `mycompany`) | 브라우저에서 워크스페이스 URL 확인 |
| `<your-profile>` | Databricks CLI 프로필명 | `databricks auth profiles` 명령어로 확인 |
| `<your-warehouse-id>` | SQL Warehouse의 ID (16자리 hex) | 워크스페이스 > SQL Warehouses > 대상 warehouse의 Connection details에서 확인 |

> **참고**: `databricks-gpt-5-2`, `databricks-claude-sonnet-4`는 Databricks Foundation Model API의 공개 엔드포인트이므로 별도 수정이 필요 없습니다. 다른 모델을 사용하려면 `serving_endpoint.name`을 변경하세요.

#### 1-2. 프론트엔드 빌드

```bash
cd frontend && npm run build && cd ..
```

#### 1-3. Bundle 배포

```bash
databricks bundle deploy --target default
```

#### 1-4. 앱 권한 설정

Databricks 워크스페이스에서 배포된 앱의 사용자 권한을 설정합니다.

#### 인증 방식

Databricks Apps 환경에서는 다음이 자동으로 처리됩니다:
- **사용자 토큰**: Apps 게이트웨이가 `X-Forwarded-Access-Token` 헤더를 주입
- **서비스 프린시펄**: `app.yaml`의 리소스 설정에 따라 OAuth M2M 자동 구성
- **환경 변수**: `WAREHOUSE_ID`, `FRONTEND_EXPORT_DIR` 등이 `app.yaml`에서 자동 설정

---

### 방법 2: 로컬 개발 환경

로컬 머신에서 직접 구동하는 방법입니다. Databricks CLI의 OAuth 인증을 사용합니다.

#### 2-1. Databricks CLI 인증

```bash
# Databricks CLI로 워크스페이스에 로그인 (OAuth 브라우저 인증)
# --profile 옵션으로 프로필 이름을 지정합니다 (databricks.yml의 <your-profile>과 동일하게 설정)
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile <your-profile>

# 인증 확인
databricks auth token --host https://<your-workspace>.cloud.databricks.com --profile <your-profile>

# 등록된 프로필 목록 확인
databricks auth profiles
```

#### 2-2. 환경 변수 설정

```bash
cat > .env << 'EOF'
DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<your-warehouse-id>
EOF
```

| 변수 | 설명 | 필수 |
|------|------|------|
| `DATABRICKS_HOST` | Databricks 워크스페이스 URL | 예 |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse HTTP 경로 | 예 |
| `FRONTEND_EXPORT_DIR` | 프론트엔드 정적 파일 경로 (기본: `frontend/out`) | 아니오 |

> **참고**: 로컬 환경에서는 `databricks auth token` 명령어를 통해 자동으로 토큰을 획득합니다. 별도의 PAT나 OAuth 클라이언트 설정이 필요 없습니다.

#### 2-3. 개발 모드 (핫 리로딩)

백엔드와 프론트엔드를 별도 터미널에서 실행합니다:

```bash
# 터미널 1: 백엔드
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# 터미널 2: 프론트엔드
cd frontend
npm run dev
```

`http://localhost:3000`에서 애플리케이션에 접근합니다.

#### 2-4. 프로덕션 빌드 (단일 서버)

프론트엔드를 빌드하고 백엔드가 정적 파일을 함께 서빙합니다:

```bash
# 프론트엔드 빌드
cd frontend && npm run build && cd ..

# 백엔드 실행 (정적 파일 포함)
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

`http://localhost:8000`에서 접근합니다.

## 사용 방법

### 데모 데이터 준비

`generate_demo/` 디렉토리에 리테일 분석용 데모 데이터셋, 요구사항 문서, 벤치마크 파일이 포함되어 있습니다.
데이터 삽입 및 데모 에셋 사용법은 [`generate_demo/README.md`](generate_demo/README.md)를 참고하세요.

### Lamp 워크플로우 사용하기

새로운 Genie Space를 요구사항 문서로부터 자동 생성하는 과정입니다:

1. 앱에 접속하여 **Lamp** 탭을 선택합니다
2. 좌측 사이드바에서 **새 세션 생성**을 클릭합니다
3. **Parse 단계**: `requirements.md` 파일을 업로드합니다 - AI가 요구사항을 분석하여 메트릭, 테이블, SQL 패턴을 추출합니다
4. **Generate 단계**: "생성" 버튼을 클릭하면 AI가 Genie Space 설정(테이블, 조인, 인스트럭션, 샘플 쿼리)을 자동으로 생성합니다
5. **Validate 단계**: 생성된 설정의 테이블 참조를 Unity Catalog와 대조 검증합니다. 불일치 항목은 대화형으로 수정할 수 있습니다
6. **Benchmark 단계**: `benchmarks_lamp.json`을 업로드하여 벤치마크 SQL 쿼리를 검증합니다
7. **Deploy 단계**: 검증된 설정으로 Genie Space를 워크스페이스에 배포합니다

### Enhancer 워크플로우 사용하기

기존 Genie Space의 성능을 벤치마크 기반으로 반복 개선하는 과정입니다:

1. 앱에서 **Enhancer** 탭을 선택합니다
2. 좌측 사이드바에서 **새 세션 생성**을 클릭합니다
3. **Configure 단계**: 대상 Genie Space와 SQL Warehouse를 선택하고, `benchmarks_enhancer.json`을 업로드합니다
4. **Score 단계**: "점수 측정" 버튼을 클릭하면 벤치마크 질문을 Genie Space에 실행하여 통과/실패율을 측정합니다
5. **Plan 단계**: AI가 실패 원인을 분석하고 수정안(인스트럭션 추가, 샘플 쿼리 추가, 조인 수정 등)을 제안합니다. 각 수정안을 검토하고 승인합니다
6. **Apply 단계**: 승인된 수정안을 Genie Space에 적용합니다
7. **(선택) Auto-Loop**: 목표 점수와 최대 반복 횟수를 설정하면 Score → Plan → Apply 사이클을 자동으로 반복합니다

## API 레퍼런스

### 공용 엔드포인트

| 메서드 | 엔드포인트 | 설명 |
|--------|----------|------|
| GET | `/health` | 헬스 체크 |
| GET | `/api/sessions` | 모든 세션 목록 조회 |
| POST | `/api/sessions` | 새 세션 생성 |
| GET | `/api/sessions/{id}` | 세션 상세 조회 |
| PUT | `/api/sessions/{id}` | 세션 이름 수정 |
| DELETE | `/api/sessions/{id}` | 세션 삭제 |
| GET | `/api/jobs/{id}` | 작업 상태 조회 |
| POST | `/api/jobs/{id}/cancel` | 실행 중인 작업 취소 |

### Lamp 엔드포인트 (`/api/lamp`)

| 메서드 | 엔드포인트 | 설명 |
|--------|----------|------|
| POST | `/parse` | 업로드된 요구사항 파싱 |
| POST | `/generate` | Genie Space 설정 생성 |
| POST | `/validate` | Unity Catalog 대비 검증 |
| POST | `/validate/fix` | 수정 적용 후 재검증 |
| POST | `/deploy` | Databricks에 배포 |
| POST | `/benchmark/validate` | 벤치마크 쿼리 검증 |
| GET | `/files/{session}/{file}` | 파일 내용 조회 |
| GET | `/download/config/{session}` | 설정 JSON 다운로드 |

### Enhancer 엔드포인트 (`/api/enhancer`)

| 메서드 | 엔드포인트 | 설명 |
|--------|----------|------|
| GET | `/workspace/warehouses` | SQL Warehouse 목록 조회 |
| GET | `/workspace/spaces` | Genie Space 목록 조회 |
| POST | `/jobs/score` | 점수 측정 작업 시작 |
| POST | `/jobs/plan` | 계획 수립 작업 시작 |
| POST | `/jobs/apply` | 수정안 적용 |
| POST | `/sessions/{id}/auto-loop` | 자동 루프 시작 |
| GET | `/iterations/{id}` | 반복 상태 조회 |
| POST | `/iterations/{id}/approve` | 수정안 승인 및 적용 |
| POST | `/sessions/{id}/upload` | 벤치마크 파일 업로드 |
| GET | `/benchmarks/template` | 벤치마크 템플릿 조회 |

## 데이터베이스 스키마

AutoGenie는 다음 테이블 구조의 SQLite를 사용합니다:

### `autogenie_sessions`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| session_id | TEXT PK | 고유 세션 식별자 |
| user_id | TEXT | 세션 생성 사용자 |
| name | TEXT | 세션 표시 이름 |
| workflow_type | TEXT | 'lamp' 또는 'enhancer' |
| target_score | REAL | 목표 벤치마크 점수 (enhancer) |
| max_iterations | INT | 최대 개선 반복 횟수 |
| loop_status | TEXT | 자동 루프 상태 |
| deployed_space_id | TEXT | 배포된 Genie Space ID |

### `autogenie_jobs`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| job_id | TEXT PK | 고유 작업 식별자 |
| session_id | TEXT FK | 상위 세션 |
| type | TEXT | 작업 유형 (parse, generate, score 등) |
| status | TEXT | pending, running, completed, failed |
| inputs | JSON | 작업 입력 파라미터 |
| result | JSON | 작업 출력/결과 |
| progress | JSON | 진행 이벤트 |

### `autogenie_iterations`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| iteration_id | TEXT PK | 고유 반복 식별자 |
| session_id | TEXT FK | 상위 세션 |
| iteration_number | INT | 반복 순서 번호 |
| score_before | REAL | 시작 시 점수 |
| score_after | REAL | 수정 적용 후 점수 |
| fixes_proposed | JSON | LLM 제안 수정안 |
| fixes_applied | JSON | 사용자 승인 수정안 |

## 프로젝트 구조

```
AutoGenie/
├── app.yaml                    # Databricks Apps 설정
├── databricks.yml              # Databricks Asset Bundle 설정
├── requirements.txt            # Python 의존성
├── backend/                    # FastAPI 서버
│   ├── main.py                 # 애플리케이션 진입점
│   ├── middleware/
│   │   └── auth.py             # 인증 (OBO + 서비스 프린시펄)
│   ├── services/
│   │   ├── session_store.py    # SQLite 세션/작업 영속화
│   │   ├── job_manager.py      # 백그라운드 작업 생명주기
│   │   └── file_storage.py     # 로컬 파일 처리
│   ├── lamp/
│   │   ├── routes.py           # Lamp API 라우트 (/api/lamp/*)
│   │   ├── tasks.py            # Lamp 백그라운드 작업
│   │   └── benchmark_validator.py
│   └── enhancer/
│       ├── routes.py           # Enhancer API 라우트 (/api/enhancer/*)
│       ├── tasks.py            # Enhancer 백그라운드 작업
│       └── iteration_controller.py
├── genie/                      # Lamp 핵심 로직
│   ├── parsing/                # PDF/Markdown 파싱
│   ├── pipeline/               # 생성/검증/배포
│   ├── api/                    # Genie Space API 클라이언트
│   ├── llm/                    # Databricks LLM 클라이언트
│   ├── benchmark/              # 벤치마크 추출
│   └── validation/             # 테이블/SQL 검증
├── enhancer/                   # Enhancer 핵심 로직
│   ├── scoring/                # 벤치마크 점수 측정
│   ├── enhancement/            # 수정안 생성 및 적용
│   ├── api/                    # Space 운영
│   └── utils/                  # 유틸리티
├── prompts/                    # LLM 프롬프트 템플릿
├── generate_demo/              # 데모 데이터 생성
└── frontend/                   # Next.js 14 (정적 내보내기)
    ├── app/
    │   └── page.tsx            # 메인 탭 페이지
    ├── components/
    │   ├── TabNavigation.tsx   # 탭 전환
    │   ├── SessionSidebar.tsx  # 세션 목록
    │   ├── Stepper.tsx         # 워크플로우 스테퍼
    │   ├── lamp/               # Lamp 단계 컴포넌트
    │   └── enhancer/           # Enhancer 단계 컴포넌트
    └── lib/
        └── api-client.ts       # API 클라이언트
```

## 벤치마크 파일 형식

벤치마크는 다음 구조의 JSON 파일입니다:

```json
[
  {
    "question": "지난 달 총 매출은 얼마인가요?",
    "expected_sql": "SELECT SUM(revenue) FROM sales WHERE month = '2024-01'",
    "tags": ["매출", "월별"],
    "difficulty": "easy"
  }
]
```

### 필수 필드
- `question`: 자연어 질문
- `expected_sql`: 기대하는 SQL 쿼리

### 선택 필드
- `tags`: 분류용 카테고리
- `difficulty`: easy, medium, hard
- `expected_answer`: 검증용 기대 결과값

## 트러블슈팅

### 자주 발생하는 문제

**인증 오류 (401)**
- Databricks CLI 설정 확인: `databricks auth login`
- `DATABRICKS_HOST`가 올바르게 설정되었는지 확인
- 토큰 만료 여부 확인

**테이블 검증 실패**
- Unity Catalog 권한 확인
- 설정의 카탈로그/스키마 이름 확인
- 검증 수정 UI를 사용하여 참조 수정

**프론트엔드 로딩 안됨**
- frontend 디렉토리에서 `npm run build` 실행
- `FRONTEND_EXPORT_DIR`이 `frontend/out`을 가리키는지 확인
- 정적 파일 존재 여부 확인

**작업이 Running 상태에서 멈춤**
- 백엔드 로그에서 오류 확인
- 작업은 10분 후 타임아웃될 수 있음
- 취소 엔드포인트 사용: `POST /api/jobs/{id}/cancel`

## 개발

### 테스트 실행

```bash
# 백엔드 테스트
pytest tests/ -v

# 프론트엔드 테스트
cd frontend && npm test
```

### 새 Enhancement 카테고리 추가

1. `prompts/category_*.txt`에 프롬프트 템플릿 생성
2. `enhancer/enhancement/category_enhancer.py`에 카테고리 등록
3. `frontend/components/enhancer/PlanStep.tsx`에 UI 컨트롤 추가

### 파싱 지원 확장

1. `genie/parsing/`에 파서 추가
2. `genie/pipeline/parser.py`에 등록
3. 백엔드 라우트에 파일 타입 처리 업데이트
