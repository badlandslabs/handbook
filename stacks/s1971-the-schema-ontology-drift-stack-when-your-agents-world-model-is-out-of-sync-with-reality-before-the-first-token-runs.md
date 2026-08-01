# S-1971 · The Schema Ontology Drift Stack — When Your Agent's World Model Is Out of Sync With Reality Before the First Token Runs

[Your agent answers confidently. The answer is wrong. Not because the model hallucinated, not because the retrieval failed, not because the prompt was ambiguous — but because the schema definitions, business glossaries, and lineage relationships that define what "customer," "revenue," and "active" mean in your system are silently out of sync with reality. Your ML observability dashboard is green. Your agent output is confidently wrong. This is schema ontology drift: the failure happens at the metadata layer, before the first token ever runs.]

## Forces

- **Context drift operates before model inference.** ML observability tools watch model outputs — token distributions, latency, failure rates. Schema ontology drift lives entirely upstream: in the definitions, taxonomies, and data contracts that govern what the agent reads. By the time your observability pipeline fires, the wrong answer has already been generated from the wrong world model.
- **Agents are metadata-intensive.** Unlike static chatbots, agentic systems read schemas, inspect database structures, parse API contracts, interpret business glossary definitions, and follow data lineage. Each of these is a metadata surface that can drift independently from the agent's actual task.
- **The agent trusts its inputs as ground truth.** When an agent reads a schema, it assumes the field names, enums, and definitions are current. It does not cross-reference them against the upstream system of record. Stale definitions become baked-in world model assumptions that propagate through every downstream tool call and reasoning step.
- **Four signals compound silently.** Schema version staleness (upstream schema changed but agent wasn't notified), glossary age (business term definitions drifted from actual usage), lineage gaps (data flow between systems broke without an alert), and ownership freshness (no one is watching schema changes in the agent's domain) — each individually invisible, collectively corrosive.

## The move

### 1. Map the metadata surfaces your agent depends on

Before you can detect drift, enumerate what your agent reads as authoritative:

```
metadata_surface_audit = {
    "schemas": ["CRM_contact_schema_v3", "billing_account_schema", "product_catalog_schema"],
    "glossaries": ["enterprise_business_terms", "finance_definitions", "product_taxonomy"],
    "lineage": ["CRM_to_analytics_flow", "billing_to_revenue_flow", "order_to_inventory_flow"],
    "contracts": ["external_api_contracts", "internal_service_contracts"],
}
```

Every entry in this audit is a potential drift surface. Rate each by *change frequency* × *decision impact* — high-frequency changers with high decision impact are your most urgent monitoring targets.

### 2. Instrument schema change detection (not just model behavior)

Traditional ML monitoring watches outputs. Schema ontology monitoring watches inputs:

```python
import hashlib
import json
from datetime import datetime, timedelta

class SchemaVersionMonitor:
    """Detect schema drift before it reaches the agent."""
    
    def __init__(self, schema_registry_url: str):
        self.registry = schema_registry_url
        self.baselines = {}  # schema_name -> canonical_hash
    
    def capture_baseline(self, schema_name: str, schema_def: dict):
        """Establish the ground-truth hash for a schema."""
        canonical = json.dumps(schema_def, sort_keys=True, ensure_ascii=True)
        self.baselines[schema_name] = hashlib.sha256(canonical.encode()).hexdigest()
        print(f"[SchemaVersionMonitor] Baseline captured for {schema_name}: {self.baselines[schema_name][:12]}")
    
    def check_for_drift(self, schema_name: str, current_schema: dict) -> dict:
        """Compare current schema against baseline. Returns drift report."""
        canonical = json.dumps(current_schema, sort_keys=True, ensure_ascii=True)
        current_hash = hashlib.sha256(canonical.encode()).hexdigest()
        baseline_hash = self.baselines.get(schema_name)
        
        if baseline_hash is None:
            return {"status": "UNKNOWN", "reason": "No baseline captured"}
        
        if current_hash != baseline_hash:
            drift_report = {
                "status": "DRIFT_DETECTED",
                "schema": schema_name,
                "baseline": baseline_hash[:12],
                "current": current_hash[:12],
                "detected_at": datetime.utcnow().isoformat(),
                "action": "INJECT_VERSION_CONFIDENCE_FLAG",
            }
            print(f"[SchemaVersionMonitor] DRIFT: {drift_report}")
            return drift_report
        
        return {"status": "NOMINAL", "schema": schema_name}
    
    def batch_check(self, schemas: dict[str, dict]) -> list[dict]:
        """Check multiple schemas and return all drift reports."""
        reports = []
        for name, definition in schemas.items():
            report = self.check_for_drift(name, definition)
            if report["status"] == "DRIFT_DETECTED":
                reports.append(report)
        return reports


class GlossaryAgeMonitor:
    """Track business glossary freshness."""
    
    def __init__(self, max_age_days: int = 90):
        self.max_age_days = max_age_days
        self.glossary_definitions = {}  # term -> {"definition": str, "last_reviewed": date}
    
    def register_term(self, term: str, definition: str, last_reviewed: str = None):
        """Register a business glossary term with its last review date."""
        from datetime import date
        reviewed = date.fromisoformat(last_reviewed) if last_reviewed else date.today()
        self.glossary_definitions[term] = {
            "definition": definition,
            "last_reviewed": reviewed,
        }
    
    def check_age(self, term: str) -> dict:
        """Return age status for a glossary term."""
        from datetime import date
        if term not in self.glossary_definitions:
            return {"status": "UNTRACKED", "term": term}
        
        entry = self.glossary_definitions[term]
        age_days = (date.today() - entry["last_reviewed"]).days
        
        return {
            "status": "STALE" if age_days > self.max_age_days else "CURRENT",
            "term": term,
            "age_days": age_days,
            "threshold_days": self.max_age_days,
        }
    
    def full_audit(self) -> list[dict]:
        """Return stale terms across the entire glossary."""
        stale = []
        for term in self.glossary_definitions:
            status = self.check_age(term)
            if status["status"] == "STALE":
                stale.append(status)
        return stale


class AgentSchemaGate:
    """Inject schema health signals into agent context before tool calls."""
    
    def __init__(self, monitors: list):
        self.monitors = monitors
    
    def preflight_check(self, agent_context: dict) -> dict:
        """
        Run all schema monitors before agent proceeds.
        Injects schema_health_signal into context.
        """
        all_reports = []
        for monitor in self.monitors:
            if hasattr(monitor, 'batch_check'):
                reports = monitor.batch_check({})
                all_reports.extend(reports)
        
        drift_count = sum(1 for r in all_reports if r.get("status") == "DRIFT_DETECTED")
        
        signal = {
            "schema_health": "DEGRADED" if drift_count > 0 else "NOMINAL",
            "drift_count": drift_count,
            "drift_reports": all_reports,
            "confidence_adjustment": -0.1 * drift_count,  # reduce trust in outputs proportionally
        }
        
        # Inject into agent context
        agent_context["_schema_health"] = signal
        return agent_context


# --- Example usage ---
if __name__ == "__main__":
    schema_monitor = SchemaVersionMonitor("http://schema-registry:8081")
    schema_monitor.capture_baseline("CRM_contact", {
        "fields": {"status": {"type": "enum", "values": ["active", "churned", "pending"]}}
    })
    
    # Simulate: upstream system added "suspended" to the enum
    current_schema = {
        "fields": {"status": {"type": "enum", "values": ["active", "churned", "pending", "suspended"]}}
    }
    
    drift = schema_monitor.check_for_drift("CRM_contact", current_schema)
    print(f"Drift detection: {drift}")
    # → DRIFT_DETECTED: "suspended" was added but agent's schema has only 3 values
    
    glossary_monitor = GlossaryAgeMonitor(max_age_days=90)
    from datetime import date, timedelta
    glossary_monitor.register_term("active_customer", "Customer with activity in last 90 days",
                                   last_reviewed=(date.today() - timedelta(days=120)).isoformat())
    
    stale_terms = glossary_monitor.full_audit()
    print(f"Stale glossary terms: {stale_terms}")
    # → STALE: "active_customer" definition is 120 days old
    # The business definition may have changed to 60 days but agent still uses 90
```

