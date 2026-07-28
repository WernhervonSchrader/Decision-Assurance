# Decision Assurance Engine

Deterministische Python-Referenzimplementierung für den öffentlichen Draft der
Decision Assurance Specification (DAS) v0.1.0.

Die Engine bewertet strukturierte Evidenz, Constraints, Policies,
Akteurstrennung und Risikoindikatoren. Jede Bewertung endet in genau einem
Governance-Zustand:

- `PASS`: Alle erforderlichen Prüfungen sind erfüllt.
- `REVIEW`: Eine qualifizierte menschliche Prüfung ist erforderlich.
- `BLOCK`: Eine zwingende Regel verhindert die Ausführung.

Die Präzedenz ist fest und nachvollziehbar: `BLOCK > REVIEW > PASS`.

## Enthaltener Funktionsumfang

- domänenneutraler, deterministischer Governance-Kern
- strukturierte Findings und stabile Reason Codes
- Assurance Report gemäß öffentlichem JSON-Schema
- hash-verkettete Audit-Events
- Validierung aller sieben öffentlichen DAS-Verträge
- Adapter und Regressionstests für DATS v0.1.0
- CLI für lokale JSON-Bewertungen

Dies ist eine Referenzimplementierung und keine Zertifizierung oder Aussage zur
Produktionsreife.

## Installation und Tests

Python 3.10 oder neuer wird benötigt.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Unter Linux und macOS wird entsprechend `.venv/bin/python` verwendet.

## Verwendung als Bibliothek

```python
from decision_assurance import DecisionAssuranceEngine

request = {
    "decision_id": "QUOTE-42",
    "evidence": [
        {"id": "PRICE-LIST", "verifiable": True, "supports_claim": True}
    ],
    "constraints": [
        {"id": "MARGIN", "hard": True, "satisfied": True}
    ],
    "policies": [],
    "actors": {"generator": "sales-agent", "approver": "rules-engine"},
    "risk": {"high_impact": False, "unresolved_uncertainty": False},
}

result = DecisionAssuranceEngine().assess(request)
print(result.outcome.value)       # PASS
print(result.report)              # Assurance Report
print(result.audit_events)        # verkettetes Audit-Protokoll
```

## CLI

Ein natives Assessment oder ein DATS-Szenario kann direkt ausgewertet werden:

```powershell
.\.venv\Scripts\decision-assurance.exe tests\scenarios\dats-007.json
```

Die CLI gibt den Assurance Report als JSON aus.

## Projektstruktur

```text
schemas/                         öffentliche DAS-Vertragsschemas
src/decision_assurance/
  adapters.py                    DATS-/Request-Normalisierung
  audit.py                       kanonische Hashes und Audit-Verkettung
  engine.py                      Validierung und Governance
  models.py                      Outcome-, Finding- und Result-Modelle
  validation.py                  JSON-Schema-Vertragsvalidierung
tests/scenarios/                 zehn DATS-v0.1.0-Szenarien
tests/                           Contract- und Engine-Tests
```

## Entwicklungsreihenfolge

Der nächste Ausbauschritt ist eine persistente Assurance API für Assessments,
Reports, Review-Aktionen und Audit-Abfragen. Sie wird auf diesem Kern aufbauen,
ohne die Governance-Regeln in die Transportschicht zu duplizieren.

## Repository-Arbeitsregel

GitHub ist die Quelle der Wahrheit: Vor der Arbeit wird `git pull origin main`
ausgeführt; abgeschlossene Änderungen werden bewusst committed und anschließend
gepusht.

## Lizenz

Der Code steht unter der Apache License 2.0. Normative Spezifikationstexte
unterliegen gegebenenfalls einer getrennten Lizenzierung.
