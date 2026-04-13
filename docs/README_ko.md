<p align="center">
<img width="2048" height="1138" alt="hegwid-cg" src="https://github.com/user-attachments/assets/2875669b-e7e3-45df-9e50-90110e2abbf1" />
<h1 align="center">hedwig-cg</h1>
  <p align="center">
    "With hedwig-cg, your coding agent knows what to read."
    <br />
    <a href="#빠른-시작">빠른 시작</a> · <a href="../README.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
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

> raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki - Andrej Karpathy

hedwig-cg는 10,000개 이상의 파일을 가진 코드베이스와 지식 문서들로부터, 경량 로컬 LLM 모델을 사용하여 질의 가능한 코드 그래프와 지식 베이스를 구축합니다. Two-Stage 5-신호 하이브리드 검색(벡터 + 그래프 + 키워드 + 커뮤니티 → RRF 퓨전 → Cross-Encoder 리랭킹)으로 코딩 에이전트가 프로젝트 전체를 진정으로 이해할 수 있게 됩니다. 설치하면 Claude Code가 전체 그림을 볼 수 있습니다 — 추가적인 토큰도, 추가적인 명령도 필요 없으며, 모든 것이 100% 로컬에서 실행됩니다.

## 빠른 시작

```bash
pip install hedwig-cg

cd your-project/
hedwig-cg claude install
```

그리고 Claude Code에게 말하세요:

> "이 프로젝트의 코드 그래프를 빌드해"

끝입니다. Claude Code가 그래프를 빌드하고, 이후 모든 검색에서 자동으로 참조합니다. 세션이 끝나면 그래프가 자동으로 리빌드됩니다.

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

## 지원 언어

### 구조 추출 (20개 이상 언어)

hedwig-cg는 tree-sitter와 네이티브 파서를 사용하여 함수, 클래스, 메서드, 호출, import, 상속을 추출합니다.

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | Terraform/HCL | | |

설정 및 문서 포맷도 구조 추출 지원: YAML, JSON, TOML, Markdown, PDF, HTML, CSV, Shell, R 등.

### 다국어 자연어 지원

텍스트 노드(문서, 주석, 마크다운)는 `intfloat/multilingual-e5-small`로 임베딩되어 **100개 이상의 자연어**를 지원합니다 — 한국어, 일본어, 중국어, 독일어, 프랑스어 등. 원하는 언어로 검색하면 모든 언어의 결과를 찾습니다.

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

### 100% 로컬

클라우드 서비스 없음, API 키 없음, 텔레메트리 없음. SQLite + FAISS로 저장, sentence-transformers로 임베딩. 모든 데이터가 로컬에 유지됩니다.

---

## 2단계 하이브리드 검색

모든 쿼리는 2단계 파이프라인을 거칩니다:

**1단계 — 5-신호 검색** (RRF 융합)

| 신호 | 찾는 것 |
|------|---------|
| **코드 벡터** | 의미적으로 유사한 코드 |
| **텍스트 벡터** | 100+ 언어의 문서와 주석 |
| **그래프 확장** | 구조적으로 연결된 노드 (호출자, 임포트) |
| **전문 검색** | 정확한 키워드 매칭 (BM25) |
| **커뮤니티 컨텍스트** | 같은 클러스터의 관련 노드 |

**2단계 — Cross-Encoder 리랭킹**

Cross-Encoder 모델이 후보를 재평가하여 구현 코드를 테스트/문서 노드보다 상위로 올립니다. 결과에는 노드 간 관계 엣지가 포함됩니다.

## CLI 레퍼런스

모든 명령은 기본적으로 간결한 JSON을 출력합니다 (AI 에이전트 소비용으로 설계).

| 명령 | 설명 |
|------|------|
| `build <dir>` | 코드 그래프 빌드 (`--incremental`) |
| `search <query>` | Two-Stage 5-신호 하이브리드 검색 (`--top-k`, `--fast`, `--expand`) |
| `search-vector <query>` | 벡터 유사도 전용 검색 (코드 + 텍스트 듀얼 모델) |
| `search-graph <query>` | 그래프 확장 전용 검색 (벡터 시드에서 BFS) |
| `search-keyword <query>` | FTS5 키워드 매칭 전용 검색 (BM25 랭킹) |
| `search-community <query>` | 커뮤니티 클러스터 매칭 전용 검색 |
| `query` | 대화형 검색 REPL |
| `communities` | 커뮤니티 목록 및 검색 (`--search`, `--level`) |
| `stats` | 그래프 통계 |
| `node <id>` | 퍼지 매칭으로 노드 상세 정보 |
| `export` | JSON, GraphML, D3.js로 내보내기 |
| `visualize` | 대화형 HTML 시각화 |
| `clean` | .hedwig-cg/ 데이터베이스 삭제 |
| `doctor` | 설치 상태 점검 |
| `mcp` | MCP 서버 시작 (stdio) |
| `claude install\|uninstall` | Claude Code 통합 관리 |
| `codex install\|uninstall` | Codex CLI 통합 관리 |
| `gemini install\|uninstall` | Gemini CLI 통합 관리 |
| `cursor install\|uninstall` | Cursor IDE 통합 관리 |
| `windsurf install\|uninstall` | Windsurf IDE 통합 관리 |
| `cline install\|uninstall` | Cline 통합 관리 |
| `aider install\|uninstall` | Aider CLI 통합 관리 |

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

- **임베딩 모델**: ~470MB, `~/.hedwig-cg/models/`에 한 번만 다운로드
- **데이터베이스**: ~2MB (SQLite + FTS5 + FAISS 인덱스)
- **증분 빌드**: SHA-256 해싱, 전체 빌드 대비 95%+ 빠름

## 요구사항

- Python 3.10+
- 임베딩 모델 ~470MB (첫 사용 시 캐시)

```bash
# 선택사항: PDF 추출
pip install hedwig-cg[docs]
```

## 개발

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_cg/
```

## 라이선스

MIT License. [LICENSE](../LICENSE) 참조.

## 기여

기여를 환영합니다! [CONTRIBUTING.md](../CONTRIBUTING.md) 참조.
