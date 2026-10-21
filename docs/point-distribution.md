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
Cloud-Abnahme nach Deploy von `2121ad6`/`27f1c91` erfolgreich: In beiden Apps
alle zwölf Kombinationen jeweils normalisiert und absolut geprüft. Online:
1700 = 1456 ohne Bock + 244 Bockspiele; normale App: 154 = 110 + 44.
Die Aufteilung stimmt auch je Punktewert und Parteiauswahl. Prozentanteile
summieren sich je Kombination zu 100 Prozent; absolute Balkenhöhen entsprechen
ihren Häufigkeiten. X und Y bleiben in beiden Modi fest, Seitenlauf-Marker
unverändert; Standardansicht anschließend wiederhergestellt. Ruff/Mypy erfolgreich,
546 Tests bestanden/28 übersprungen; Online-Veröffentlichungsrepository 29 bestanden.

Anpassung Prozentachse vom 21.10.2026: Statt pauschal 0–100 Prozent reicht die
normalisierte Y-Achse nun bis zum höchsten Balkenanteil über alle zwölf möglichen
Partei-/Bockfilterkombinationen der gewählten Auswertung, auf volle fünf
Prozentpunkte aufgerundet (mindestens fünf Prozent). Beispiel: größter Anteil
21,4 Prozent ergibt eine gemeinsame Achse 0–25 Prozent. Ein Teilfilter mit
66,7 Prozent setzt die gemeinsame Grenze auf 70 Prozent, auch wenn Gesamt nur
20 Prozent erreicht. Leere Filter beeinflussen das Maximum nicht; ein einzelner
Punktewert mit allen Treffern erfordert weiterhin 100 Prozent. Die Berechnung
verwendet exakte Integer-Aufrundung und Decimal; exakt 30 Prozent bleiben 30.
Filterwechsel behalten dieselbe Y-Achse und Teilung. Die absolute Y-Skala bleibt
unverändert. Der Abstand der Prozentmarken passt sich der kleineren Skala an.
Regressionen in `test_statistics_charts.py` sichern Rundungsgrenzen, leere
Auswahlen und das Maximum einer kombinierten Bockauswahl ab.
Abnahme: In beiden Apps alle zwölf Kombinationen durchschalten; kein Balken darf
abgeschnitten werden und die Prozentachse muss in allen Kombinationen gleich bleiben.
Cloud-Abnahme nach Deploy von `1772bd0`/`f98cf89` erfolgreich: Alle zwölf
Gesamtstatistik-Kombinationen behalten identische Achsen und Prozentmarken ohne
Seiten-Rerun. Online liegt das Maximum bei Solo Re/Nur Bock mit 31,58 Prozent,
gemeinsame Achse 0–35 Prozent in Fünferschritten. In der normalen App erreicht
Kontra/Nur Bock 60 Prozent, gemeinsame Achse 0–60 Prozent in Zehnerschritten.
Absolute Skalen bleiben online 0–211 bzw. normal 0–31. Standardansichten
wiederhergestellt. Ruff/Mypy erfolgreich, Hauptrepository 555 Tests bestanden/28
übersprungen; Online-Veröffentlichungsrepository 38 bestanden.

Präzisierung Peak-Normierung vom 21.10.2026: „Normalisieren“ bedeutet jetzt
Häufigkeit geteilt durch den höchsten Balken der aktuell gewählten Partei-/Bock-
Kombination. Jeder nichtleere Plot erreicht exakt 100 Prozent auf derselben
Y-Achse; die Form bleibt unabhängig von der Anzahl der Spiele vergleichbar.
Beispiele: 20/10/5 und 4/2/1 ergeben beide 100/50/25 Prozent Peakhöhe. Die
Maxima stammen jeweils nur aus den aktuellen Daten der betreffenden App,
Auswertung und Filterkombination, werden beim Filterwechsel neu bestimmt und
weder zwischen Apps noch zwischen Filtern geteilt. Ein leerer Filter bleibt null.
Tooltip „Peakhöhe“ benennt die Normierung; „Häufigkeit“ und „Anteil“ enthalten
weiterhin absolute Häufigkeit bzw. Anteil an allen Spielen im aktuellen Filter.
Ein kurzer Hinweis erklärt Peak = 100 Prozent. Standardcheckbox, X-Achse und
gemeinsame absolute Y-Skala bleiben erhalten. Die bisherige Prozentanteil-
Normierung und die spätere globale Prozentobergrenze sind damit abgelöst.
Regressionen wurden an die präzisierte Anforderung angepasst: lokales Maximum
nach beiden Filtern, verschiedene App-Zähler, Nullfall und feste Achsen.
Abnahme: In beiden Apps alle zwölf Kombinationen wechseln; der höchste sichtbare
Balken muss jeweils 100 Prozent erreichen, ohne dass die Seite neu lädt.


