# Solution — Govern a Federated Retail Data Platform

The completed, executed capstone (answer key) for reviewers. **`project.ipynb`** is the same
notebook the learner receives, with every `TODO(you)` cell implemented and every deliverable
written to a "Meets/Exceeds" standard, executed top-to-bottom with outputs.

## Files

| File | What it is |
|---|---|
| `project.ipynb` | The completed answer key, executed with outputs. |
| `governance_toolkit.py` | Provided governance engine + `make_catalog()` factory. Identical to the learner's copy. |
| `aws_backend.py` | Provided live AWS backend (real Glue / Lake Formation / Athena for Steps 2, 7, 9). |
| `setup_aws.py` | Provisioner seeder (Glue DB + S3 data with the deliberate gaps). |
| `requirements.txt` | Python dependencies. |
| `seed_data.py` | Provided deterministic four-domain seed. Identical to the learner's copy. |
| `terraform/governed-data-product/main.tf` | Provided read-only IaC module read in Step 7. |

## Run / re-execute

```
pip install -r requirements.txt
export CARDINAL_LF_LIVE=1     # to re-execute against live AWS; omit for the local fallback
jupyter lab project.ipynb           # to inspect interactively
```

The seed is deterministic (`SEED=42`), so every run yields identical data and outputs —
reviewers see exactly what the learner sees. Re-running the notebook rebuilds the platform from
scratch.

> **Backend.** Step 0's `make_catalog()` returns the **live AWS engine** when the lab is
> provisioned — Steps 2 (Glue), 7 (Lake Formation + Athena, per-persona assume-role), and 9
> (governance audit/remediation) run against real AWS — otherwise an equivalent **local engine**
> (scoped SQLite views) so reviewers can re-execute offline. The graded path is AWS;
> `lf_backend()` reports the active path. Provisioning is specified in the capstone
> `environment-provisioning-request.md`; seed an account with `python3 setup_aws.py`.

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
