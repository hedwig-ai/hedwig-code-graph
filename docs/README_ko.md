<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    AI 코딩 에이전트를 위한 로컬 우선 지식 그래프 빌더
    <br />
    <a href="#ai-코딩-에이전트-통합">통합</a> · <a href="#빠른-시작">빠른 시작</a> · <a href="#아키텍처">아키텍처</a> · <a href="../README.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

---

**hedwig-kg**는 소스 코드와 문서로부터 지식 그래프를 구축하고, 듀얼 임베딩 모델(코드 특화 + 자연어 특화)을 활용한 **5-시그널 HybridRAG 검색**을 RRF 융합으로 제공합니다. 모든 것이 **100% 로컬**에서 실행됩니다.

## AI 코딩 에이전트 통합

한 줄 명령으로 주요 AI 코딩 에이전트와 통합할 수 있습니다. 각 통합은 플랫폼별 컨텍스트 파일과 hook을 작성하여 에이전트가 원시 파일 검색 전에 지식 그래프를 자동으로 활용합니다.

```bash
pip install hedwig-kg
```

### Claude Code

```bash
hedwig-kg claude install
```

`CLAUDE.md` 섹션 + `.claude/settings.json` PreToolUse hook을 작성합니다.

### OpenAI Codex CLI

```bash
hedwig-kg codex install
```

`AGENTS.md` 섹션 + `.codex/hooks.json` PreToolUse hook을 작성합니다.

### Google Gemini CLI

```bash
hedwig-kg gemini install
```

`GEMINI.md` 섹션 + `.gemini/settings.json` BeforeTool hook을 작성합니다.

### Windsurf IDE

```bash
hedwig-kg windsurf install
```

`.windsurf/rules/hedwig-kg.md` 규칙 파일을 생성합니다.

### Cline (VS Code 확장)

```bash
hedwig-kg cline install
```

`.clinerules` 파일을 생성합니다.

### 동작 방식

각 `install` 명령은 두 가지를 수행합니다:

1. **컨텍스트 파일** — 플랫폼의 컨텍스트 파일에 `## hedwig-kg` 섹션을 추가
2. **Hook** — 도구 호출 전에 실행되는 경량 셸 hook을 등록

제거: `hedwig-kg <platform> uninstall`

### 요구사항

- Python 3.10+
- 기본 임베딩 모델을 위한 ~500MB 디스크 공간 (첫 사용 시 다운로드)

### 선택적 의존성

```bash
# PDF 텍스트 추출
pip install hedwig-kg[docs]
```

## 빠른 시작

### 1. 설치 및 빌드

```bash
pip install hedwig-kg
cd ./my-project
hedwig-kg build .
```

첫 빌드는 모든 파일을 스캔하고, AST 구조를 추출하며, 임베딩을 생성하고 (~80MB 모델 첫 다운로드), 커뮤니티를 감지하여 `.hedwig-kg/knowledge.db`에 저장합니다.

### 2. 검색

```bash
hedwig-kg search "인증 핸들러"
```

### 3. 에이전트 통합

```bash
hedwig-kg claude install        # Claude Code
hedwig-kg codex install         # Codex CLI
hedwig-kg gemini install        # Gemini CLI
hedwig-kg windsurf install      # Windsurf IDE
hedwig-kg cline install         # Cline (VS Code)
```

### 4. 최신 상태 유지

```bash
hedwig-kg build . --incremental
```

### 5. 탐색

```bash
hedwig-kg stats                           # 그래프 개요
hedwig-kg communities --search "auth"     # 커뮤니티 탐색
hedwig-kg node "AuthHandler"              # 노드 상세
hedwig-kg query                           # 대화형 REPL
hedwig-kg visualize                       # HTML 시각화
```

## 아키텍처

```
소스 코드/문서 → 탐지 → 추출 → 그래프 구축 → 임베딩 → 클러스터링 → 요약 → 분석 → 저장
```

### HybridRAG 검색 (5 시그널)

1. **코드 벡터 검색** — `BAAI/bge-small-en-v1.5`로 쿼리를 임베딩, 코드 노드(함수, 클래스, 메서드) FAISS 검색
2. **텍스트 벡터 검색** — `all-MiniLM-L6-v2`로 쿼리를 임베딩, 문서 노드(제목, 섹션, 독스트링) FAISS 검색
3. **그래프 확장** — 상위 벡터 결과에서 N-홉 이웃 순회
4. **키워드 검색** — FTS5 전문 검색 (BM25 랭킹)
5. **커뮤니티 검색** — 커뮤니티 요약과 쿼리 매칭
5. **RRF 융합** — 모든 시그널을 통합 랭킹으로 결합

## 라이선스

MIT License. 자세한 내용은 [LICENSE](../LICENSE)를 참조하세요.
