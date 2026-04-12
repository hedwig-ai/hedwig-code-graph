<p align="center">
<img width="2048" height="1138" alt="hegwid-cg" src="https://github.com/user-attachments/assets/2875669b-e7e3-45df-9e50-90110e2abbf1" />
<h1 align="center">hedwig-cg</h1>
  <p align="center">
    "With hedwig-cg, your coding agent knows what to read."
    <br />
    <a href="#schnellstart">Schnellstart</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a>
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

hedwig-cg erstellt einen einheitlichen Code Graph aus Code, Dokumentation und Abhaengigkeiten — konzipiert fuer Enterprise-Codebasen mit 10.000+ Dateien. 5-Signal-Hybridsuche (Vektor + Graph + Keyword + Community → RRF-Fusion) ermoeglicht Coding-Agents, Ihr gesamtes Projekt wirklich zu verstehen. Installieren Sie es, und Claude Code sieht das Gesamtbild — keine zusaetzlichen Tokens, keine zusaetzlichen Befehle, alles laeuft 100% lokal.

## Schnellstart

```bash
pip install hedwig-cg
hedwig-cg claude install
```

Sagen Sie Claude Code:

> "Baue einen Code Graph fuer dieses Projekt"

Das war's. Claude Code baut den Graph und konsultiert ihn ab sofort bei jeder Suche. Der Graph wird automatisch neu gebaut, wenn Ihre Sitzung endet.

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

## 5-Signal-Hybridsuche

Alle Abfragen durchlaufen fünf Signale, fusioniert durch Reciprocal Rank Fusion (RRF):

| Signal | Findet |
|--------|--------|
| **Code-Vektor** | Semantisch ähnlichen Code |
| **Text-Vektor** | Dokumentation und Kommentare in 100+ Sprachen |
| **Graph-Expansion** | Strukturell verbundene Knoten (Aufrufer, Imports) |
| **Volltextsuche** | Exakte Keyword-Treffer (BM25) |
| **Community-Kontext** | Verwandte Knoten aus demselben Cluster |

## CLI-Referenz

Alle Befehle geben standardmaessig kompaktes JSON aus (fuer AI-Agent-Nutzung konzipiert).

| Befehl | Beschreibung |
|--------|-------------|
| `build <dir>` | Code-Graph erstellen (`--incremental`, `--no-embed`) |
| `search <query>` | 5-Signal-Hybridsuche (`--top-k`, `--fast`, `--expand`) |
| `query` | Interaktive Such-REPL |
| `communities` | Communities auflisten und durchsuchen (`--search`, `--level`) |
| `stats` | Graph-Statistiken |
| `node <id>` | Knotendetails mit Fuzzy-Matching |
| `export` | Export als JSON, GraphML oder D3.js |
| `visualize` | Interaktive HTML-Visualisierung |
| `clean` | .hedwig-cg/-Datenbank entfernen |
| `doctor` | Installationsstatus pruefen |
| `mcp` | MCP-Server starten (stdio) |

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

- **Einbettungsmodelle**: ~470MB, einmalig nach `~/.hedwig-cg/models/` heruntergeladen
- **Datenbank**: ~2MB (SQLite + FTS5 + FAISS-Indizes)
- **Inkrementelle Builds**: SHA-256-Hashing, 95%+ schneller als vollstaendiger Build

## Anforderungen

- Python 3.10+
- Einbettungsmodelle ~470MB (beim ersten Gebrauch gecacht)

```bash
# Optional: PDF-Extraktion
pip install hedwig-cg[docs]
```

## Entwicklung

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_cg/
```

## Lizenz

MIT License. Siehe [LICENSE](../LICENSE).

## Mitwirken

Beitraege sind willkommen! Siehe [CONTRIBUTING.md](../CONTRIBUTING.md).
