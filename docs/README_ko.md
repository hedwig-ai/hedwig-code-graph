<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    AI 코딩 에이전트를 위한 로컬 우선 지식 그래프 빌더
    <br />
    <a href="#빠른-시작">빠른 시작</a> · <a href="#지원-언어">언어</a> · <a href="#ai-에이전트-통합">통합</a> · <a href="#아키텍처">아키텍처</a> · <a href="../README.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## 왜 hedwig-kg인가?

클로드 코드로 개발할 때, 뭔가 아쉬운 점 느끼지 않으셨나요?

결제 시스템을 만들 때, 우리는 자연스럽게 전체 맥락을 봅니다 — 카드, 청구, 환불, 사기 탐지가 하나의 흐름으로 연결되어 있죠. 하지만 코딩 에이전트는 "Payment"를 검색해서 `payment_service.py`만 찾습니다. 같은 트랜잭션 흐름에 있는 `fraud_detector.py`나 `billing_engine.py`는 파일명에 "payment"가 없으니 보이지 않습니다.

지식 그래프가 있으면 달라집니다. `PaymentService` → `CardValidator` → `FraudDetector` → `BillingEngine` — 코드 간의 관계를 따라가며 에이전트도 전체 맥락을 볼 수 있게 됩니다.

hedwig-kg를 쓰면 코딩 에이전트가 키워드 매칭이 아닌, 사람처럼 연결고리를 따라 탐색합니다. 토큰은 줄고, 결과는 좋아지고, 기존에 찾지 못하던 코드까지 발견합니다.

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## 빠른 시작

```bash
pip install hedwig-kg
hedwig-kg claude install
```

그리고 Claude Code에게 말하세요:

> "이 프로젝트의 지식 그래프를 빌드해"

끝입니다. Claude Code가 그래프를 빌드하고, 이후 모든 검색에서 자동으로 참조합니다. 코드가 변경되면:

> "지식 그래프 다시 빌드해"

## 지원 언어

### 심층 AST 추출 (17개 언어)

hedwig-kg는 [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html)을 사용하여 범용 구조 추출을 수행합니다 — 함수, 클래스, 메서드, 호출, import, 상속 — 언어별 커스텀 코드 없이.

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | | | |

추가로 탐지 및 인덱싱: Markdown, PDF, HTML, CSV, YAML, JSON, TOML, Shell, R 등.

### 다국어 자연어 지원

텍스트 노드(문서, 주석, 마크다운)는 `intfloat/multilingual-e5-small`로 임베딩되어 **100개 이상의 자연어**를 지원합니다 — 한국어, 일본어, 중국어, 독일어, 프랑스어 등. 원하는 언어로 검색하면 모든 언어의 결과를 찾습니다.

## AI 에이전트 통합

hedwig-kg는 주요 AI 코딩 에이전트와 한 명령어로 통합됩니다:

| 에이전트 | 설치 | 설명 |
|---------|------|------|
| **Claude Code** | `hedwig-kg claude install` | Skill + CLAUDE.md + PreToolUse 훅 |
| **Codex CLI** | `hedwig-kg codex install` | AGENTS.md + PreToolUse 훅 |
| **Gemini CLI** | `hedwig-kg gemini install` | GEMINI.md + BeforeTool 훅 |
| **Cursor IDE** | `hedwig-kg cursor install` | `.cursor/rules/` 규칙 파일 |
| **Windsurf IDE** | `hedwig-kg windsurf install` | `.windsurf/rules/` 규칙 파일 |
| **Cline** | `hedwig-kg cline install` | `.clinerules` 파일 |
| **Aider CLI** | `hedwig-kg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP 서버** | `claude mcp add hedwig-kg -- hedwig-kg mcp` | Model Context Protocol 5개 도구 |

각 `install`은 컨텍스트 파일 작성과 (지원하는 플랫폼의 경우) 도구 호출 전 훅 등록을 수행합니다. 제거: `hedwig-kg <platform> uninstall`.

---

## 아키텍처

```
소스 코드/문서
       |
       v
   탐지 ──> 추출 ──> 빌드 ──> 임베딩 ──> 클러스터 ──> 분석 ──> 저장
            tags.scm  NetworkX   듀얼      Leiden      PageRank   SQLite
            (17개)    DiGraph    FAISS     계층구조    갓노드     FTS5+FAISS
```

### 하이브리드 검색 (5개 신호)

1. **코드 벡터** — `BAAI/bge-small-en-v1.5`로 코드 노드 임베딩, FAISS 코사인 검색
2. **텍스트 벡터** — `intfloat/multilingual-e5-small`로 텍스트 노드 임베딩 (100+ 언어)
3. **그래프 확장** — 벡터 히트에서 BFS, 엣지 품질로 가중 (calls > imports > contains)
4. **키워드** — FTS5 전문 검색, 전체 소스 코드 대상 (스니펫 제한 없음)
5. **커뮤니티** — Leiden 클러스터링 요약이 관련 노드를 부스트
6. **RRF 융합** — 가중 역순위 융합이 모든 신호를 결합

## 성능

hedwig-kg 자체 코드베이스 기준 벤치마크 (~3,500줄, 90개 파일, 1,300개 노드):

| 연산 | 시간 |
|------|------|
| 전체 빌드 | ~14초 |
| 증분 빌드 (변경 있음) | ~4초 |
| 증분 빌드 (변경 없음) | ~0.4초 |
| 콜드 검색 (듀얼 모델) | ~2.8초 |
| 콜드 검색 (`--fast`) | ~0.2초 |
| 웜 검색 | ~0.08초 |
| 캐시 히트 | <1ms |

## 요구사항

- Python 3.10+
- 임베딩 모델 ~470MB (첫 사용 시 캐시)

## 라이선스

MIT License. [LICENSE](../LICENSE) 참조.

## 기여

기여를 환영합니다! [CONTRIBUTING.md](../CONTRIBUTING.md) 참조.
