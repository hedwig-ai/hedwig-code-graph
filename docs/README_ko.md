<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    로컬 우선 지식 그래프 빌더 — 4-시그널 HybridRAG 검색
    <br />
    <a href="#설치">설치</a> · <a href="#빠른-시작">빠른 시작</a> · <a href="#아키텍처">아키텍처</a> · <a href="../README.md">English</a> · <a href="README_ja.md">日本語</a>
  </p>
</p>

---

## hedwig-kg란?

**hedwig-kg**는 소스 코드와 문서를 분석하여 지식 그래프를 구축하고, 벡터 유사도 + 그래프 순회 + 키워드 매칭 + 커뮤니티 요약을 융합한 **4-시그널 HybridRAG 검색**을 제공합니다. 모든 것이 **100% 로컬**에서 실행되며, 클라우드 API를 사용하지 않습니다.

### 주요 기능

- **4-시그널 HybridRAG 검색** — 벡터 유사도 → 그래프 N-홉 확장 → FTS5 키워드 매칭 → 커뮤니티 요약 매칭 → RRF 융합
- **Tree-sitter AST 추출** — Python, JavaScript, TypeScript의 정확한 구조 파싱 (메서드→클래스 귀속, 상속 추적, 호출 그래프)
- **Markdown 문서 추출** — 헤딩을 섹션 노드로, 내부 링크를 참조 엣지로 변환
- **계층적 커뮤니티** — 다중 해상도 Leiden 클러스터링 + 자동 생성 키워드 요약
- **증분 빌드** — SHA-256 해시로 변경되지 않은 파일 스킵 (빠른 재빌드)
- **로컬 임베딩** — sentence-transformers 기반 프라이버시 보장 시맨틱 검색
- **SQLite + FTS5 + FAISS** — 단일 파일 데이터베이스에 전문 검색 + 벡터 인덱스 통합
- **20+ 언어 지원** — Python, JS/TS, Java, Go, Rust, C/C++, Ruby 등

## 설치

```bash
pip install hedwig-kg
```

또는 소스에서 설치:

```bash
git clone https://github.com/hedwig-ai/hedwig-knowledge-graph.git
cd hedwig-knowledge-graph
pip install -e .
```

## 빠른 시작

```bash
# 지식 그래프 구축
hedwig-kg build ./my-project

# 증분 재빌드 (변경되지 않은 파일 스킵)
hedwig-kg build ./my-project --incremental

# 4-시그널 하이브리드 검색
hedwig-kg search "인증 핸들러"

# 커뮤니티 탐색
hedwig-kg communities
hedwig-kg communities --search "auth"

# 대화형 탐색 (REPL — 그래프를 한 번 로드하고 연속 검색)
hedwig-kg query

# 통계 보기 (밀도, 클러스터링 계수, 연결 성분 포함)
hedwig-kg stats

# 노드 상세 보기 (퍼지 매칭 지원)
hedwig-kg node "AuthHandler"

# 그래프 내보내기
hedwig-kg export --format json
hedwig-kg export --format d3       # D3.js 호환 JSON

# 인터랙티브 시각화 (브라우저에서 열기)
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 -o my_graph.html

# 데이터베이스 삭제
hedwig-kg clean
hedwig-kg clean --yes              # 확인 없이 삭제
```

## 아키텍처

```
소스 코드 → 탐지 → 추출 → 그래프 구축 → 임베딩 → 클러스터링 → 요약 → 분석 → 저장
```

| 단계 | 설명 |
|------|------|
| **탐지** | 디렉토리 스캔, 20+ 언어 분류, `.hedwig-kg-ignore` 지원 |
| **추출** | Tree-sitter AST (Python/JS/TS), Markdown 헤딩/섹션 추출, 정규식 폴백 |
| **구축** | 3단계 중복 제거로 방향 그래프 조립 |
| **임베딩** | sentence-transformers 로컬 임베딩 생성 |
| **클러스터** | 다중 해상도 Leiden 계층적 커뮤니티 탐지 |
| **요약** | 노드 속성에서 키워드 풍부한 커뮤니티 요약 자동 생성 |
| **분석** | PageRank, 갓 노드, 허브 분석 |
| **저장** | SQLite + FTS5 전문 검색 + FAISS 벡터 인덱스 |

## 라이선스

MIT License. 자세한 내용은 [LICENSE](../LICENSE)를 참조하세요.
