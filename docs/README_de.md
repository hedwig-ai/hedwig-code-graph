<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    "Hedwig wird mit der Nachricht zurueckkommen"
    <br />
    <a href="#schnellstart">Schnellstart</a> · <a href="#unterstuetzte-sprachen">Sprachen</a> · <a href="#ai-agent-integrationen">Integrationen</a> · <a href="#architektur">Architektur</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## Warum hedwig-kg?

hedwig-kg analysiert Quellcode mit tree-sitter AST-Extraktion (17 Sprachen), erstellt einen Knowledge Graph auf NetworkX und bietet 5-Signal-Hybridsuche — Dual-Vektor (Code + Text), Graph-Expansion, FTS5-Keyword und Community-Zusammenfassung — fusioniert durch gewichtetes RRF. Agents fragen einen Endpunkt ab und erhalten gerankte Ergebnisse ueber Code, Dokumentation, Konfiguration und Tests. Alles laeuft 100% lokal auf SQLite + FAISS + sentence-transformers — keine Cloud-Dienste, keine Daten verlassen Ihren Rechner.

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## Schnellstart

```bash
pip install hedwig-kg
hedwig-kg claude install
```

Sagen Sie Claude Code:

> "Baue einen Knowledge Graph fuer dieses Projekt"

Das war's. Claude Code baut den Graph und konsultiert ihn ab sofort bei jeder Suche. Bei Code-Aenderungen:

> "Knowledge Graph neu bauen"

## Unterstuetzte Sprachen

### Tiefe AST-Extraktion (17 Sprachen)

hedwig-kg verwendet [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html) fuer universelle Strukturextraktion — Funktionen, Klassen, Methoden, Aufrufe, Imports, Vererbung — ohne sprachspezifischen Code.

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | | | |

Zusaetzlich erkannt und indiziert: Markdown, PDF, HTML, CSV, YAML, JSON, TOML, Shell, R und mehr.

### Mehrsprachige natuerliche Sprache

Textknoten (Dokumente, Kommentare, Markdown) werden mit `intfloat/multilingual-e5-small` eingebettet und unterstuetzen **100+ natuerliche Sprachen** — Deutsch, Koreanisch, Japanisch, Chinesisch, Franzoesisch und mehr. Suchen Sie in Ihrer Sprache, finden Sie Ergebnisse in jeder Sprache.

## AI-Agent-Integrationen

hedwig-kg integriert sich mit einem Befehl in fuehrende AI Coding Agents:

| Agent | Installation | Beschreibung |
|-------|-------------|-------------|
| **Claude Code** | `hedwig-kg claude install` | Skill + CLAUDE.md + PreToolUse-Hook |
| **Codex CLI** | `hedwig-kg codex install` | AGENTS.md + PreToolUse-Hook |
| **Gemini CLI** | `hedwig-kg gemini install` | GEMINI.md + BeforeTool-Hook |
| **Cursor IDE** | `hedwig-kg cursor install` | `.cursor/rules/`-Regeldatei |
| **Windsurf IDE** | `hedwig-kg windsurf install` | `.windsurf/rules/`-Regeldatei |
| **Cline** | `hedwig-kg cline install` | `.clinerules`-Datei |
| **Aider CLI** | `hedwig-kg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP-Server** | `claude mcp add hedwig-kg -- hedwig-kg mcp` | Model Context Protocol 5 Tools |

Jeder `install`-Befehl schreibt eine Kontextdatei und registriert (bei unterstuetzten Plattformen) einen Hook vor Tool-Aufrufen. Entfernen: `hedwig-kg <platform> uninstall`.

---

## Architektur

```
Quellcode/Dokumente
       |
       v
   Erkennen ──> Extrahieren ──> Bauen ──> Einbetten ──> Clustern ──> Analysieren ──> Speichern
                tags.scm       NetworkX   Dual-        Leiden       PageRank       SQLite
                (17 Sprachen)  DiGraph    FAISS        Hierarchie   God-Nodes      FTS5+FAISS
```

### Hybridsuche (5 Signale)

1. **Code-Vektor** — `BAAI/bge-small-en-v1.5` bettet Code-Knoten ein, FAISS-Kosinus-Suche
2. **Text-Vektor** — `intfloat/multilingual-e5-small` bettet Textknoten ein (100+ Sprachen)
3. **Graph-Expansion** — BFS von Vektor-Treffern, gewichtet nach Kantenqualitaet
4. **Keyword** — FTS5-Volltextsuche ueber vollstaendigen Quellcode
5. **Community** — Leiden-Clustering-Zusammenfassungen boosten verwandte Knoten
6. **RRF-Fusion** — Gewichtete reziproke Rang-Fusion kombiniert alle Signale

## Leistung

Benchmarks auf der eigenen Codebasis von hedwig-kg (~3.500 Zeilen, 90 Dateien, 1.300 Knoten):

| Operation | Zeit |
|-----------|------|
| Vollstaendiger Build | ~14s |
| Inkrementeller Build (Aenderungen) | ~4s |
| Inkrementeller Build (keine Aenderungen) | ~0,4s |
| Kaltstart-Suche (Dual-Modell) | ~2,8s |
| Kaltstart-Suche (`--fast`) | ~0,2s |
| Warme Suche | ~0,08s |
| Cache-Treffer | <1ms |

## Anforderungen

- Python 3.10+
- Einbettungsmodelle ~470MB (beim ersten Gebrauch gecacht)

## Lizenz

MIT License. Siehe [LICENSE](../LICENSE).

## Mitwirken

Beitraege sind willkommen! Siehe [CONTRIBUTING.md](../CONTRIBUTING.md).
