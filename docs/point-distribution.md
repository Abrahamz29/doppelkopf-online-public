## Punkteverteilung mit Filter vom 21.10.2026

Die gemeinsame Statistik-Seite beider Cloud-Apps (normale Spieltage und Online-Daten)
bietet eine Einzelauswahl: Gesamt (Standard), Re (Normalspiel), Kontra (Normalspiel)
und Solo Re. Re/Kontra zählen nur von der jeweiligen Partei gewonnene Normalspiele;
Solos sind ausgeschlossen. Solo Re zählt gewonnene Solos. Jede Runde zählt einmal
mit dem absoluten Punktewert, bei Solos mit dem dreifachen Solistenwert.
Gesamt bleibt unverändert und enthält auch verlorene Solos sowie Nullrunden.
Nullrunden haben keine gewinnende Partei und erscheinen nur in Gesamt.
Beispiel: Re-Normalspiel mit 4 Punkten, Kontra-Normalspiel mit 4 Punkten und
gewonnenes Solo mit 12 Solistenpunkten ergeben Gesamt 4:2/12:1, Re 4:1,
Kontra 4:1 und Solo Re 12:1. Bockpunkte bleiben enthalten.
Leere Kategorien zeigen einen Hinweis. Der Filter gilt innerhalb des ausgewählten
Spieltags bzw. Datumsbereichs und aktualisiert nur sein Diagramm per Fragment.
Keine Schemaänderung. Domain- und Streamlit-Tests sichern Trennung, Häufigkeiten,
Nullrunden, leere Auswahl und Wechsel der Auswertung ab.
Abnahme: In beiden Apps Statistik öffnen, alle vier Optionen für einen Spieltag
und für Gesamtstatistik ausprobieren; bei Re/Kontra dürfen keine Solos erscheinen.


