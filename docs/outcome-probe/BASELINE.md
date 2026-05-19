# Baseline (`4aa4f9a`, pre-Schritt-0) + Delta

> Referenzbaum = letzter Commit vor Schritt 0 (`git log`: `4aa4f9a feat:
> Lead-Typ … und Lead-Owner`, direkt vor `e781e4a docs: Schritt 0`).
> Struktur dort: monolithisch — `models.py` **610 Zeilen** (alle 14
> Tabellen + alle Schemas + alle Label-Dicts), `routes/*.py` (Logik im
> Handler), `services/mcp_server.py` mit **dupliziertem** Lead/Proposal-
> Code (Schuld 4, vor der Entdopplung), kein Scaffold, kein import-linter,
> kein Alembic.
>
> Erhebung post-hoc über `git ls-tree`/`git show 4aa4f9a:…` (faktisch, nicht
> geschätzt). Einschränkung s. README §Methodik 4.

## Worauf es ankommt

Die Roadmap-Schwelle ist **„3/3 treffen *exakt* das versiegelte Set, keine
Extra-Datei"**. Der Nutzen ist daher *nicht* „weniger Dateien" sondern
**Vorhersagbarkeit**: lässt sich das Set vor dem Lauf aus Protokoll +
Struktur ableiten? Zweitens **Blast-Radius**: wie viel fremde Oberfläche
muss man anfassen.

## Pro Aufgabe: Baseline-Set & Vorhersagbarkeit

| Aufgabe | Baseline-Dateimenge (`4aa4f9a`) | Vorhersagbar vorab? |
|---|---|---|
| `lead-field` | `models.py` (610-Z. God-File), `routes/leads.py`, `routes/api.py`, `templates/leads/form.html`, `tests/e2e/test_api.py` **+ Falle:** `services/mcp_server.py` (dupliziert Lead-Konstruktion) | **Nein** — die MCP-Duplikat-Falle macht das wahre Set mehrdeutig: vergisst ein Lauf sie, fehlt eine Datei; nimmt sie ein anderer mit, ist es eine „Extra-Datei". 3 Läufe divergieren → **fällt 3/3-Exaktheit**. |
| `mcp-tool` | `services/mcp_server.py`, `models.py` | Teilweise — kompakt, aber `models.py` ist der God-File (jede Modelländerung kollidiert mit allem). |
| `vat-rule` | `services/invoicing/vat.py`, `tests/unit/test_vat_engine.py` | **Ja** — `vat.py` war schon bei der Baseline ein eigenes Modul. **Kaum Delta.** |
| `api-endpoint` | `routes/api.py`, `models.py`, `tests/e2e/test_api.py` | Teilweise — God-File-Kopplung; Note-Read-Logik existierte nicht zentral → Gefahr der Ad-hoc-Platzierung. |
| `new-domain` | **undefiniert** — kein Scaffold; eine neue Domäne ist handgebaut, Platzierung frei (neue `routes/x.py`? Anbau an `models.py`? `services/x.py`?) | **Nein, prinzipiell** — es gibt kein ableitbares Set. Maximale Divergenz. |

## Delta (= der gemessene Nutzen, ehrlich)

- **Größter Gewinn — `new-domain`:** von „kein ableitbares Set"
  (handgebaut, beliebig platzierbar = exakt „random code in random files")
  zu einem **deterministischen 8-Datei-Set per einem Befehl**. Das ist die
  Kern-These des Plans, hier am stärksten belegt — *vorbehaltlich* R6
  (Enforcement skaliert nicht mit, s. `new-domain.expected`).
- **Zweitgrößter — `lead-field` & `api-endpoint`:** von einem 610-Zeilen-
  God-File + Duplikat-Falle (Set vorab **nicht** zuverlässig bestimmbar →
  fällt die 3/3-Exaktheits-Schwelle) zu einem aus Protokoll+Struktur
  **ableitbaren** Set in isolierten Domänen-Paketen. Die Schritt-7-
  Entdopplung killt die MCP-Duplikat-Falle (`api-endpoint` reused den
  Service statt zu duplizieren).
- **Kein nennenswerter Gewinn — `vat-rule`:** der Compliance-Kern war
  bereits modular; Set in beiden Bäumen identisch (2 Dateien). Ehrliche
  Aussage: nicht jede Aufgabe profitiert — der Plan wirkt dort, wo vorher
  Streuung/Duplikation war, nicht als pauschale Verbesserung.

## Honest verdict (vorbehaltlich der echten N=3-Läufe)

Die Struktur **macht das Set vorhersagbar**, wo es bei der Baseline durch
God-File + Duplikation Glücksspiel war (3 von 5 Aufgaben). Die Probe wird
das *quantifiziert* bestätigen oder widerlegen — aber sie wird **gleichzeitig
zwei Protokoll-Lücken aufdecken** (fehlende Migration R3 bei `lead-field`,
nicht-gepatchter Contract R6 bei `new-domain`): „Agent landet exakt dort"
ist dann wahr, „die Änderung ist damit vollständig/erzwungen-konsistent"
nicht durchgängig. Das ist genau die Differenzierung, die das Audit verlangt
hat.
