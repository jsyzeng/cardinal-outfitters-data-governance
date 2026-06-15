# Govern a Federated Retail Data Platform — Solution (Reviewer Toolkit)

**nd038 — Data Architect, Course 4 (Data Governance) — Capstone Project**

This repository holds the **fully working solution** for the Course 4 capstone, for use in
the reviewer toolkit. The completed, executed project is in **`solution/project.ipynb`**;
the provided toolkit it runs on lives alongside it.

For project-design context, see [Project Creation Guidance](./Project_Creation_Guidance.md).

## What this project asks of the learner

The learner is the data architect for *Cardinal Outfitters*, a federation of four retail
domains under simultaneous **GDPR** and **CSRD** pressure. Across ten steps they reconcile
catalog metadata, encode obligations in a data contract, interpret data quality, steward
master data, read lineage and specify monitoring, enforce Lake Formation access for four
personas, verify cross-domain reporting traceability, stand up governance operations, and
write an architect's brief. It is a judgment project (~5 hours): the learner runs provided
tooling and produces decision-oriented artifacts.

## Running the solution

```
pip install pandas jsonschema pyyaml jupyterlab
cd solution
jupyter lab project.ipynb
```

`solution/project.ipynb` is the **answer key**, executed with expected outputs. It runs
locally with no AWS account (see the hybrid-backend note in `solution/README.md`).

## Mapping to the rubric

Each step produces exactly one graded deliverable; the criteria (C1–C10 plus the architect's
brief) line up one-to-one with the steps. The solution demonstrates a "Meets/Exceeds" answer
for every criterion — in particular, the Step 7 verification table shows all four personas
**PASS** (column-, row-, tag-, and metadata-level access enforced).

## Contents

| Path | Purpose |
|---|---|
| `solution/project.ipynb` | Completed, executed answer key |
| `solution/governance_toolkit.py` | Provided governance engine |
| `solution/seed_data.py` | Provided deterministic seed |
| `solution/terraform/governed-data-product/main.tf` | Provided read-only IaC (Step 7) |
| `Project_Creation_Guidance.md` | Udacity project-design standards |
