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
Spieltags bzw. Datumsbereichs und aktualisiert nur sein Diagramm im Browser.
Keine Schemaänderung. Domain- und Streamlit-Tests sichern Trennung, Häufigkeiten,
Nullrunden, leere Auswahl und Wechsel der Auswertung ab.
Abnahme: In beiden Apps Statistik öffnen, alle vier Optionen für einen Spieltag
und für Gesamtstatistik ausprobieren; bei Re/Kontra dürfen keine Solos erscheinen.
Cloud-Prüfung am 21.10.2026: Beide Apps zeigen nach Deploy den Filter mit allen
vier Optionen; Umschalten im Browser erfolgreich, Gesamt als Standard vorhanden.
Veröffentlicht als `e4f38a8` in `doppelkopf-manager` und `13cf996` in
`doppelkopf-online-public`. Ruff und Mypy erfolgreich; Hauptrepository:
533 Tests bestanden, 28 PostgreSQL-Tests ohne Testserver übersprungen;
Online-Veröffentlichungsrepository: 12 Domain-Tests bestanden.

Ergänzung vom 21.10.2026: Alle vier Filter verwenden dieselben X-Kategorien,
dieselbe Reihenfolge und dieselben Achsenmarkierungen aus der Gesamtverteilung
der ausgewählten Auswertung. Fehlende Punktewerte erhalten Häufigkeit null;
auch ein leerer Filter behält das Diagramm samt X-Achse und zeigt den Hinweis.
Beispiel: Gesamtwerte 2, 4 und 18 bleiben in Re, Kontra und Solo Re an denselben
Positionen sichtbar, auch wenn dort nur ein Punktewert vorkommt. Der feste Platz
für Y-Beschriftungen verhindert seitliches Verschieben bei anderen Häufigkeiten.
Regressionen: `test_statistics_charts.py` prüft Achsendomäne, Teilung und Nullwerte
für alle Filter sowie einen leeren Filter. Abnahme: In beiden Online-Apps die vier
Optionen wechseln und identische X-Beschriftungen und Balkenpositionen prüfen.
Cloud-Abnahme erfolgreich: Nach Deploy von `4191689`/`ee88cf1` bleiben beim
Wechsel Gesamt → Solo Re in der Spieltag-App alle fünf X-Werte (3, 4, 6, 10, 12)
und in der Online-App alle 14 X-Werte (0 bis 30) samt Teilung erhalten. Auch der
leere Solo-Filter der Spieltag-App behält die Achse. Ruff/Mypy erfolgreich,
538 Tests bestanden, 28 übersprungen; Online-Repository: 21 Tests bestanden.

Korrektur nach Nutzerfehlerbericht vom 21.10.2026: In der Gesamtstatistik der
Online-App reagierte das Streamlit-Dropdown nicht zuverlässig, während der
bestehende native Vega-Kennzahlfilter in derselben Ansicht sofort funktionierte.
Die Punkteverteilung verwendet deshalb ebenfalls eine native Vega-Einzelauswahl.
Alle vier Häufigkeiten werden einmal je Punktewert übertragen; Umschalten
berechnet die Balkenhöhen direkt im Browser ohne Python-Rerun oder Datenbankabruf.
X-Achse und Nullwerte bleiben fest. Ein leerer Filter zeigt seinen Hinweis im
Diagramm. Ein vollständiger Neuaufbau der Auswertung setzt den Filter auf Gesamt.
Die frühere Prüfung eines einzelnen Spieltags deckte den gemeldeten Fehler in
der Gesamtstatistik nicht ab. Abnahme jetzt ausdrücklich mit Gesamtstatistik:
In beiden Apps alle Optionen mehrfach wechseln, tatsächliche Balkenhäufigkeiten
und unveränderte X-Achse prüfen; andere Kennzahlfilter müssen erhalten bleiben.
Cloud-Abnahme nach Deploy von `751ce15`/`cdae163` erfolgreich: ausdrücklich
Gesamtstatistik in beiden Apps geladen. Sichtbare SVG-Balkenhäufigkeiten online:
Gesamt 1700, Re 811, Kontra 391, Solo Re 326; normale App: Gesamt 154, Re 79,
Kontra 38, Solo Re 28. Nach Rückkehr zu Gesamt sind sämtliche ursprünglichen
Balkenbeschriftungen identisch. Bei jedem Wechsel bleiben X-Domäne und
Seitenlauf-Marker unverändert. Ruff/Mypy erfolgreich; vollständige Suite 538
bestanden/28 übersprungen, zwei danach ergänzte Aggregate-Regressionen ebenfalls
bestanden; Online-Veröffentlichungsrepository 23 Tests bestanden.

