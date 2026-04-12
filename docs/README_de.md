<p align="center">
  <h1 align="center">hedwig-cg</h1>
  <p align="center">
    "Hedwig wird mit der Nachricht zurueckkommen"
    <br />
    <a href="#schnellstart">Schnellstart</a> · <a href="#unterstuetzte-sprachen">Sprachen</a> · <a href="#ai-agent-integrationen">Integrationen</a> · <a href="#architektur">Architektur</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-code-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-cg/"><img src="https://img.shields.io/pypi/v/hedwig-cg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-code-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## Warum hedwig-cg?

hedwig-cg erstellt einen einheitlichen Code Graph aus Code, Dokumentation und Abhaengigkeiten — damit Coding-Agents Ihr gesamtes Projekt wirklich verstehen, statt nur Schluesselwoerter zu suchen. Installieren Sie es, und Claude Code sieht das Gesamtbild — keine zusaetzlichen Tokens, keine zusaetzlichen Befehle, alles laeuft 100% lokal.

<img width="1919" height="991" alt="Code Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## Schnellstart

```bash
pip install hedwig-cg
hedwig-cg claude install
```

Sagen Sie Claude Code:

> "Baue einen Code Graph fuer dieses Projekt"

Das war's. Claude Code baut den Graph und konsultiert ihn ab sofort bei jeder Suche. Bei Code-Aenderungen:

> "Code Graph neu bauen"

## Unterstuetzte Sprachen

### Tiefe AST-Extraktion (17 Sprachen)

hedwig-cg verwendet [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html) fuer universelle Strukturextraktion — Funktionen, Klassen, Methoden, Aufrufe, Imports, Vererbung — ohne sprachspezifischen Code.

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

hedwig-cg integriert sich mit einem Befehl in fuehrende AI Coding Agents:

| Agent | Installation | Beschreibung |
|-------|-------------|-------------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse-Hook |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse-Hook |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool-Hook |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/`-Regeldatei |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/`-Regeldatei |
| **Cline** | `hedwig-cg cline install` | `.clinerules`-Datei |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP-Server** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | Model Context Protocol 5 Tools |

Jeder `install`-Befehl schreibt eine Kontextdatei und registriert (bei unterstuetzten Plattformen) einen Hook vor Tool-Aufrufen. Entfernen: `hedwig-cg <platform> uninstall`.

---

## Funktionen

### Automatischer Rebuild

Bei Integration mit KI-Coding-Agenten (Claude Code, Codex usw.) **baut hedwig-cg den Graphen automatisch neu**, wenn sich Code aendert. Der Stop/SessionEnd-Hook erkennt geaenderte Dateien ueber `git diff` und fuehrt im Hintergrund einen inkrementellen Build durch — kein manuelles Eingreifen noetig.

### Intelligentes Ignore

Unterstuetzt Ignore-Muster aus drei Quellen, alle mit **vollstaendiger gitignore-Spezifikation** (Negation `!`, `**`-Globs, verzeichnisspezifische Muster):

| Quelle | Beschreibung |
|--------|-------------|
| Eingebaut | `.git`, `node_modules`, `__pycache__`, `dist`, `build` usw. |
| `.gitignore` | Automatisches Lesen aus dem Projektstamm — bestehende Git-Ignores funktionieren einfach |
| `.hedwig-cg-ignore` | Projektspezifische Ueberschreibungen fuer den Code-Graphen |

### Inkrementelle Builds

SHA-256-Content-Hashing pro Datei. Nur geaenderte Dateien werden neu extrahiert und neu eingebettet. Unveraenderte Dateien werden aus dem bestehenden Graphen uebernommen — typischerweise **95%+ schneller** als ein vollstaendiger Build.

### Speicherverwaltung

4GB Speicherbudget mit stufenweiser Freigabe. Die Pipeline erzeugt → speichert → gibt frei in jeder Phase: Extraktionsergebnisse werden nach dem Graph-Aufbau freigegeben, Embeddings werden batchweise gestreamt und nach DB-Schreiben freigegeben, der gesamte Graph wird nach der Persistierung freigegeben. GC wird bei 75% Schwellenwert praeventiv ausgeloest.

### 100% Lokal

Keine Cloud-Dienste, keine API-Schluessel, keine Telemetrie. SQLite + FAISS fuer Speicherung, sentence-transformers fuer Embeddings. Alle Daten bleiben auf Ihrem Rechner.

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

### 5-Signal-Hybridsuche

Jede Suchanfrage durchlaeuft fuenf unabhaengige Abrufsignale und wird dann zu einem einzigen Ranking-Ergebnis fusioniert:

| Signal | Engine | Findet |
|--------|--------|--------|
| **Code-Vektor** | FAISS + `bge-small-en-v1.5` | Semantisch aehnlichen Code (Funktionen, Klassen, Methoden) |
| **Text-Vektor** | FAISS + `multilingual-e5-small` | Dokumentation, Kommentare, Markdown (100+ Sprachen) |
| **Graph-Expansion** | NetworkX gewichtete BFS | Strukturell verbundene Knoten (Aufrufer, Aufgerufene, Imports) |
| **Volltextsuche** | SQLite FTS5 + BM25 | Exakte Keyword-Treffer im gesamten Quellcode |
| **Community-Kontext** | Leiden-Clustering | Verwandte Knoten aus demselben funktionalen Cluster |
| **RRF-Fusion** | Gewichtete reziproke Rang-Fusion | Kombiniert alle Signale — Knoten aus mehreren Signalen ranken hoeher |

## Leistung

Benchmarks auf der eigenen Codebasis von hedwig-cg (~3.500 Zeilen, 90 Dateien, 1.300 Knoten):

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
