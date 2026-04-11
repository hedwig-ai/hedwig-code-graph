<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    Local-first Wissensgraph-Builder für KI-Coding-Agenten
    <br />
    <a href="#integration-mit-ki-coding-agenten">Integration</a> · <a href="#schnellstart">Schnellstart</a> · <a href="#architektur">Architektur</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_zh.md">中文</a>
  </p>
</p>

---

**hedwig-kg** erstellt Wissensgraphen aus Quellcode und Dokumenten und bietet eine **5-Signal HybridRAG-Suche** mit dualen Embedding-Modellen (Code-spezialisiert + Text-spezialisiert), fusioniert über RRF. Alles läuft **100% lokal** — keine Cloud-APIs, keine Daten verlassen Ihren Rechner.

## Integration mit KI-Coding-Agenten

Mit einem einzigen Befehl integrieren Sie hedwig-kg in führende KI-Coding-Agenten. Jede Integration erstellt plattformspezifische Kontextdateien und Hooks, sodass der Agent automatisch den Wissensgraphen nutzt, bevor er Rohdateien durchsucht.

```bash
pip install hedwig-kg
```

### Claude Code

```bash
hedwig-kg claude install
```

Erstellt einen `CLAUDE.md`-Abschnitt + `.claude/settings.json` PreToolUse-Hook.

### OpenAI Codex CLI

```bash
hedwig-kg codex install
```

Erstellt einen `AGENTS.md`-Abschnitt + `.codex/hooks.json` PreToolUse-Hook.

### Google Gemini CLI

```bash
hedwig-kg gemini install
```

Erstellt einen `GEMINI.md`-Abschnitt + `.gemini/settings.json` BeforeTool-Hook.

### Funktionsweise

Jeder `install`-Befehl führt zwei Schritte aus:

1. **Kontextdatei** — Fügt einen `## hedwig-kg`-Abschnitt zur Kontextdatei der Plattform hinzu
2. **Hook** — Registriert einen leichtgewichtigen Shell-Hook, der vor Tool-Aufrufen ausgelöst wird

Deinstallation: `hedwig-kg <platform> uninstall`

### Voraussetzungen

- Python 3.10+
- ~250 MB Speicherplatz für duale Embedding-Modelle (beim ersten Gebrauch in `~/.hedwig-kg/models/` zwischengespeichert)

### Optionale Abhängigkeiten

```bash
# PDF-Textextraktion
pip install hedwig-kg[docs]
```

## Schnellstart

### 1. Installation & Build

```bash
pip install hedwig-kg
cd ./my-project
hedwig-kg build .
```

Der erste Build scannt alle Dateien, extrahiert AST-Strukturen, generiert Embeddings mit dualen Modellen (~250 MB Download beim ersten Lauf, zwischengespeichert in `~/.hedwig-kg/models/`), erkennt Communities und speichert alles in `.hedwig-kg/knowledge.db`.

### 2. Suche

```bash
hedwig-kg search "Authentifizierungs-Handler"
```

### 3. Agenten-Integration

```bash
hedwig-kg claude install   # Claude Code
hedwig-kg codex install    # Codex CLI
hedwig-kg gemini install   # Gemini CLI
```

### 4. Aktuell halten

```bash
hedwig-kg build . --incremental
```

### 5. Erkunden

```bash
hedwig-kg stats                           # Graph-Übersicht
hedwig-kg communities --search "auth"     # Community-Erkundung
hedwig-kg node "AuthHandler"              # Knotendetails
hedwig-kg query                           # Interaktive REPL
hedwig-kg visualize                       # HTML-Visualisierung
```

## Architektur

```
Quellcode/Dokumente → Erkennung → Extraktion → Graph-Aufbau → Embedding → Clustering → Zusammenfassung → Analyse → Speicherung
```

### HybridRAG-Suche (5 Signale)

1. **Code-Vektorsuche** — Abfrage mit `BAAI/bge-small-en-v1.5` eingebettet, durchsucht Code-Knoten (Funktionen, Klassen, Methoden) über FAISS
2. **Text-Vektorsuche** — Abfrage mit `all-MiniLM-L6-v2` eingebettet, durchsucht Dokumentknoten (Überschriften, Abschnitte, Docstrings) über FAISS
3. **Graph-Erweiterung** — Von den besten Vektortreffern werden N-Hop-Nachbarn durchlaufen
4. **Stichwortsuche** — FTS5-Volltextsuche mit BM25-Ranking
5. **Community-Suche** — Abfrage wird mit Community-Zusammenfassungen abgeglichen
5. **RRF-Fusion** — Alle Signale werden zu einem einheitlichen Ranking kombiniert

## Lizenz

MIT-Lizenz. Siehe [LICENSE](../LICENSE) für Details.