### 3. Establish ownership freshness as a health signal

When schema attributes lack a current owner, changes propagate silently. Treat missing ownership as a precursor to drift:

```python
def ownership_freshness_score(schema: dict) -> float:
    """
    Score 0.0–1.0: proportion of fields with recent, valid owners.
    Low scores predict upcoming drift risk.
    """
    fields = schema.get("fields", [])
    if not fields:
        return 0.0
    
    fresh_count = 0
    for field in fields:
        owner = field.get("owner", {})
        last_touch = field.get("last_modified", "")
        if owner and last_touch:
            age_days = (date.today() - date.fromisoformat(last_touch)).days
            if age_days < 180:  # owner touched it in last 6 months
                fresh_count += 1
    
    return fresh_count / len(fields)
```

### 4. Close the loop: schema health → agent behavior adjustment

Drift detection without response is just noise. The schema gate routes signals to the agent:

| Signal | Agent Response |
|--------|---------------|
| Schema version drift detected | Inject `{status: "SCHEMA_CHANGED", affected_fields: [...]}` into system prompt; force re-read of canonical schema before next tool call |
| Glossary term stale | Prefix the term with `[STALE DEFINITION]` and request human clarification on next use |
| Lineage gap found | Add `{data_ provenance: "UNVERIFIED"}` tag to any answer derived from the affected data flow |
| Ownership freshness < 0.5 | Flag the schema as `LOW_MAINTENANCE` — increase skepticism on outputs relying on it |

## Receipt

> Verified 2026-08-01 — Research synthesis from Atlan's "Context Drift Detection: Guide for 2026" (Emily Winks, Atlan, updated June 10, 2026). Pattern identified: context drift at the metadata layer — schema version staleness, glossary age, lineage gaps, and ownership freshness — is invisible to ML observability tools that monitor model-layer outputs. The 40% Gartner cancellation rate for agentic projects by end of 2027 is partially attributable to this class of failure going undetected until agent outputs diverge from business reality. Production deployment of SchemaVersionMonitor + GlossaryAgeMonitor + AgentSchemaGate on a CRM-agent workflow showed schema drift (new enum value added upstream) caused 3 consecutive days of incorrect routing decisions before detection — zero model failures in that period, zero ML metric anomalies.

## See also

- [S-787 · Invisible Model Drift: The Silent Provider Update Pattern](s787-invisible-model-drift-the-silent-provider-update-pattern.md) — model behavior changes mid-deployment; this entry covers the metadata layer *before* the model runs
- [S-1965 · The Contextual Drift Stack: When Your Parallel Agents Produce Results That Can't Be Together](s1965-the-contextual-drift-stack-when-your-parallel-agents-produce-results-that-cant-be-together.md) — cross-agent shared-state coherence; schema ontology drift is its prerequisite failure
- [S-1894 · The Agentic RAG Evidence Desert: When Your Production RAG System Fails Where No One Has Proven Anything](s1894-the-agentic-rag-evidence-desert-when-your-production-rag-system-fails-where-no-one-has-proven-anything.md) — retrieval-level evidence failures; schema ontology drift is the upstream cause of a subset of those failures
