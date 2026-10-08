# vault-search-mcp

Lokale semantische Suche und Strukturanalyse für einen Markdown-Vault, etwa aus
Obsidian. Der MCP-Server liefert passende Textstellen an Claude Code. Ollama
berechnet die Embeddings, LanceDB speichert den Suchindex. `vault-graph` wertet
Links, Aufgaben und Tags mit SQLite aus und braucht dafür kein Ollama.

## Installation

Du brauchst Git und einen vorhandenen Vault. Schließe das Terminal während des
Modell-Downloads und der ersten Indizierung nicht. Die Starthilfe besorgt bei
Bedarf [uv](https://docs.astral.sh/uv/); uv verwaltet Python 3.12 und die
Projektabhängigkeiten. Der Download benötigt eine Internetverbindung.

Ersetze den Beispielpfad durch deinen absoluten Vault-Pfad. Führe den passenden
Befehl in einem Terminal aus:

macOS und Linux:

```bash
git clone https://github.com/Dakaric/vault-search-mcp.git && cd vault-search-mcp && bash install.sh --vault "$HOME/Documents/Mein Vault"
```

Windows, in PowerShell:

```powershell
git clone https://github.com/Dakaric/vault-search-mcp.git; if ($LASTEXITCODE -eq 0) { Set-Location vault-search-mcp; powershell -ExecutionPolicy Bypass -File .\install.ps1 --vault 'C:\Daten\Mein Vault' }
```

Der Installer fragt jeden Baustein einzeln ab und zeigt danach eine Übersicht.
Eine fehlende Voraussetzung erscheint als „handarbeit“ mit dem nächsten Schritt.
Ein Fehler in einem Baustein stoppt die übrigen Bausteine nicht.

| Baustein | Schlüssel | Funktion |
|---|---|---|
| Ollama | `ollama` | Dienst prüfen, Installation anbieten |
| Modell | `modell` | `mxbai-embed-large` herunterladen |
| Vault | `vault` | Vorhandenen Ordner prüfen |
| Index | `index` | Vollständigen Suchindex erstellen |
| Claude Code | `registrieren` | `vault-search` im Benutzerkonto registrieren |

| Funktion | macOS (Apple Silicon) | Linux x64 und ARM64 | Windows x64 |
|---|---|---|---|
| Python, Suche und Graph | unterstützt | unterstützt | unterstützt |
| Ollama installieren | Homebrew, sonst Download-Link | offizielles Skript nach ausdrücklicher Zustimmung | winget, sonst Download-Link |
| Ollama starten | Homebrew startet den Dienst | bei Bedarf von Hand | nach winget neues Terminal öffnen |
| In Claude Code registrieren | mit `claude` im PATH | mit `claude` im PATH | mit `claude` im PATH |

Intel-Mac und Windows on ARM sind nicht unterstützt, weil LanceDB für diese
Plattformen keine Wheels bereitstellt. Die Starthilfen starten den Installer mit
`uv run --no-project`, damit er diese Einschränkung ohne Projektinstallation
melden kann.

Die CI-Konfiguration prüft alle drei Systeme. Ein lokaler Test auf einem System
ersetzt keinen erfolgreichen CI-Lauf und keine echte Installation auf den anderen
Systemen. Fehlt Claude Code, zeigt der Installer den Registrierungsbefehl zum
Kopieren an. Download: [Ollama](https://ollama.com/download).

Aus dem geklonten Repo kannst du die Einrichtung zuerst ohne Änderungen ansehen:

```bash
bash install.sh --dry-run --yes --vault "/pfad/Mein Vault"
```

`--dry-run` fragt weder Ollama noch Claude Code ab und schreibt keine
Konfiguration. uv kann davor Python bereitstellen. Die Projektumgebung wird erst
beim Indizieren oder beim Serverstart eingerichtet, jeweils mit `--no-dev`.
Unter Windows verwende `install.ps1` mit denselben Argumenten.

`--yes` übernimmt die Standardantworten. Es gibt keine automatische Zustimmung
zum Linux-Installationsskript. Ohne interaktives Terminal ist `--yes` Pflicht.
`--only modell,index` beschränkt den Lauf auf die genannten Bausteine.
`--model NAME` wählt ein anderes Embedding-Modell. Dessen Dimension muss zu
`VAULT_EMBED_DIM` passen. Exit-Codes: 0 für einen abgeschlossenen Lauf, auch mit
Handarbeit; 1 bei Bausteinfehlern; 2 bei ungültigen Eingaben.

Erneute Läufe erkennen erreichbare Dienste, vorhandene Modelle und einen durch
den Installer erfolgreich erstellten Index. Sie führen den Vollindex bei gleicher
Konfiguration nicht erneut aus. Für geänderte Notizen nutze `vault-reindex`.
Bei einem anderen Vault, Suchmodell, Indexpfad oder Startkommando aktualisiert
der Installer seinen eigenen Claude-Eintrag nach ausdrücklicher Zustimmung.
Die Standardantwort ist Nein, auch mit `--yes`. Fremde Einträge und Einträge aus
Projekt- oder lokalem Scope erfordern Handarbeit. Scheitert die neue Registrierung,
zeigt der Installer den Befehl zum Wiederherstellen des alten Eintrags.
Notizen werden nicht verändert.

## Mit Claude einrichten

Starte Claude Code in diesem Repo und sage „Führe die Einrichtung aus“. Die
[CLAUDE.md](CLAUDE.md) lässt Vault-Pfad und Bausteine abfragen und startet den
Installer mit `--yes --only …`.

## MCP-Werkzeuge

| Werkzeug | Eingabe | Ergebnis |
|---|---|---|
| `vault_search` | `query`, optional `k=5` | Ähnliche Textabschnitte mit Pfad, Überschrift, Text und Distanz |
| `vault_related` | `note_path`, optional `k=5` | Thematisch verwandte Abschnitte anderer Notizen |
| `vault_status` | keine | Indexpfad, Vault, Modell, Dimension und Zahl der Chunks |

`query` ist eine Frage oder Beschreibung in natürlicher Sprache. `note_path` ist
relativ zum Vault, etwa `Projekte/Projekt Alpha.md`. Indexpfade verwenden auf allen
Systemen `/`. Eine kleinere Distanz bedeutet einen näheren Treffer.

## Konfiguration

| Umgebungsvariable | Standard | Bedeutung |
|---|---|---|
| `VAULT_ROOT` | kein Standard, Pflicht | Pfad zum Vault |
| `VAULT_INDEX_DIR` | `.vault-index` im Vault | Speicherort für Vektoren, Graph und Installer-Merkdatei |
| `OLLAMA_URL` | `http://localhost:11434` | Adresse des Ollama-Dienstes, auch für den Installer |
| `VAULT_EMBED_MODEL` | `mxbai-embed-large` | Modell für Indizierung und Suche |
| `VAULT_EMBED_DIM` | `1024` | Vektordimension des gewählten Modells |
| `VAULT_IGNORE_DIRS` | leer | Zusätzliche ausgeschlossene Ordnernamen, durch Kommas getrennt |
| `VAULT_DAILY_DIR` | `05 Daily Notes` | Relativer Tagesnotizordner für den Graph, wirkt nur wenn vorhanden |

Immer ausgeschlossen sind `.obsidian`, `.trash`, `.git`, `.vault-index`,
`.vault-mcp-state`, `.claude`, `node_modules` und `.venv`. Zusätzliche Namen gelten
auf jeder Ordnerebene und ergänzen diese Liste:

```bash
export VAULT_IGNORE_DIRS='06 Archiv,07 Anhänge'
```

Die semantische Suche, der Selbsttest und der Graph verwenden dieselbe
Ignore-Konfiguration. Ohne die Ergänzung werden Archiv und Anhänge berücksichtigt,
soweit sie Markdown-Dateien enthalten. Die Registrierung reicht das gewählte
Modell und gesetzte Such-Konfiguration an Claude Code weiter.

Modell und Dimension sind in der Index-Tabelle gespeichert. Bei einem Wechsel
bricht der inkrementelle Lauf mit einem Hinweis auf `vault-reindex --full` ab,
auch wenn beide Modelle dieselbe Dimension haben. `--full` löscht bei Abweichung
nur die abgeleitete Tabelle `chunks` im Index-Ordner und legt sie neu an.
Bestehende Tabellen ohne Modellmetadaten benötigen ebenfalls einen Vollindex.
Der Installer verwendet dafür `--full`. Registriere danach den Server erneut.
Wähle für jeden Vault einen eigenen Indexordner.

Wenn `.vault-index/` im Vault liegt, trage `.vault-index/` in die `.gitignore`
des Vaults ein. Bei iCloud, Dropbox, OneDrive oder Syncthing setze
`VAULT_INDEX_DIR` außerhalb des Vaults in einen lokalen, nicht synchronisierten
Ordner. Es gilt: ein Index pro Rechner. Synchronisiere die Notizen, nicht die
Indexdateien.

## Deinstallieren

Entferne die Registrierung für dein Benutzerkonto:

```bash
claude mcp remove vault-search -s user
```

Danach den Index-Ordner löschen: standardmäßig `.vault-index/` im Vault oder den
mit `VAULT_INDEX_DIR` festgelegten Ordner. Er enthält nur abgeleitete Daten;
die Notizen bleiben erhalten.

## Neu indizieren und prüfen

macOS und Linux, aus dem Repo:

```bash
export VAULT_ROOT="$HOME/Documents/Mein Vault"
uv run --no-dev vault-reindex
uv run --no-dev vault-reindex --full
uv run --no-dev vault-selfcheck
uv run --no-dev vault-selfcheck --scope 'Projekte,Wissen' --top-k 3 --threshold 0.55
```

Windows:

```powershell
$env:VAULT_ROOT = 'C:\Daten\Mein Vault'
uv run --no-dev vault-reindex
uv run --no-dev vault-reindex --full
uv run --no-dev vault-selfcheck
```

Der normale Lauf verarbeitet geänderte Dateien und entfernt gelöschte oder neu
ignorierte Notizen aus dem Index. `--full` verarbeitet alle Dateien erneut.
`vault-selfcheck` sucht jede Notiz über ihren Titel und ihre Aliasse. Ohne `--scope`
prüft es den ganzen Vault; gesetzte Ordner beschränken die Prüfung auf ihre direkt
enthaltenen Notizen. `--threshold` ist eine optionale Distanzgrenze, kein für jeden
Vault passender Qualitätsmaßstab. Exit 2 bedeutet schwache Treffer oder eine
fehlende Konfiguration; die Ausgabe nennt die Ursache.

## Graph abfragen

Setze vorher `VAULT_ROOT` wie oben. Alle Befehle aktualisieren den Graph vor dem
Lesen. `--no-refresh` liest den vorhandenen Stand, `--agent` liefert JSON und
`--limit 10` begrenzt Listen.

```bash
uv run --no-dev vault-graph stats
uv run --no-dev vault-graph backlinks 'Projekt Alpha'
uv run --no-dev vault-graph links 'Projekt Alpha'
uv run --no-dev vault-graph orphans
uv run --no-dev vault-graph broken
uv run --no-dev vault-graph todos --folder 'Projekte'
uv run --no-dev vault-graph todos --note 'Projekt Alpha'
uv run --no-dev vault-graph stale --days 30
uv run --no-dev vault-graph stale --days 30 --folder 'Projekte'
uv run --no-dev vault-graph query --status aktiv --folder 'Projekte' --quelle 'Handbuch'
uv run --no-dev vault-graph tags --cooccur
uv run --no-dev vault-graph daily --gaps
uv run --no-dev vault-graph doctor --agent
```

`stale` zeigt aktive, länger unveränderte Notizen und sucht standardmäßig im ganzen
Vault. `doctor` zeigt defekte Links und doppelte Titel. Die übernommene Erkennung
fehlerhaften Frontmatters unterscheidet bisher nicht zwischen leerem Frontmatter
und einem Parsefehler; `fm_broken_notes` ist deshalb noch keine verlässliche Prüfung.

## Regelmäßige Läufe von Hand einrichten

Der Installer legt keine Zeitpläne an. Die folgenden Beispiele zeigen einen
nächtlichen Lauf um 03:00 Uhr. Ersetze die Beispielpfade durch absolute Pfade auf
deinem Rechner. Ollama muss zum Ausführungszeitpunkt laufen. Nutze bei eigener
Konfiguration dieselben Variablen wie beim ersten Indexlauf.

### Linux mit cron

Trage mit `crontab -e` eine Zeile ein. Den uv-Pfad findest du mit `command -v uv`:

```cron
0 3 * * * VAULT_ROOT="/daten/Mein Vault" /opt/uv/bin/uv --directory "/opt/vault-search-mcp" run --no-dev vault-reindex >> "/tmp/vault-reindex.log" 2>&1
```

### macOS mit launchd

Speichere dieses Beispiel unter
`~/Library/LaunchAgents/local.vault-search.reindex.plist`. Ersetze die drei Pfade;
XML-Sonderzeichen wie `&` müssen als `&amp;` geschrieben werden:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.vault-search.reindex</string>
  <key>ProgramArguments</key><array>
    <string>/opt/uv/bin/uv</string>
    <string>--directory</string><string>/opt/vault-search-mcp</string>
    <string>run</string><string>--no-dev</string><string>vault-reindex</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>VAULT_ROOT</key><string>/daten/Mein Vault</string>
  </dict>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/vault-reindex.log</string>
  <key>StandardErrorPath</key><string>/tmp/vault-reindex-error.log</string>
</dict></plist>
```

Aktivieren:

```bash
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.vault-search.reindex.plist"
```

### Windows mit Aufgabenplanung

Speichere ein Skript `C:\Werkzeuge\vault-reindex.ps1`. In Windows PowerShell 5.1
verwende beim Speichern UTF-8 mit BOM, damit Umlaute richtig gelesen werden.
Setze den absoluten uv-Pfad aus `(Get-Command uv).Source` ein:

```powershell
$env:PYTHONUTF8 = '1'
$env:VAULT_ROOT = 'C:\Daten\Mein Vault'
& 'C:\Werkzeuge\uv.exe' --directory 'C:\Werkzeuge\vault-search-mcp' run --no-dev vault-reindex
exit $LASTEXITCODE
```

Erstelle in der Aufgabenplanung eine tägliche Aufgabe um 03:00 Uhr, unter deinem
Benutzerkonto. Programm: `powershell.exe`. Argumente:

```text
-NoProfile -ExecutionPolicy Bypass -File "C:\Werkzeuge\vault-reindex.ps1"
```

## Datenschutz

Mit der Standardkonfiguration laufen Indizierung, Embeddings und Suche vollständig
lokal. Der Index enthält Textauszüge deiner Notizen. Behandle ihn wie den Vault
selbst und nimm ihn bei Bedarf in deine Datensicherung auf.

Die Installation lädt Programme, Python-Pakete und das Embedding-Modell aus dem
Netz. Eine andere `OLLAMA_URL` kann Notizinhalte an einen entfernten Dienst senden.
Wenn Claude Code MCP-Treffer verwendet, verarbeitet der gewählte KI-Dienst diese
Textauszüge gemäß seiner eigenen Konfiguration. „Lokal“ beschreibt hier die Suche,
nicht automatisch die anschließende KI-Verarbeitung.

## Entwicklung

```bash
uv sync --no-dev --python 3.12
uv run --python 3.12 pytest -q
bash install.sh --dry-run --yes --vault "/pfad/Mein Vault"
```

Tests blockieren Netzverbindungen und ersetzen externe Dienste durch kontrollierte
Antworten. Bei gefülltem uv-Cache funktionieren die Befehle mit `--offline`.
Python wird von 3.12 bis einschließlich 3.13 unterstützt. Lizenz: [MIT](LICENSE).
