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

당신은 소프트웨어 엔지니어입니다. 결제 도메인을 구현한다고 할 때, 무엇이 떠오르나요? 아마 "Paddle"이나 "Stripe"일 겁니다.

하지만 Claude Code 같은 도구는 관련 코드를 자연스럽게 찾아내지 못합니다. 의미적 연결 자체가 존재하지 않기 때문입니다. Claude에게 "Payment"와 "Stripe"는 완전히 다른 세계에 살고 있습니다.

그래서 할 수 있는 유일한 일만 반복합니다 — "Payment"라는 단어를 계속 grep하는 것.

**hedwig-kg**는 이 문제를 해결합니다. 코드베이스에서 지식 그래프를 구축하고 — 함수, 클래스, import, 호출 그래프, 상속, 커뮤니티 — 사람이 생각하는 방식과 비슷하게 의미적으로 검색합니다.

"결제 관련 코드 찾아봐"라고 하면, "payment"라는 단어가 없어도 `StripeClient`, `checkout_handler`, `WebhookController`를 찾아냅니다.

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

### HybridRAG 검색 (5개 신호)

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
