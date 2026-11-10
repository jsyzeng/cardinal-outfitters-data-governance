"""
aws_backend.py — the LIVE AWS backend for the Cardinal Outfitters capstone.

PROVIDED FILE. Students do not edit it; they call into it from the notebook exactly as
they call the local engine. `make_catalog()` in governance_toolkit returns this class
instead of the local `GovernedCatalog` when the environment is live
(CARDINAL_LF_LIVE=1 + awswrangler + working AWS credentials).

WHAT IS REAL HERE
-----------------
This backend performs *actual* AWS operations for the three hands-on steps:

    MP2  catalog_audit / set_table_metadata / tag_column  -> AWS Glue (GetTables, UpdateTable)
    MP7  assign_tag / grant_* / create_row_filter / reset -> AWS Lake Formation
    MP7  query_as(persona, sql)                           -> STS assume-role + Amazon Athena
    MP9  governance_audit                                 -> rolls up the real Glue + LF state

Everything else (quality MP4, MDM MP5, lineage MP6, reporting MP8) is inherited unchanged
from the local engine and runs against the in-process synthetic dataset — those steps are
intentionally not part of the live-AWS scope for this course.

DESIGN: AwsGovernedCatalog subclasses GovernedCatalog. Each overridden method makes the
real AWS call AND keeps the in-memory grant/catalog mirror in sync (via super().<method>),
so grants_summary(), the local query fallback, and the MP9 access-control check all stay
coherent without extra AWS round-trips.

NOTE: this file is verified against the environment-provisioning-request.md spec but has
not been executed end-to-end outside a provisioned account — `# pragma: no cover` marks the
live-only paths. The platform team seeds the Glue database + S3 data with setup_aws.py.
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

from governance_toolkit import GovernedCatalog, PERSONAS, AccessDenied


# Catalog id default is the account id; resources live in one region (see provisioning §Region).
def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


class AwsGovernedCatalog(GovernedCatalog):  # pragma: no cover - live AWS only
    """Live AWS implementation of the governance engine (Glue + Lake Formation + Athena)."""

    def __init__(self, db_path: str = "cardinal.db"):
        # Build the local seed too: it powers the inherited as-is steps (MP4/5/6/8) and
        # serves as the in-memory mirror the access-control audit reads.
        super().__init__(db_path)

        import boto3
        self.region = _cfg("CARDINAL_AWS_REGION", "us-east-1")
        self._session = boto3.Session(region_name=self.region)
        self.glue = self._session.client("glue")
        self.lf = self._session.client("lakeformation")
        self.sts = self._session.client("sts")

        self.account_id = self.sts.get_caller_identity()["Account"]
        # The Glue database that holds the governed tables (provisioned by setup_aws.py).
        # Derived from the seed (cardinal capstone or trailhead exercises) unless overridden.
        self.database = _cfg("CARDINAL_GLUE_DATABASE", self.catalog.database)
        self.athena_workgroup = _cfg("CARDINAL_ATHENA_WORKGROUP", self.database)
        self.results_bucket = _cfg("CARDINAL_S3_RESULTS",
                                   f"s3://{self.account_id}-{self.database}-athena-results/")

        # Resolve persona role ARNs (placeholder ACCOUNT -> real account; override per-role
        # via CARDINAL_ROLE_<NAME> if the provisioner used different names).
        self.personas = {
            role: os.environ.get(f"CARDINAL_ROLE_{role.upper()}",
                                 arn.replace("ACCOUNT", self.account_id))
            for role, arn in PERSONAS.items()
        }
        self.bootstrap_aws()

    # ----------------------------------------------------------------------- #
    # Setup / verification
    # ----------------------------------------------------------------------- #

    def bootstrap_aws(self) -> None:
        """Verify the provisioned Glue database is reachable (data is seeded by setup_aws.py)."""
        try:
            self.glue.get_database(Name=self.database)
        except Exception as e:
            raise RuntimeError(
                f"Glue database {self.database!r} not found in {self.region}. "
                f"Ask the platform team to run setup_aws.py (see environment-provisioning-request.md)."
            ) from e

    # ----------------------------------------------------------------------- #
    # MP2 — metadata reconciliation against the real Glue Data Catalog
    # ----------------------------------------------------------------------- #

    def _glue_tables(self) -> list[dict]:
        tables, token = [], None
        while True:
            kw = {"DatabaseName": self.database}
            if token:
                kw["NextToken"] = token
            resp = self.glue.get_tables(**kw)
            tables.extend(resp.get("TableList", []))
            token = resp.get("NextToken")
            if not token:
                break
        return tables

    # Table-level governance classification is stored under this Glue Parameter key,
    # NOT "classification": awswrangler's to_parquet(dataset=True, table=...) already
    # stamps every table with Parameters["classification"] = "parquet" (its own file-format
    # marker), which would otherwise make every table look governance-classified from the
    # moment it's written, hiding real missing_classification gaps. Column-level Parameters
    # don't have this collision (awswrangler doesn't set a per-column "classification"), so
    # tag_column() below keeps using "classification" at the column level unchanged.
    _GOVERNANCE_CLASSIFICATION_KEY = "governance_classification"

    def catalog_audit(self) -> pd.DataFrame:
        """One row per governance gap, read live from Glue table & column Parameters."""
        rows = []
        domain_of = {t: tm.domain for t, tm in self.catalog.tables.items()}
        for tbl in self._glue_tables():
            name = tbl["Name"]
            params = tbl.get("Parameters", {})
            domain = params.get("domain", domain_of.get(name, "(unknown)"))
            for attr, param_key in (("owner", "owner"),
                                    ("classification", self._GOVERNANCE_CLASSIFICATION_KEY),
                                    ("retention", "retention")):
                if not params.get(param_key):
                    rows.append({"table": name, "domain": domain,
                                 "gap_type": f"missing_{attr}", "detail": attr})
            for col in tbl.get("StorageDescriptor", {}).get("Columns", []):
                if not col.get("Parameters", {}).get("classification"):
                    rows.append({"table": name, "domain": domain,
                                 "gap_type": "untagged_column",
                                 "detail": f"{col['Name']} (type {col.get('Type','')})"})
        return pd.DataFrame(rows)

    def set_table_metadata(self, table, owner=None, classification=None, retention=None) -> None:
        super().set_table_metadata(table, owner, classification, retention)  # mirror
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        params = ti.setdefault("Parameters", {})
        for k, v in (("owner", owner),
                     (self._GOVERNANCE_CLASSIFICATION_KEY, classification),
                     ("retention", retention)):
            if v is not None:
                params[k] = v
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    def tag_column(self, table, column, classification) -> None:
        super().tag_column(table, column, classification)  # mirror
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        for col in ti.get("StorageDescriptor", {}).get("Columns", []):
            if col["Name"] == column:
                col.setdefault("Parameters", {})["classification"] = classification
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    # ----------------------------------------------------------------------- #
    # MP7 — Lake Formation grants (real), mirrored locally
    # ----------------------------------------------------------------------- #

    def _principal(self, role: str) -> dict:
        return {"DataLakePrincipalIdentifier": self.personas[role]}

    def _table_resource(self, table: str) -> dict:
        return {"Table": {"CatalogId": self.account_id,
                          "DatabaseName": self.database, "Name": table}}

    def grant_columns(self, role, table, exclude=None, include=None) -> None:
        super().grant_columns(role, table, exclude=exclude, include=include)  # mirror
        allowed = self._grants[role].table_grants[table].columns
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"TableWithColumns": {"CatalogId": self.account_id,
                                           "DatabaseName": self.database, "Name": table,
                                           "ColumnNames": allowed}},
            Permissions=["SELECT"])

    def create_row_filter(self, name, table, expr) -> None:
        super().create_row_filter(name, table, expr)  # mirror
        all_cols = self._cols(table)
        try:
            self.lf.create_data_cells_filter(TableData={
                "TableCatalogId": self.account_id, "DatabaseName": self.database,
                "TableName": table, "Name": name,
                "RowFilter": {"FilterExpression": expr},
                "ColumnNames": all_cols})
        except self.lf.exceptions.AlreadyExistsException:
            pass

    def grant_rows(self, role, table, filter_name) -> None:
        super().grant_rows(role, table, filter_name)  # mirror
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"DataCellsFilter": {"TableCatalogId": self.account_id,
                                          "DatabaseName": self.database,
                                          "TableName": table, "Name": filter_name}},
            Permissions=["SELECT"])

    def assign_tag(self, table, key, value) -> None:
        super().assign_tag(table, key, value)  # mirror (catalog.lf_tags)
        try:
            self.lf.create_lf_tag(TagKey=key, TagValues=[value])
        except self.lf.exceptions.AlreadyExistsException:
            pass
        except self.lf.exceptions.InvalidInputException as e:
            # LF raises InvalidInputException (not AlreadyExistsException) when the tag
            # key already exists, e.g. the same key assigned to a second table/step.
            if "already exist" not in str(e).lower():
                raise
            try:
                self.lf.update_lf_tag(TagKey=key, TagValuesToAdd=[value])
            except self.lf.exceptions.InvalidInputException:
                pass  # value already present on the tag
        self.lf.add_lf_tags_to_resource(
            Resource=self._table_resource(table),
            LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}])

    def grant_by_tag(self, role, key, value) -> None:
        super().grant_by_tag(role, key, value)  # mirror
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"LFTagPolicy": {"CatalogId": self.account_id, "ResourceType": "TABLE",
                                      "Expression": [{"TagKey": key, "TagValues": [value]}]}},
            Permissions=["SELECT", "DESCRIBE"])

    def grant_describe_only(self, role) -> None:
        super().grant_describe_only(role)  # mirror
        # Athena must resolve the database to plan a DESCRIBE/SELECT, so DESCRIBE on the
        # database is required in addition to DESCRIBE on each table -- table-only leaves
        # every query failing with "Insufficient Lake Formation permission(s)".
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"Database": {"CatalogId": self.account_id, "Name": self.database}},
            Permissions=["DESCRIBE"])
        for t in self.tables():
            self.lf.grant_permissions(
                Principal=self._principal(role),
                Resource=self._table_resource(t),
                Permissions=["DESCRIBE"])

    def revoke_all(self, role) -> None:
        self._revoke_role_in_lf(role)
        super().revoke_all(role)  # clear mirror

    def reset(self) -> None:
        """Re-baseline real Lake Formation: revoke every persona grant, drop filters/tags."""
        for role in list(self.personas):
            self._revoke_role_in_lf(role)
        # delete data-cells filters we created
        for name, rf in list(self._row_filters.items()):
            try:
                self.lf.delete_data_cells_filter(
                    TableCatalogId=self.account_id, DatabaseName=self.database,
                    TableName=rf["table"], Name=name)
            except Exception:
                pass
        # remove LF-Tags from tables that carry them
        for t, tm in self.catalog.tables.items():
            for key, value in list(tm.lf_tags.items()):
                try:
                    self.lf.remove_lf_tags_from_resource(
                        Resource=self._table_resource(t),
                        LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}])
                except Exception:
                    pass
        super().reset()  # clear mirror

    def _revoke_role_in_lf(self, role: str) -> None:
        """Best-effort revoke of whatever this role currently holds (per the mirror)."""
        g = self._grants[role]
        p = self._principal(role)
        for table, tg in g.table_grants.items():
            res = ({"TableWithColumns": {"CatalogId": self.account_id, "DatabaseName": self.database,
                                         "Name": table, "ColumnNames": tg.columns}}
                   if tg.columns is not None else self._table_resource(table))
            _safe(lambda: self.lf.revoke_permissions(Principal=p, Resource=res, Permissions=["SELECT"]))
        for key, value in g.tag_grants:
            _safe(lambda: self.lf.revoke_permissions(
                Principal=p,
                Resource={"LFTagPolicy": {"CatalogId": self.account_id, "ResourceType": "TABLE",
                                          "Expression": [{"TagKey": key, "TagValues": [value]}]}},
                Permissions=["SELECT", "DESCRIBE"]))
        if g.describe_only:
            _safe(lambda: self.lf.revoke_permissions(
                Principal=p,
                Resource={"Database": {"CatalogId": self.account_id, "Name": self.database}},
                Permissions=["DESCRIBE"]))
            for t in self.tables():
                _safe(lambda: self.lf.revoke_permissions(
                    Principal=p, Resource=self._table_resource(t), Permissions=["DESCRIBE"]))

    # ----------------------------------------------------------------------- #
    # MP7 verification — assume each persona role and query via real Athena
    # ----------------------------------------------------------------------- #

    def _query_as_live(self, role: str, sql: str) -> pd.DataFrame:
        import awswrangler as wr
        import boto3

        from governance_toolkit import _is_describe

        creds = self.sts.assume_role(
            RoleArn=self.personas[role], RoleSessionName=f"capstone-{role}")["Credentials"]
        sess = boto3.Session(region_name=self.region,
                             aws_access_key_id=creds["AccessKeyId"],
                             aws_secret_access_key=creds["SecretAccessKey"],
                             aws_session_token=creds["SessionToken"])
        try:
            if _is_describe(sql):
                # DESCRIBE/SHOW COLUMNS results come back as one tab-packed text value per
                # row (no real CSV header), which breaks awswrangler's CSV-based result
                # parser (it silently returns zero columns) -- parse the raw Athena rows.
                return self._describe_live(sess, sql)
            # ctas_approach=False: awswrangler's default CTAS path creates (then drops) a
            # temporary Glue table to stage results, which needs glue:CreateTable/DeleteTable
            # -- permissions a least-privilege persona role intentionally does not have. The
            # non-CTAS path only needs StartQueryExecution/GetQueryResults + the Lake
            # Formation-vended S3 read, which the persona policy already grants.
            return wr.athena.read_sql_query(
                sql, database=self.database, workgroup=self.athena_workgroup,
                s3_output=self.results_bucket, boto3_session=sess, ctas_approach=False)
        except Exception as e:
            # Lake Formation / Athena denials surface as a query error, in several wordings
            # depending on WHAT is denied: a flat-out AccessDeniedException from Glue/LF
            # before the query even runs, or (for a persona granted zero columns, e.g. the
            # metadata-only auditor) Presto's "Relation contains no accessible columns" once
            # Athena runs the query. Recognize all of them so verify_step7's denial checks
            # test real live enforcement instead of silently falling back to the local engine.
            msg = str(e).lower()
            denial_markers = ("accessdenied", "not authorized", "access denied",
                              "insufficient lake formation permission",
                              "no accessible columns", "permission denied")
            if any(m in msg for m in denial_markers):
                raise AccessDenied(f"{role}: {e}") from None
            raise

    def _describe_live(self, sess, sql: str) -> pd.DataFrame:
        """Run a DESCRIBE/SHOW COLUMNS statement and parse Athena's raw result rows.

        Each row comes back as a single tab-padded string (col_name, data_type, comment),
        not separate fields -- split on whitespace runs and build the DataFrame by hand.
        """
        import time

        athena = sess.client("athena")
        qid = athena.start_query_execution(
            QueryString=sql, QueryExecutionContext={"Database": self.database},
            WorkGroup=self.athena_workgroup,
            ResultConfiguration={"OutputLocation": self.results_bucket})["QueryExecutionId"]
        for _ in range(60):
            status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
            if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(0.5)
        if status["State"] != "SUCCEEDED":
            raise RuntimeError(status.get("StateChangeReason", status["State"]))

        rows = []
        paginator = athena.get_paginator("get_query_results")
        for page in paginator.paginate(QueryExecutionId=qid):
            for row in page["ResultSet"]["Rows"]:
                raw = row["Data"][0].get("VarCharValue", "")
                parts = [p.strip() for p in raw.split("\t")]
                parts = (parts + ["", "", ""])[:3]   # pad/truncate to exactly 3 fields
                rows.append(parts)
        return pd.DataFrame(rows, columns=["col_name", "data_type", "comment"])


def _strip_table_input(table: dict) -> dict:
    """Turn a GetTable response into a valid UpdateTable TableInput (drop read-only keys)."""
    keep = ("Name", "Description", "Owner", "Retention", "StorageDescriptor", "PartitionKeys",
            "ViewOriginalText", "ViewExpandedText", "TableType", "Parameters", "TargetTable")
    return {k: table[k] for k in keep if k in table}


def _safe(fn):
    try:
        fn()
    except Exception:
        pass
