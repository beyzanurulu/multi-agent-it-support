"""Validate analytics SQL before it reaches the read-only `run_sql` tool.

Accepts exactly one SELECT (CTEs/UNIONs allowed) over allowlisted relations,
rejects dangerous functions, and enforces LIMIT <= 200.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"v_tickets", "departments"}
DENIED_FUNCTIONS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import",
                    "lo_export", "dblink", "set_config", "pg_terminate_backend", "current_setting"}
MAX_LIMIT = 200


@dataclass
class SqlCheck:
    ok: bool
    sql: str = ""
    reason: str = ""


def check_sql(sql: str) -> SqlCheck:
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="postgres") if s is not None]
    except sqlglot.errors.SqlglotError as exc:  # ParseError, TokenError (e.g. LLM prose)
        return SqlCheck(False, reason=f"parse error: {exc}".splitlines()[0])
    if len(statements) != 1:
        return SqlCheck(False, reason="exactly one statement allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        return SqlCheck(False, reason=f"only SELECT allowed, got {tree.key.upper()}")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                             exp.Alter, exp.Command, exp.Into)):
            return SqlCheck(False, reason=f"forbidden clause {node.key.upper()}")
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name not in ALLOWED_TABLES and name not in cte_names:
            return SqlCheck(False, reason=f"table not allowed: {name}")
        if table.db and table.db.lower() not in ("", "public"):
            return SqlCheck(False, reason=f"schema not allowed: {table.db}")
    for func in tree.find_all(exp.Func):
        fname = (func.sql_name() if not isinstance(func, exp.Anonymous) else func.name).lower()
        if fname in DENIED_FUNCTIONS:
            return SqlCheck(False, reason=f"function not allowed: {fname}")

    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError):
            return SqlCheck(False, reason="LIMIT must be a constant")
    if current is None or current > MAX_LIMIT:
        tree = tree.limit(MAX_LIMIT)
    return SqlCheck(True, sql=tree.sql(dialect="postgres"))
