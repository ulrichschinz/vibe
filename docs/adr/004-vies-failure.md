# ADR-004: VIES-Failure-Verhalten

**Status:** Akzeptiert (2026-05-09)

## Kontext

R-16 fordert eine VIES-Validierung jeder EU-USt-IdNr. zum Finalize-Zeitpunkt
einer Reverse-Charge-Rechnung. Das Ergebnis muss unveränderbar archiviert
werden.

VIES (das offizielle EU-System) ist regelmäßig nicht erreichbar oder antwortet
mit "service_unavailable". Wir müssen entscheiden, was wir in diesem Fall tun.

## Optionen geprüft

1. **Hart blocken, kein Override**
2. **Hart blocken, Admin-Override mit Pflichtbegründung** *(gewählt)*
3. **Warnen, finalisieren erlauben, Audit speichern**

## Entscheidung

**Option 2.** `invalid` blockt unwiderruflich. `service_unavailable` blockt für
Editor-Rollen, kann aber von einem Admin mit ausgefüllter Pflichtbegründung
übersteuert werden. Jede VIES-Antwort (gültig, ungültig, unavailable, override)
wird mit Zeitstempel, abgefragter VAT-ID, Rohantwort und (bei override)
Begründung in `viesauditentry` archiviert.

## Begründung

- **Hartes Block bei `invalid`** ist nicht-verhandelbar: Eine Reverse-Charge-
  Rechnung mit ungültiger USt-IdNr. ist rechtlich riskant. Kein Override.
- **Admin-Override bei `service_unavailable`** verhindert, dass ein VIES-Ausfall
  den Geschäftsbetrieb lahmlegt. Der Override ist Admin-only, erfordert eine
  Begründung, und landet im Audit. Sollte das Finanzamt prüfen, lässt sich
  belegen, *warum* trotz fehlender Live-Antwort finalisiert wurde (z. B.
  „Kunde verifiziert per Telefon am 09.05.2026, Vertragsnummer XYZ").
- **Kein Caching am Finalize:** Jeder Finalize-Call macht einen Live-Check.
  Der Audit-Eintrag muss den exakten Zeitpunkt der Validierung enthalten —
  ein gecachetes Ergebnis von vor Stunden wäre nicht aussagekräftig.

## Konsequenzen

**Positiv:**
- Compliant mit R-16 (Audit jeder Antwort).
- Operativ tragbar — VIES-Ausfälle blockieren nicht dauerhaft.
- Audit-Trail nachvollziehbar.

**Negativ:**
- Override-Misbrauch ist möglich, wenn die Admin-Rolle zu freigiebig vergeben
  wird. Mitigation: Auftraggeber ist Single-Operator; nur er hat Admin-Rechte.
- Bei VIES-Dauerausfall müssen alle EU-B2B-Rechnungen Override-Audit-Einträge
  haben — das ist erkennbar und vor dem Finanzamt zu rechtfertigen.

## Alternativen verworfen

- **Option 1 (kein Override):** Würde bei VIES-Ausfall den Geschäftsbetrieb
  blockieren. Im echten Leben kommt das vor.
- **Option 3 (warnen + durchwinken):** Verlöre die Audit-Stärke. Eine VIES-
  Antwort, die "unavailable" sagt, ist kein Beweis, dass die USt-IdNr. korrekt
  ist. Ohne explizite Override-Begründung wäre vor dem Finanzamt schwer zu
  argumentieren.

## Verifikation

- `tests/integration/test_vies_audit.py::test_invalid_vat_id_blocks_and_audits`
  → invalid blockt, Audit geschrieben.
- `test_service_unavailable_blocks_without_override` → Editor blockiert.
- `test_service_unavailable_admin_override_succeeds` → Admin mit Begründung
  kommt durch, Audit-Status `override`, Begründung gespeichert.
- `test_override_without_reason_rejected` → Override ohne Begründung wird
  abgelehnt.
