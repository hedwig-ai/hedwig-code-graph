<p align="center">
  <h1 align="center">hedwig-cg</h1>
  <p align="center">
    "헤드위그는 반드시 소식을 가지고 돌아올 거예요"
    <br />
    <a href="#빠른-시작">빠른 시작</a> · <a href="#지원-언어">언어</a> · <a href="#ai-에이전트-통합">통합</a> · <a href="#기능">기능</a> · <a href="../README.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-code-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-cg/"><img src="https://img.shields.io/pypi/v/hedwig-cg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-code-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## 왜 hedwig-cg인가?

hedwig-cg는 코드, 문서, 의존성으로부터 하나의 통합된 코드 그래프를 구축합니다 — 코딩 에이전트가 키워드 검색이 아닌, 프로젝트 전체를 진정으로 이해할 수 있게 됩니다. AST 구조 추출과 LLM 시맨틱 강화를 통해 명시적 관계와 숨겨진 크로스 모듈 관계를 모두 자동으로 발견합니다.

<img width="1919" height="991" alt="Code Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## 빠른 시작

```bash
pip install hedwig-cg
hedwig-cg claude install
```

그리고 Claude Code에서:

```
/hedwig-cg build .
```

AST 추출 + LLM 시맨틱 강화가 자동으로 실행됩니다 — 구조적 관계(import, 호출, 상속)와 숨겨진 시맨틱 연결(디자인 패턴, 행동 의존성, 크로스 모듈 관계)을 한 번에 발견합니다. 코드가 변경되면:

```
/hedwig-cg build . --incremental
```

## 지원 언어

### 심층 AST 추출 (17개 언어)

hedwig-cg는 [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html)을 사용하여 범용 구조 추출을 수행합니다 — 함수, 클래스, 메서드, 호출, import, 상속 — 언어별 커스텀 코드 없이.

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

hedwig-cg는 주요 AI 코딩 에이전트와 한 명령어로 통합됩니다:

| 에이전트 | 설치 | 설명 |
|---------|------|------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse 훅 |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse 훅 |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool 훅 |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/` 규칙 파일 |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/` 규칙 파일 |
| **Cline** | `hedwig-cg cline install` | `.clinerules` 파일 |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP 서버** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | Model Context Protocol 5개 도구 |

각 `install`은 컨텍스트 파일 작성과 (지원하는 플랫폼의 경우) 도구 호출 전 훅 등록을 수행합니다. 제거: `hedwig-cg <platform> uninstall`.

---

## 기능

### 자동 리빌드

AI 코딩 에이전트(Claude Code, Codex 등)와 통합 시, hedwig-cg는 코드 변경 시 **자동으로 그래프를 리빌드**합니다. Stop/SessionEnd 훅이 `git diff`로 변경된 파일을 감지하고 백그라운드에서 증분 빌드를 실행합니다 — 수동 작업이 필요 없습니다.

### 스마트 무시

세 가지 소스의 무시 패턴을 지원하며, 모두 **완전한 gitignore 스펙**(negation `!`, `**` 글로브, 디렉토리 전용 패턴)을 따릅니다:

| 소스 | 설명 |
|------|------|
| 기본 내장 | `.git`, `node_modules`, `__pycache__`, `dist`, `build` 등 |
| `.gitignore` | 프로젝트 루트에서 자동 읽기 — 기존 git ignore가 그대로 동작 |
| `.hedwig-cg-ignore` | 코드 그래프 전용 프로젝트별 오버라이드 |

### 증분 빌드

파일별 SHA-256 콘텐츠 해싱. 변경된 파일만 재추출 및 재임베딩합니다. 변경되지 않은 파일은 기존 그래프에서 병합 — 일반적으로 전체 빌드 대비 **95% 이상 빠릅니다**.

### 메모리 관리

4GB 메모리 예산과 단계별 해제. 파이프라인은 각 단계에서 생성 → 저장 → 해제: 추출 결과는 그래프 빌드 후 해제, 임베딩은 배치 단위로 스트리밍 후 DB 쓰기 후 해제, 전체 그래프는 영속화 후 해제됩니다. GC는 75% 임계값에서 선제적으로 트리거됩니다.

### 5-신호 하이브리드 검색

모든 검색 쿼리는 5개의 독립적인 검색 신호를 거친 후 가중 RRF로 단일 랭킹 결과로 융합됩니다:

| 신호 | 엔진 | 찾는 것 |
|------|------|---------|
| **코드 벡터** | FAISS + `bge-small-en-v1.5` | 의미적으로 유사한 코드 (함수, 클래스, 메서드) |
| **텍스트 벡터** | FAISS + `multilingual-e5-small` | 문서, 주석, 마크다운 (100+ 언어) |
| **그래프 확장** | NetworkX 가중 BFS | 구조적으로 연결된 노드 + INFERRED 엣지 |
| **전문 검색** | SQLite FTS5 + BM25 | 소스 코드 전체에서 정확한 키워드 매칭 |
| **커뮤니티 컨텍스트** | Leiden 계층 클러스터링 | 같은 기능 클러스터의 관련 노드 |

LLM 시맨틱 강화가 그래프 확장과 커뮤니티 신호를 강화합니다 — INFERRED 엣지가 AST만으로는 연결할 수 없는 노드 간 경로를 만듭니다.

### LLM 시맨틱 강화

AI 코딩 에이전트 안에서 빌드하면, 에이전트의 LLM이 코드 노드 배치를 병렬로 분석하여 INFERRED 엣지를 주입합니다 — 디자인 패턴, 행동 의존성, 크로스 모듈 연결 등 정적 분석으로는 탐지할 수 없는 관계를 발견합니다. 별도의 API 키가 필요 없습니다.

## 성능

hedwig-cg 자체 코드베이스 기준 벤치마크 (~3,500줄, 90개 파일, 1,300개 노드):

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
