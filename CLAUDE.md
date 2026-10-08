# Einrichtung

Wenn der Nutzer „Führe die Einrichtung aus“ sagt:

1. Frage nach dem absoluten Pfad zu einem vorhandenen Markdown-Vault. Prüfe, dass
   der Ordner existiert. Lege keinen neuen Vault an.
2. Zeige die Bausteine `ollama`, `modell`, `vault`, `index`, `registrieren` und frage,
   welche eingerichtet werden sollen. Frage bei einem anderen Embedding-Modell
   auch nach dessen Dimension; Standard ist `mxbai-embed-large` mit 1024 Dimensionen.
3. Starte aus diesem Repo `bash install.sh --yes --only AUSWAHL --vault PFAD`
   beziehungsweise unter Windows
   `powershell -ExecutionPolicy Bypass -File .\install.ps1 --yes --only AUSWAHL --vault PFAD`.
   Ersetze AUSWAHL durch die gewählten Schlüssel, durch Kommas getrennt, und PFAD
   durch den bestätigten Pfad. Übergib Argumente einzeln, damit Leerzeichen und
   Umlaute erhalten bleiben. Nutze bei Bedarf `--model NAME` und `VAULT_EMBED_DIM`.
4. Melde das Ergebnis einschließlich Handarbeit und Fehlern. Unter Linux verlangt
   das offizielle Ollama-Skript eine ausdrückliche Zustimmung. `--yes` erteilt sie
   nicht. Verweise in diesem Fall auf den interaktiven Installer oder den Download.

Nutze immer `--yes` und `--only`, weil deine Shell kein interaktives Terminal hat.
Ein `--dry-run` zeigt den Plan, ohne Dienste abzufragen oder Einstellungen zu ändern.
Ändere keine Notizen und richte keine automatischen Zeitpläne ein.

# Entwicklung

Änderungen passend testen: `uv run --offline --python 3.12 pytest -q`.
Installer-Code nutzt nur die Python-Standardbibliothek. Unterprozesse bekommen
Argumentlisten. Rekursives Löschen ist nur über `installer.fsutil.safe_rmtree`
unterhalb des Installer-Cache-Ordners erlaubt.
