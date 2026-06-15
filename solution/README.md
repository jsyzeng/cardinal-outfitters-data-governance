# Solution — Govern a Federated Retail Data Platform

The completed, executed capstone (answer key) for reviewers. **`project.ipynb`** is the same
notebook the learner receives, with every `TODO(you)` cell implemented and every deliverable
written to a "Meets/Exceeds" standard, executed top-to-bottom with outputs.

## Files

| File | What it is |
|---|---|
| `project.ipynb` | The completed answer key, executed with outputs. |
| `governance_toolkit.py` | Provided governance engine (catalog, Lake Formation grants, query-as-persona, quality, lineage, MDM, reporting, audit). Identical to the learner's copy. |
| `seed_data.py` | Provided deterministic four-domain seed. Identical to the learner's copy. |
| `terraform/governed-data-product/main.tf` | Provided read-only IaC module read in Step 7. |

## Run / re-execute

```
pip install pandas jsonschema pyyaml jupyterlab
jupyter lab project.ipynb           # to inspect interactively
```

The seed is deterministic (`SEED=42`), so every run yields identical data and outputs —
reviewers see exactly what the learner sees. Re-running the notebook rebuilds the local lake
(`cardinal.db`) from scratch.

> **Hybrid backend.** `query_as()` (Step 7) uses live AWS Lake Formation + Athena when the
> environment provides per-persona assume-role; otherwise it enforces locally via scoped
> SQLite views. The local path is the default and requires no AWS account. To force the live
> path: `export CARDINAL_LF_LIVE=1` with AWS credentials and the persona role ARNs set in
> `governance_toolkit.PERSONAS`. `lf_backend()` reports the active path. The graded outcomes
> are identical under either backend.

## What the solution demonstrates per step

| Step | Deliverable | Key expected result |
|---|---|---|
| 1 | Governance model + RACI + topology | Federated model with a thin central core, single accountable owner per function |
| 2 | Reconciliation memo | 14 catalog gaps incl. untagged PII (`customer.phone`); 3 cross-domain conflicts |
| 3 | Governed data contract | Contract passes the validator after adding the governance block; propagation reasoning |
| 4 | Quality remediation plan | 8/9 expectations fail across six dimensions; source/downstream/quarantine per issue |
| 5 | Stewardship decision log | 6 ambiguous + 2 auto-merge customer dupes; survivorship = lowest `customer_id` |
| 6 | Lineage + monitoring spec | Breach at `shipment` → `order_carbon` → `quarterly_sustainability`; signals table |
| 7 | Lake Formation access | All four personas **PASS**; Terraform read-and-explain + sample IAM |
| 8 | Reporting auditability | Carbon grams-vs-kg unit defect found via reconciliation |
| 9 | Governance operations | Dashboard spec + onboarding checklist; high-severity findings triaged |
| 10 | Architect's brief | Posture, tradeoffs, next-quarter roadmap, tied to step evidence |