Normalisierung vom 21.10.2026: Die native Checkbox „Normalisieren“ ist beim
Neuaufbau der Auswertung standardmäßig aktiv. Jeder Balken zeigt dann seinen
Anteil an allen Spielen des gewählten Filters; die Balken summieren sich zu
100 Prozent, ein leerer Filter bleibt bei null ohne Division durch null.
Beispiel: Häufigkeiten 2 und 1 entsprechen 66,7 und 33,3 Prozent.
Die Y-Achse ist in allen vier Ansichten fest 0–100 Prozent. Ohne Normalisierung
zeigt sie absolute Häufigkeiten von null bis zum höchsten Gesamtbalken (mindestens
eins), mit identischer Teilung für alle vier Filter. Die X-Achse bleibt wie zuvor
fest. Tooltips enthalten weiterhin absolute Häufigkeit und Prozentanteil.
Checkbox und Filter reagieren gemeinsam direkt im Browser; ein Filterwechsel
behält den Checkboxzustand. Kein Datenbankabruf oder Seiten-Rerun beim Umschalten.
Abnahme: In beiden Apps Gesamtstatistik öffnen, aktivierte Checkbox prüfen,
alle Filter mit identischer Prozentachse wechseln; Checkbox deaktivieren und
erneut alle Filter auf derselben absoluten Y-Skala prüfen, danach reaktivieren.
Cloud-Abnahme nach Deploy von `d953ad3`/`7da10e1` erfolgreich: Checkbox in beiden
Apps standardmäßig aktiv; alle vier Gesamtstatistik-Filter summieren sich auf
100 Prozent und behalten die 0–100-Prozent-Achse. Ohne Normalisierung bleibt die
Y-Domäne online 0–211, in der normalen App 0–31 für alle Filter unverändert.
Beispiel online Gesamt: Punktewert 3, Häufigkeit 211 von 1700, Anteil 12,4 Prozent.
Zurückschalten stellt die Prozentansicht wieder her; X-Achse und Seitenlauf-Marker
bleiben bei allen Wechseln gleich. Ruff/Mypy erfolgreich, Hauptrepository 540
Tests bestanden/28 übersprungen; Online-Veröffentlichungsrepository 23 bestanden.

Bockfilter vom 21.10.2026: Ein zweites natives Dropdown „Bockfilter“ ergänzt
die Parteiauswahl. „Mit Bock“ (Standard) enthält alle Spiele einschließlich
Bockspielen; „Ohne Bock“ enthält nur Runden ohne aktiven Bock, „Nur Bock“ nur
Runden mit mindestens einem aktiven Bock. Maßgeblich ist `active_bocks > 0` der
gespielten Runde, nicht ein erst für spätere Runden ausgelöster Bock. Mehrere
aktive Böcke zählen die Runde weiterhin einmal. Punktewerte behalten ihre
gespeicherte Höhe; Bockfaktoren werden weder entfernt noch erneut angewendet.
Alle zwölf Kombinationen aus Partei- und Bockfilter sind möglich. Die
Normalisierung bezieht sich auf die jeweilige Kombination; leere Kombinationen
bleiben null und zeigen den Hinweis. Beide Achsen orientieren sich weiterhin
an der vollständigen Auswertung (X und absolute Y) bzw. 0–100 Prozent.
Beispiel: Re-Normalspiel mit 4 ohne Bock und Re-Normalspiel mit 8 im Bock ergeben
unter Re/Mit Bock je einen Treffer; Re/Ohne Bock nur 4, Re/Nur Bock nur 8.
Rundenklassifikation und Zählung liegen in der Domain; an den Browser gehen nur
aggregierte Häufigkeiten. Kein Rerun beim Umschalten, keine Schemaänderung.
Domain-, Diagramm- und UI-Tests sichern Kombinationen, Partitionierung, Nullrunden,
verlorene Solos, mehrfache Böcke, feste Achsen und Standardwerte ab.
Abnahme: In beiden Gesamtstatistiken alle drei Bockfilter mit jeder Parteiauswahl
und mit/ohne Normalisierung durchschalten; Mit Bock muss Ohne Bock plus Nur Bock
ergeben. Checkbox und beide Filter müssen unabhängig bleiben.


