# ADR-007: BillingOrder-Vertrag — die CRM↔Billing-Naht

**Status:** Akzeptiert (2026-05-18)

## Kontext

Das Invoicing-Subsystem (`services/invoicing/`, ~90 % Coverage, §14 UStG /
ZUGFeRD) soll ein **extraktions-fähiger Bounded Context** werden (Beschluss
s. `docs/scaling-roadmap.md` + `ARCHITECTURE.md`). Der einzige echte
Inward-Reach von Billing ins CRM war
`finalize.py::_snapshot_customer()`, das `Lead.{salutation,street,street2,
postal_code,city,country_code,vat_id,is_business,email,name,company}` direkt
las. Zusätzlich importierten alle 8 Invoicing-Module ihre — seit Schritt 4
billing-eigenen — Modelle über den aggregierenden `models`-Shim, der auch
`Lead`/`domains/*` re-exportiert.

Ein späterer physischer Service-Split soll eine reine Deploy-Entscheidung
bleiben, kein Rewrite. Dafür muss die *Code-Grenze* jetzt sauber sein.

## Optionen geprüft

1. **Caller baut `BillingOrder`, Billing nimmt nur den Vertrag entgegen;
   `customer_resolver` wird via `FinalizeOptions` injiziert** *(gewählt)*
2. Caller schreibt den Customer-Snapshot vor `finalize_invoice` direkt auf
   den Draft; `_snapshot_customer` entfällt ganz
3. Default-Resolver in `finalize.py`, der `Lead` lädt
4. Physischer Split jetzt (zwei Apps + HTTP/Queue-Vertrag)

## Entscheidung

**Option 1.** Ein reines pydantic-DTO `app/contracts/billing_order.py`
(`BillingOrder` + `BillingCustomer`/`Issuer`/`Line`/`Meta`, alle `frozen`).
Die CRM-Seite (`app/domains/leads/billing_export.build_billing_customer`)
projiziert `Lead` → `BillingCustomer`; der Resolver wird wie
`renderer`/`archiver`/`vies_gate` über `FinalizeOptions` eingespritzt
(konsistent mit dem bestehenden Muster). Die Merge-Logik samt
`name or company`-Präzedenz bleibt **byte-äquivalent** in
`_snapshot_customer()` — nur die Datenquelle ändert sich (die einzige
inhaltliche Änderung im ganzen Migrationsplan; sonst move-not-rewrite).

Alle Invoicing-Modell-Importe wurden vom `models`-Shim auf
`app.domains.billing.models` (Billings *eigene* Modelle) repointet.

- Option 2 verschiebt den Snapshot-Zeitpunkt (Draft- statt Finalize-Zeit) =
  echte Verhaltensänderung; verworfen.
- Option 3 würde `services.invoicing → app.domains.leads` erzwingen — genau
  die verbotene Kante; verworfen.
- Option 4 ist die Ops-Steuer (Idempotenz/Outbox/Versionierung) einer
  Single-Process-App; erst bei Split-Trigger (Stufe B / Schritt 10).

## Konsequenz / Erzwingung

`import-linter` (`pyproject.toml`) wird von der Saat
`services.invoicing ↛ routes` zur vollen Billing-Regel geschärft:
`services.invoicing` darf **nichts** aus `routes`, `app.domains.leads`
oder `app.domains.proposals` importieren. Der `models`-Shim re-exportiert
`domains/*`; ihn nennt die Regel **nicht** explizit (ein einzelnes
`.py`-Modul ist kein gültiges grimp-`root_package`) — der `forbidden`-
Contract erkennt indirekte Importe per Default, also wird ein Reach
`services.invoicing → models → app.domains.leads` **transitiv** erkannt.
Das ist die exakte Kodierung der Roadmap-Regel „billing ↛ domains/*/
models" ohne das nackte `models`-Modul. Erlaubt bleiben
`app.domains.billing.*` (eigene Modelle), `app.contracts.*`,
`app.core.*`, `app.shared.*`. Das ist die `domains/billing/*`-Zeile der
Roadmap-Kantentabelle; die volle Interface-Kantenmenge folgt in Schritt 7.

Akzeptanz-Gate: import-linter-Regel grün **und** 90 %-Invoicing-Suite grün
**und** die 140 Characterization-Tests unverändert grün (0 `tests/`-Diff im
`characterization/`-Netz; die Integration-Helfer ziehen den Snapshot über
den `BillingOrder`-Naht-Adapter nach, Zusicherungen unverändert).
