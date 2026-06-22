# AI Agents

AX 관점에서 AI Agent는 LLM이 지시를 받고, 도구를 사용하고, 상태를 유지하고, 외부 시스템에 접근해 실제 작업을 수행하는 방식입니다.  
중요한 질문은 “어떤 에이전트가 똑똑한가”가 아니라, “어떤 구조가 안정적이고 안전하며 로컬 우선으로 운영 가능한가”입니다.

## Framework / SDK / ADK

### Framework

에이전트 흐름과 구조를 잡는 도구입니다.

- 예: LangGraph, AutoGen, CrewAI, Semantic Kernel
- 용도: 멀티 에이전트, 상태 관리, 워크플로우 제어, 인간 승인, 장기 실행 작업

### SDK

특정 모델 또는 플랫폼에 연결하기 위한 개발 도구 모음입니다.

- 예: OpenAI Agents SDK, 모델 제공사 SDK
- 용도: tool calling, handoff, guardrails, structured output

### ADK

에이전트 개발에 특화된 도구 묶음입니다.

- 예: Google ADK
- 용도: 에이전트 생성, 디버깅, 평가, 배포, 멀티 에이전트 운영

## 주요 분류

### Orchestration Framework

- LangGraph
- AutoGen
- CrewAI
- Semantic Kernel

적합한 경우:

- 상태가 필요한 워크플로우
- 장시간 실행되는 작업
- human-in-the-loop 승인
- 여러 에이전트 협업

### Model Provider SDK

- OpenAI Agents SDK
- Gemini / Google 계열 도구
- Anthropic 계열 도구

적합한 경우:

- 빠른 연동
- 모델별 기능 활용
- 구조화된 출력
- tool calling

### Enterprise ADK

- Google ADK
- Microsoft Agent Framework 방향

적합한 경우:

- 프로덕션 배포
- 관측성
- 평가
- 멀티 에이전트 운영

### Local Action Agent

- OpenClaw
- Hermes Agent
- OpenHands
- 로컬 코딩 에이전트

적합한 경우:

- 로컬 파일 작업
- 브라우저 자동화
- 메신저 연동
- 실제 업무 수행

## 주요 도구 요약

| 도구 | 유형 | 적합한 용도 | AX 관점 |
| --- | --- | --- | --- |
| LangGraph | Orchestration framework | 상태 기반, 장기 실행 에이전트 | 매우 적합 |
| LangChain | LLM app framework | 도구, RAG, 연결성 | 보조 레이어로 유용 |
| Google ADK | Agent Development Kit | 기업용 에이전트 시스템 | 참고 가치 큼 |
| OpenAI Agents SDK | SDK | tools, handoffs, guardrails | 클라우드/하이브리드용 |
| AutoGen | Multi-agent framework | 에이전트 협업 실험 | 연구 참고용 |
| Semantic Kernel | Enterprise orchestration SDK | Microsoft 생태계 | 환경에 따라 유용 |
| CrewAI | Multi-agent framework | 빠른 프로토타입 | 데모용 |
| OpenHands | Software agent SDK | 코딩 에이전트 | 개발 자동화 참고 |
| OpenClaw | Local action agent | 로컬 자동화 | 참고 가능 |
| Hermes Agent | Self-hosted agent | 개인형 에이전트 | 연구 옵션 |

## 핵심 후보

### LangGraph

AX에 가장 중요한 후보입니다. 상태가 있는 장기 실행 에이전트, 인간 승인, 메모리, 복구 가능한 흐름에 강합니다.

- 장점: 생산 환경에 맞음, 상태 관리가 좋음, human-in-the-loop 구성 가능
- 단점: 구현 부담이 있음, 데모용으로는 다소 무거움

### Google ADK

기업용 에이전트 개발과 배포 관점에서 참고할 만합니다.

- 장점: 생산 중심, 멀티 에이전트 지원, 디버깅과 배포 방향이 명확함
- 단점: 특정 클라우드 생태계로 기울 수 있음

### OpenAI Agents SDK

tool, handoff, guardrails, structured output 중심의 에이전트 구성에 적합합니다.

- 장점: 구성이 깔끔함, 모델 연동이 쉬움
- 단점: 클라우드 중심이기 쉬움

### AutoGen

현재는 유지보수 모드이므로 새 프로젝트의 핵심으로 두기에는 적절하지 않습니다.

- 장점: 멀티 에이전트 패턴 참고 가능
- 단점: 새 기능 중심의 코어로는 부적합

## Nextor AX 권장 방향

AX는 하나의 프레임워크에 전부 의존하기보다, 역할을 나누는 구조가 더 적합합니다.

```text
User Interface
- Slack Bot
- Telegram Bot
- Web Dashboard

Agent API Layer
- Auth
- Permission
- Audit Log

Agent Orchestrator
- LangGraph
- Custom AX Core

Agent Layer
- PM Agent
- QA Agent
- Dev Agent
- Ops Agent
- Data Agent
- Security Agent

Model Router
- Local SLLM
- Local LLM
- Optional Cloud LLM

Tool Layer
- Files
- Database
- Git
- ERP / CRM
- Browser
- Company APIs
```

## 권장 스택

| 레이어 | 선택 |
| --- | --- |
| Core orchestration | LangGraph |
| Tool / RAG support | LangChain |
| Local inference | Ollama 우선, vLLM 확장 |
| Cloud escalation | OpenAI Agents SDK 또는 Gemini API |
| Enterprise reference | Google ADK |
| Coding agent research | OpenHands |
| UX | Web dashboard + Slack / Telegram |
| Governance | Custom AX approval / audit layer |

## 결론

AX는 “에이전트를 하나 고르는 문제”가 아니라,  
“로컬 우선, 승인 기반, 보안 중심의 업무용 AI 운영 구조를 만드는 문제”로 보는 것이 맞습니다.

권장 방향은 다음과 같습니다.

> LangGraph를 중심 오케스트레이터로 두고,  
> AX 전용 governance layer를 얹고,  
> 로컬 모델과 클라우드 모델을 model router로 분리해서 지원한다.

이 구조가 다음을 동시에 만족합니다.

- 로컬 우선
- 비용 절감
- 데이터 보호
- 인간 승인
- 멀티 에이전트 협업
- 벤더 종속 최소화
