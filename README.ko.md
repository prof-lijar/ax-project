# AX Project · Nexgent

[English](README.md) | **한국어**

AX Project는 Nextor.ai의 기존 제품과 업무에 AI 및 AI 에이전트를 도입하기 위한 프로젝트입니다. 이 저장소의 주요 애플리케이션인 **Nexgent**는 대화형 어시스턴트, 지식 검색, 리서치, 돌봄 서비스 보고서, 파일 관리를 로그인 기반의 운영 화면에서 제공합니다.

저장소에는 요구사항 분석, 아키텍처·설계 자료, 별도의 스케줄링 프로토타입도 포함되어 있습니다. 일부 기능은 **안심지키미(Ansimk)** 스마트 돌봄 서비스와 연동되므로 해당 서비스의 기존 인프라에 접근할 수 있어야 합니다.

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [저장소 구조](#저장소-구조)
- [사전 요구사항](#사전-요구사항)
- [개발 환경 설정](#개발-환경-설정)
- [환경 설정 참조](#환경-설정-참조)
- [운영 환경 및 관리](#운영-환경-및-관리)
- [개발 및 테스트](#개발-및-테스트)
- [문제 해결](#문제-해결)
- [관련 문서](#관련-문서)

## 주요 기능

| 영역 | 구현된 기능 |
| --- | --- |
| AX Chat | 스트리밍 대화, 영구 저장되는 대화 기록, 문서·이미지 첨부, OpenAI 호환 모델 연동. |
| Knowledge / RAG | 문서·텍스트 수집, PostgreSQL/pgvector 기반 벡터 검색, 검색 결과를 활용하는 대화 워크플로. RAG API는 별도로 실행합니다. |
| Weekly Reporter | 안심지키미 돌봄 대상자 보고서, 백그라운드 일괄 처리, 작업 진행 상태, ZIP 내보내기, 데이터베이스 저장, 예약 실행. |
| Scout | 공개 웹 자료를 검색하고 Markdown 보고서와 실행 산출물을 저장하는 Google ADK 리서치 에이전트. 예약 실행에는 별도 서비스가 필요합니다. |
| 파일 | Nextcloud 연동과 사용자별 비공개 저장소. 폴더, 업로드, 다운로드, 미리보기, 휴지통, 복원을 지원합니다. |
| Sumin | Slack 업로드 파일의 Nextcloud 보관 및 봇 멘션을 통한 채널 범위 파일 검색. |
| 계정 | 로그인, 계정 설정, 관리자 접근 권한 관리, 한국어·영어 인터페이스. |
| 알림 | 영구 저장되는 Slack 알림 작업 및 별도 전송 워커. |

로그인한 일반 사용자는 Chat, 파일, 계정 설정, 에이전트 목록을 이용할 수 있습니다. Knowledge와 Scout·Weekly Reporter를 포함한 에이전트 작업 화면은 관리자 권한이 필요합니다. 자세한 내용은 [접근 정책](nexgent/docs/08-implementation/admin-only-knowledge-agent-pages.md)을 참고하세요.

## 아키텍처

![시스템 아키텍처](nexgent/docs/03-architecture/diagrams/system-architecture.ko.svg)

[다이어그램 원본](nexgent/docs/03-architecture/diagrams/system-architecture.ko.mmd)

브라우저는 동일 출처의 백엔드 경로를 사용합니다. 백엔드는 인증을 적용하고 사전에 정해진 내부 서비스로 요청을 전달합니다. 채팅·알림 워커는 API와 별도로 실행됩니다. 기본 Compose 파일은 Agent Server를 내부 네트워크에만 노출합니다. 현재 `langgraph dev` 런타임은 메모리 기반이며 자체 인증이 없습니다. 제품의 영구 대화 기록은 이 런타임과 별개로 백엔드가 저장합니다.

프런트엔드는 React 18, TypeScript, Vite를 사용합니다. Tauri 2/Rust 데스크톱 셸도 포함되어 있으나 Docker 프런트엔드는 브라우저 애플리케이션을 실행합니다. Python 서비스는 역할에 따라 FastAPI, LangGraph, Google ADK를 사용합니다.

## 저장소 구조

```text
ax-project/
├── nexgent/                         주요 애플리케이션
│   ├── frontend/                    React 웹 UI 및 Tauri 데스크톱 셸
│   ├── backend/                     API, 인증, 마이그레이션, 워커
│   ├── agents/                      LangGraph 서비스 및 업무 워크플로
│   │   ├── apps/                    API, 스케줄러, 워커
│   │   ├── workflows/               Chat, RAG, 보고서, Sumin 등
│   │   ├── packages/                공통 계약, 도구, 연동, 런타임
│   │   └── tests/                   단위·계약·통합 테스트 및 평가
│   ├── adk_agents/                  Scout 및 실험용 ADK 에이전트
│   ├── RAG/                         검색 API, 수집, pgvector, 평가
│   ├── docs/                        제품·아키텍처·구현 기록
│   ├── compose.yaml                 개발 스택
│   └── compose.prod.yaml            안정 버전 운영 스택
├── scheduling-agent-poc/            별도 스케줄링 서비스 및 프로토타입
├── requirement_analysis/            초기 요구사항 및 구현 단계
├── project안심지키미/                  돌봄 서비스 워크플로 자료
└── *.md, *.pdf, *.png               프로젝트 메모, 설계, 참고 자료
```

## 사전 요구사항

컨테이너 실행에 필요한 항목은 다음과 같습니다.

- Docker Engine 및 `include`, 선택적 `env_file` 항목을 지원하는 최신 Docker Compose v2. 포함된 Sumin 배포 구성은 Linux 호스트 네트워크를 사용합니다.
- 서명 키 설정 도우미를 실행할 Python 3.
- 접근 가능한 PostgreSQL 데이터베이스와 외부 Docker 네트워크 `nexgent-rag_default`. 로컬 개발에서는 포함된 RAG 데이터베이스 스택으로 둘 다 준비할 수 있습니다.
- 접근 가능한 OpenAI 호환 모델 엔드포인트 및 인증 정보.
- 기본 애플리케이션 스택의 의존 서비스인 주간 보고서 원본 API가 사용할 안심지키미 원본 데이터베이스.
- 파일 기능을 위한 Nextcloud 인증 정보. Sumin 및 알림·보고서 연동에는 Slack과 추가 데이터베이스 설정도 필요합니다.

컨테이너 밖에서 개발할 때는 프런트엔드 Docker 이미지와 동일한 Node.js 22 및 npm, 백엔드·LangGraph 코드용 Python 3.11 이상, `uv`를 사용합니다. Scout 컨테이너는 Python 3.12를 사용합니다. 데스크톱 빌드에는 Rust와 Tauri 네이티브 의존성도 필요합니다. [프런트엔드 안내](nexgent/frontend/README.md)를 참고하세요.

이 프로젝트는 외부 시스템과 연동되는 애플리케이션입니다. 예제 파일을 복사하는 것만으로 외부 서비스나 유효한 인증 정보가 준비되지는 않습니다.

## 개발 환경 설정

별도 안내가 없는 명령은 `nexgent/` 디렉터리에서 실행합니다.

```bash
cd nexgent
```

### 1. 로컬 설정 파일 생성

다음 명령은 기존 파일이 있으면 그대로 유지합니다.

```bash
test -f backend/dev.env || cp backend/example.env backend/dev.env
test -f agents/.env || cp agents/.env.example agents/.env
test -f adk_agents/ansimk_scout_agent/.env || cp adk_agents/ansimk_scout_agent/.env.example adk_agents/ansimk_scout_agent/.env
python3 backend/setup_env.py
```

서비스를 시작하기 전에 파일을 수정합니다.

- `backend/dev.env`: `NEXGENT_DATABASE_URL`, `NEXGENT_PUBLIC_URL`, Nextcloud용 `NC_*` 값을 설정합니다. 로컬 HTTP에서는 `NEXGENT_ALLOW_INSECURE_HTTP=true`를 사용합니다. 공개 URL은 포트를 포함하여 브라우저에서 접속하는 출처와 정확히 일치해야 합니다.
- `agents/.env`: 모델 URL, 모델 이름, API 키, 보고서 원본용 `ANSIMK_DATABASE_DSN`을 설정합니다. 보고서를 저장하려면 `WEEKLY_REPORT_STORAGE_DATABASE_DSN`도 필요합니다.
- Scout의 `.env`: `OPENAI_API_BASE`, `OPENAI_API_KEY`, `SCOUT_MODEL`을 설정합니다. 컨테이너에서 접근 가능한 주소를 사용하세요. 컨테이너 안의 `127.0.0.1`은 해당 컨테이너 자체입니다. `/etc/nexgent/`의 호스트 관리 Scout 환경 파일이 있으면 해당 값이 우선 적용됩니다.

실제 인증 정보가 들어 있는 환경 파일은 비공개로 관리하고, 저장소의 예제 파일을 설정 참조로 사용하세요.

### 2. PostgreSQL 준비

기존 데이터베이스와 네트워크가 준비되어 있으면 그대로 사용합니다. 새로운 로컬 데이터베이스가 필요하면 포함된 스택을 준비합니다.

```bash
test -f RAG/.env || cp RAG/.env.example RAG/.env
# 계속하기 전에 RAG/.env의 RAG_POSTGRES_PASSWORD를 설정합니다.
docker compose -f RAG/compose.yaml up -d
docker compose -f RAG/compose.yaml ps
```

이 명령은 `nexgent-rag_default` 네트워크와 pgvector PostgreSQL 서비스를 생성합니다. 기본 데이터베이스 이름은 `t`가 포함된 **`nextgent`**입니다. 애플리케이션 컨테이너에서는 `nexgent-rag-postgres-1:5432`, 호스트에서는 `127.0.0.1:5433`으로 접근합니다.

사용할 데이터베이스 역할에 맞는 SQLAlchemy URL을 `NEXGENT_DATABASE_URL`에 입력합니다.

```dotenv
NEXGENT_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@nexgent-rag-postgres-1:5432/nextgent
NEXGENT_PUBLIC_URL=http://localhost:5173
NEXGENT_ALLOW_INSECURE_HTTP=true
```

자리표시자를 실제 값으로 바꾸고 인증 정보의 특수 문자는 URL 인코딩하세요. 백엔드는 시작 시 Alembic 마이그레이션을 실행하므로 데이터베이스 역할에 필요한 스키마 권한이 있어야 합니다. 이 설정은 안심지키미 원본 데이터를 채우거나 RAG API를 시작하지 않습니다.

### 3. 애플리케이션 시작

Sumin을 제외한 UI와 의존 서비스, 채팅·알림·보고서 처리 서비스를 시작하려면 다음을 실행합니다.

```bash
docker compose up --build -d frontend chat-worker notification-worker weekly-report-worker
docker compose ps
curl --fail http://localhost:8000/health
```

전체 개발 스택을 실행하려면 먼저 `agents/.env`에 Sumin용 `AGENT_DATABASE_DSN`, Slack 봇·앱 토큰, Nextcloud 설정을 입력한 뒤 실행합니다.

```bash
docker compose up --build -d
```

전체 실행 명령에는 `sumin-migrate`, `sumin-events`, `sumin-worker`도 포함됩니다. Sumin 인증 정보가 없으면 해당 서비스가 실패합니다. [Sumin 설정 안내](nexgent/agents/workflows/sumin/README.md)를 참고하세요.

### 4. 최초 관리자 생성

백엔드가 정상 상태가 되면 최초 관리자가 아직 없는 데이터베이스에 한해 다음 명령을 실행합니다.

```bash
docker compose exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
```

안내에 따라 비밀번호를 입력한 후 <http://localhost:5173>에 접속하여 로그인합니다. 계정과 권한은 **설정(Settings)**에서 관리합니다. 기본 비밀번호는 제공하지 않습니다.

### 5. 필요한 별도 서비스 활성화

- **Knowledge / RAG 대화:** 별도 RAG API를 시작하고 백엔드의 `AX_RAG_SERVER_URL`, Agent Server의 `RAG_SERVER_BASE_URL`을 설정합니다. [RAG 서비스 안내](nexgent/RAG/docs/rag-server.md)를 참고하세요.
- **Scout 예약 실행:** 별도 스케줄링 API를 설정한 주소에서 시작합니다. 기본 호스트 포트는 `8092`입니다. [스케줄러 안내](scheduling-agent-poc/scheduling-agent/README.md)를 참고하세요.
- **Slack 알림:** 백엔드의 `NEXGENT_SLACK_*` 값을 설정합니다. [알림 안내](nexgent/docs/08-implementation/slack-notification-service.md)를 참고하세요.

## 환경 설정 참조

| 파일 / 범위 | 주요 설정 | 용도 |
| --- | --- | --- |
| `backend/dev.env` 또는 `backend/prod.env` | `NEXGENT_DATABASE_URL`, `NEXGENT_PUBLIC_URL`, `NEXGENT_AUTH_SIGNING_KEY` | 애플리케이션 DB, 브라우저 출처, 세션 서명. |
| 백엔드 환경 | `NC_URL`, `NC_USER`, `NC_PASS`, `NC_CA_BUNDLE` | Nextcloud 접근 및 선택적 사설 CA 신뢰 설정. |
| 백엔드 환경 | `AX_AGENT_SERVER_URL`, `AX_RAG_SERVER_URL`, `AX_SCOUT_URL`, `AX_SCOUT_SCHEDULER_URL` | 내부 서비스 주소. 일부 값은 Compose에서 지정합니다. |
| `agents/.env` | `URL` / `OPENAI_BASE_URL`, `MODEL` / `OPENAI_MODEL`, `OPENAI_API_KEY` | LangGraph 모델 연동. |
| `agents/.env` | `ANSIMK_DATABASE_DSN`, `WEEKLY_REPORT_STORAGE_DATABASE_DSN` | 보고서 원본 조회 및 저장 연결. |
| `agents/.env` | `AGENT_DATABASE_DSN`, `SUMIN_*` | Sumin DB, Slack, Nextcloud 연동. |
| Scout `.env` | `OPENAI_API_BASE`, `OPENAI_API_KEY`, `SCOUT_MODEL` | Scout 전용 모델 설정. |
| `RAG/.env` | `RAG_POSTGRES_*` | 검색 데이터베이스 연결. |
| 셸 또는 `nexgent/.env` | `FRONTEND_PORT`, `BACKEND_PORT`, `PROD_FRONTEND_PORT`, `PROD_BACKEND_PORT` | Compose 호스트 포트 변경. |
| 셸 또는 `nexgent/.env` | `SEARXNG_SECRET`, `WEEKLY_REPORT_JOB_PASSWORD` | Compose가 치환하는 서비스 비밀 값. 배포 시 개발 기본값을 교체합니다. |

Compose 변수 치환과 컨테이너의 `env_file` 로딩은 서로 다릅니다. 기본 Compose 파일에서 `${...}`로 참조하는 값은 셸 또는 `nexgent/.env`에 설정합니다. `agents/.env`에만 입력하면 Compose의 명시적 `environment` 값을 덮어쓰지 못할 수 있습니다. 전체 설정은 [backend/example.env](nexgent/backend/example.env)와 [agents/.env.example](nexgent/agents/.env.example)을 참고하세요.

## 운영 환경 및 관리

| 환경 | Compose 파일 | 프로젝트 | 프런트엔드 | 백엔드 상태 확인 |
| --- | --- | --- | --- | --- |
| 개발 | `compose.yaml` | `nexgent` | `http://localhost:5173` | `http://localhost:8000/health` |
| 안정 버전 운영 서버 | `compose.prod.yaml` | `nexgent-prod` | `http://localhost:5174` | `http://localhost:8001/health` |

백엔드 호스트 포트는 루프백에 바인딩됩니다. 다른 기기에서는 Docker 호스트의 프런트엔드 주소로 접속하고 공개 출처 설정도 맞춰야 합니다. 운영 프런트엔드는 Nginx로 빌드된 정적 파일을 제공하며, 백엔드는 개발용 소스 마운트와 자동 리로드 없이 실행됩니다.

`backend/example.env`를 바탕으로 `backend/prod.env`를 준비한 뒤 서명 키를 생성합니다.

```bash
python3 backend/setup_env.py --env-file prod.env
```

운영 데이터베이스, 공개 출처, 연동 인증 정보를 설정합니다. 공개 배포에는 HTTPS를 사용하세요. 운영과 개발은 `agents/.env`를 공유하므로 Compose 프로젝트를 나눠도 외부 데이터베이스, Slack 목적지, Nextcloud 저장소가 자동으로 분리되지는 않습니다.

운영 스택은 주간 보고서 스케줄러를 기본 활성화하며 `agents/playground/weekly-reporter/.env` 등 추가 환경 파일을 마운트합니다. 시작 전에 [예약 보고서 파이프라인](nexgent/agents/apps/weekly_report_scheduler/README.md)을 설정하세요. 개발 스케줄러는 `scheduled` 프로필로 활성화합니다. 실행 시각과 파이프라인 단계는 [실제 cron 정의](nexgent/agents/apps/weekly_report_scheduler/crontab) 및 스케줄러 안내를 확인하세요. Sumin은 개발 Compose 파일에 포함되지만 `compose.prod.yaml`에는 포함되지 않습니다.

설정을 완료한 뒤 실행합니다.

```bash
docker compose -f compose.prod.yaml up --build -d
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs -f
```

자주 사용하는 개발 환경 관리 명령입니다.

```bash
docker compose logs -f backend agent-server chat-worker
docker compose down
```

운영 환경에는 `-f compose.prod.yaml`을 추가합니다. `down`은 이름 있는 볼륨을 유지하지만 `down -v`는 삭제합니다. 데이터를 삭제하는 유지보수 전에는 애플리케이션 DB와 영구 파일을 백업하세요. 별도 RAG 스택은 독립적으로 시작·종료합니다.

## 개발 및 테스트

각 명령 블록은 저장소 루트에서 새 터미널을 열거나 루트로 돌아온 뒤 실행합니다.

**프런트엔드**

```bash
cd nexgent/frontend
npm ci
npm test
npm run build
npm run dev
```

로컬 Vite 서버는 기본적으로 `http://127.0.0.1:8000`으로 요청을 프록시합니다. 필요하면 `NEXGENT_BACKEND_TARGET`을 설정하세요. `5173` 포트에서 다른 서버를 실행하기 전에는 Docker 프런트엔드를 중지하거나 다른 포트를 사용합니다.

**백엔드**

```bash
cd nexgent/backend
uv sync --extra dev
uv run pytest
```

컨테이너 밖의 API·워커 실행, 마이그레이션, 환경 변수 로딩은 [백엔드 안내](nexgent/backend/README.md)를 참고하세요. 호스트에서 실행하는 프로세스에는 Docker 서비스 이름 대신 호스트에서 접근 가능한 주소가 필요합니다.

**LangGraph 서비스**

```bash
cd nexgent/agents
uv sync --dev
uv run pytest tests/unit tests/contract
uv run ruff check apps workflows packages tests
```

통합 테스트와 평가에는 추가 서비스, 데이터베이스, 모델이 필요할 수 있습니다. 실행 전에 해당 테스트 설정을 확인하세요. Scout와 스케줄러는 별도 환경과 테스트 모음을 사용하므로 각 구성요소의 README를 따릅니다.

기여하기 전에 해당 디렉터리에 적용되는 `AGENTS.md`를 읽으세요. Nexgent의 주요 구현·인프라 변경에는 `nexgent/docs/` 아래 날짜가 명시된 문서와 문서 색인 항목이 필요합니다.

## 문제 해결

| 증상 | 확인 사항 |
| --- | --- |
| `nexgent-rag_default`가 없음 | 설정된 `RAG/compose.yaml` 데이터베이스 스택을 시작하거나 기존 외부 네트워크·DB 구성을 복구합니다. |
| 백엔드가 시작 중 종료됨 | DB 연결, 스키마 권한, 서명 키, 마이그레이션 로그를 확인합니다. |
| 로그인 또는 변경 요청이 거부됨 | `NEXGENT_PUBLIC_URL`과 브라우저 출처가 정확히 일치하는지 확인합니다. 로컬 HTTP 허용 설정을 확인하고 인증 설정 변경 후 다시 로그인합니다. |
| Knowledge 또는 에이전트 화면에서 403 발생 | 관리자 계정을 사용합니다. 해당 경로는 서버에서도 권한을 검사합니다. |
| 채팅 또는 연동에서 502/503 발생 | 대상 서비스, 워커 로그, 모델 인증 정보, 컨테이너에서 접근 가능한 URL을 확인합니다. RAG와 Scout 스케줄러는 별도로 실행됩니다. |
| Sumin이 종료되거나 재시작됨 | `AGENT_DATABASE_DSN`, 두 Slack 토큰, Nextcloud 인증 정보, CA 파일 경로를 확인합니다. |
| 프런트엔드가 의존 서비스를 기다림 | `docker compose ps`와 Scout, Agent Server, 백엔드, 보고서 서비스 로그를 확인합니다. UI는 해당 서비스의 상태 확인을 기다립니다. |
| 보고서 접수 또는 내보내기 실패 | 산출물 볼륨과 디스크 여유 공간을 확인합니다. 기본 최소 여유 공간 설정은 10 GiB입니다. |

## 관련 문서

- [Nexgent 운영 개요](nexgent/README.md)
- [제품 및 구현 문서 색인](nexgent/docs/README.md)
- [에이전트 워크스페이스 및 아키텍처](nexgent/agents/README.md)
- [Scout 리서치 에이전트](nexgent/adk_agents/ansimk_scout_agent/README.md)
- [RAG 문서 색인](nexgent/RAG/docs/README.md)
- [스케줄링 서비스](scheduling-agent-poc/scheduling-agent/README.md)
- [초기 요구사항 분석](requirement_analysis/README.md)
- [AX 프로젝트 원본 배경 자료](ax_project.md)

과거 설계 문서에는 구현된 기능과 제안 단계의 기능이 함께 설명되어 있습니다. 배포 세부사항은 현재 Compose 파일, 환경 설정 예제, 코드, 주제별 구현 기록을 함께 확인하세요.
