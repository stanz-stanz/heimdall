"""HEIM-23 / HEIM-38 — Audit-write fail-secure invariant for src/api/**.

Closes the discipline gap that motivated the 2026-05-04 /console/ws
fix (commit 07294bd): every handler under ``src/api/`` that calls
``write_console_audit_row(...)`` must enclose the call in a
``try/except`` whose handler catches ``sqlite3.Error`` or one of the
5 named subclasses (``DatabaseError``, ``OperationalError``,
``IntegrityError``, ``DataError``, ``NotSupportedError``). An
audit-layer fault must never abort the request handler or close an
already-accepted WS connection by exception propagation.

Static AST scan. No fixtures, no DB, no app boot.

**Wrapper helpers** (see ``_WRAPPER_HELPERS`` below) are exempt from
the inner-call check; instead every callsite of the wrapper —
direct, ``asyncio.to_thread(wrapper, ...)``, OR keyword-form
``runner(fn=wrapper)`` — must itself sit inside a failsafe ``try.body``.

**Function/lambda boundary.** A writer call inside a nested
``def`` / ``async def`` / ``lambda`` is NOT counted as protected by
an outer ``try`` — the inner function may be invoked later, outside
the protection. The parent-walk stops at the first
``FunctionDef`` / ``AsyncFunctionDef`` / ``Lambda`` boundary it
crosses.

**Tuple-handler tightness.** ``except (sqlite3.Error, Exception):``
is rejected — every element of the tuple must be a sqlite3-allowed
type, otherwise the broad sibling masks programming bugs.

**Import-aware exception matching.** The visitor scans top-level
``import sqlite3 [as X]`` and ``from sqlite3 import Y [as Z]``
statements, then accepts:

* ``<module-alias>.<X>`` where ``<module-alias>`` resolves to ``sqlite3``
  and ``<X>`` is allowed.
* Bare ``<name>`` only when ``<name>`` was imported from sqlite3 at the
  top level (binding tracked through ``as`` renames).

Bare names not traceable to a sqlite3 import are rejected — closes
the namespace-collision risk where an unrelated module's local class
named ``OperationalError`` would otherwise satisfy the lint.

**Writer-call shapes.** Both bare ``write_console_audit_row(...)``
and attribute form ``audit.write_console_audit_row(...)`` are
detected. Function-name uniqueness in the codebase makes the false-
positive risk on the attribute form negligible.

Scope (HEIM-38): every ``src/api/**/*.py`` file is parsed and walked
independently. Per-file ``import sqlite3`` resolution; violations
aggregated across files in the real-tree assertion.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_API_DIR = REPO_ROOT / "src" / "api"

_WRITER_NAME = "write_console_audit_row"

# Wrapper-helper allowlist. Each entry is a function whose body
# contains a writer call; the lint redirects from the inner call to
# the helper's own callsites and requires THOSE to be wrapped instead.
#
# - ``_write_command_dispatch_audit`` (src/api/console.py): thin
#   audit-only helper invoked via ``asyncio.to_thread`` from inside
#   a failsafe try.body in the WS dispatch handler.
# - ``_write_deny_audit`` (src/api/auth/permissions.py): thin
#   audit-only helper invoked via ``asyncio.to_thread`` from inside
#   the ``require_permission`` decorator's failsafe try.body. Helper's
#   own docstring delegates exception handling to the caller.
# - ``_login_with_conn`` (src/api/routers/auth.py): NOT a thin audit
#   helper — it is the entire login workflow. Allowlisted because the
#   protective ``try/except sqlite3.OperationalError`` lives in its
#   only caller, ``login()`` (src/api/routers/auth.py:240-255), and
#   that placement is intentional: the §3.1.a invariant
#   (auth.py:293-300) requires audit-write failures to surface as 503
#   so the rate-limit counter does NOT advance on a DB outage.
#   Wrapping inside ``_login_with_conn`` with the canonical "log WARN
#   and continue" pattern would silently swallow the DB error and
#   return 200, masquerading a transient outage as an auth fail.
_WRAPPER_HELPERS = frozenset(
    {
        "_write_command_dispatch_audit",
        "_write_deny_audit",
        "_login_with_conn",
    }
)
_ALLOWED_EXC = frozenset(
    {
        "Error",
        "DatabaseError",
        "OperationalError",
        "IntegrityError",
        "DataError",
        "NotSupportedError",
    }
)


# ---------------------------------------------------------------------------
# Import-alias resolution
# ---------------------------------------------------------------------------


def _collect_sqlite_imports(
    tree: ast.AST,
) -> tuple[frozenset[str], dict[str, str]]:
    """Scan top-level ``Import`` / ``ImportFrom`` for sqlite3 bindings.

    Returns ``(module_aliases, name_aliases)``:

    * ``module_aliases`` — set of local names that bind to the sqlite3
      module (always includes ``"sqlite3"`` itself plus any
      ``import sqlite3 as <X>`` rename).
    * ``name_aliases`` — map of local name → original sqlite3 exception
      name. ``from sqlite3 import OperationalError`` adds
      ``{"OperationalError": "OperationalError"}``;
      ``from sqlite3 import OperationalError as OE`` adds
      ``{"OE": "OperationalError"}``.

    Module-level only — local imports inside a function are NOT
    tracked, since this is a static lint that doesn't perform scope
    analysis. The codebase convention (top-level ``import sqlite3``
    in every file that uses it) makes this sufficient.

    ``"sqlite3"`` is NOT pre-seeded into ``module_aliases`` — a file
    that uses ``except sqlite3.X`` without an ``import sqlite3`` is
    unsound (the ``sqlite3`` name is unbound at runtime). The lint
    refuses to certify such a pattern.
    """
    module_aliases: set[str] = set()
    name_aliases: dict[str, str] = {}

    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    name_aliases[local_name] = alias.name

    return frozenset(module_aliases), name_aliases


# ---------------------------------------------------------------------------
# Exception-handler matchers
# ---------------------------------------------------------------------------


def _handler_type_matches(
    node: ast.expr,
    module_aliases: frozenset[str],
    name_aliases: dict[str, str],
) -> bool:
    """True iff *node* references a sqlite3 exception we accept.

    Accepts ``<sqlite3-or-alias>.<X>`` (Attribute) and bare ``<name>``
    where ``<name>`` was imported from sqlite3 at the top level. Names
    not traceable to a sqlite3 import are rejected — closes the
    namespace-collision false-negative risk.
    """
    if isinstance(node, ast.Attribute):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id in module_aliases
            and node.attr in _ALLOWED_EXC
        )
    if isinstance(node, ast.Name):
        original = name_aliases.get(node.id)
        return original is not None and original in _ALLOWED_EXC
    return False


def _is_failsafe_handler(
    handler: ast.ExceptHandler,
    module_aliases: frozenset[str],
    name_aliases: dict[str, str],
) -> bool:
    """True iff *handler* catches sqlite3 exceptions ONLY.

    Rejects:

    * Bare ``except:`` (would mask ``KeyboardInterrupt`` / ``SystemExit``).
    * ``except Exception:`` (would mask programming bugs the canonical
      pattern at ``console.py:345`` explicitly preserves).
    * Mixed tuples like ``except (sqlite3.Error, Exception):`` — the
      broad sibling defeats the invariant. Every tuple element must be
      a sqlite3-allowed type.
    """
    exc_type = handler.type
    if exc_type is None:
        return False
    if isinstance(exc_type, ast.Tuple):
        if not exc_type.elts:
            return False
        return all(
            _handler_type_matches(elt, module_aliases, name_aliases)
            for elt in exc_type.elts
        )
    return _handler_type_matches(exc_type, module_aliases, name_aliases)


# ---------------------------------------------------------------------------
# AST traversal helpers
# ---------------------------------------------------------------------------


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """One-pass id-keyed parent map. AST nodes are not hashable across
    all Python versions; key on ``id(child)`` to avoid relying on
    equality semantics.
    """
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _is_descendant_of_body(
    call: ast.Call,
    try_node: ast.Try,
    parents: dict[int, ast.AST],
) -> bool:
    """True iff *call* is a descendant of any statement in
    ``try_node.body``. Calls in ``handlers`` / ``orelse`` /
    ``finalbody`` of the same Try do NOT count.
    """
    body_ids = {id(stmt) for stmt in try_node.body}
    node: ast.AST | None = call
    while node is not None:
        if id(node) in body_ids:
            return True
        node = parents.get(id(node))
    return False


def _enclosing_failsafe_try(
    call: ast.Call,
    parents: dict[int, ast.AST],
    module_aliases: frozenset[str],
    name_aliases: dict[str, str],
) -> bool:
    """True iff *call* sits in some enclosing ``Try.body`` whose
    handlers include a sqlite3-only ``ExceptHandler``.

    The walk stops at the first ``FunctionDef`` / ``AsyncFunctionDef``
    / ``Lambda`` boundary — beyond that, the call is in deferred code
    that the outer Try does not protect synchronously.
    """
    node: ast.AST | None = parents.get(id(call))
    while node is not None:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            return False
        if isinstance(node, ast.Try) and _is_descendant_of_body(
            call, node, parents
        ):
            # All handlers must pass — a single broad sibling
            # (``except Exception:`` next to ``except sqlite3.X:``)
            # would still mask programming bugs, so a "majority safe"
            # rule is unsafe.
            if node.handlers and all(
                _is_failsafe_handler(h, module_aliases, name_aliases)
                for h in node.handlers
            ):
                return True
        node = parents.get(id(node))
    return False


def _enclosing_function(
    call: ast.Call, parents: dict[int, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Nearest enclosing ``FunctionDef`` / ``AsyncFunctionDef``."""
    node: ast.AST | None = parents.get(id(call))
    while node is not None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
        node = parents.get(id(node))
    return None


# ---------------------------------------------------------------------------
# Writer / wrapper callsite collectors
# ---------------------------------------------------------------------------


def _writer_calls(tree: ast.AST) -> list[ast.Call]:
    """Every ``Call`` whose function resolves to ``write_console_audit_row``.

    Matches:

    * Bare ``write_console_audit_row(...)``.
    * Attribute form ``<anything>.write_console_audit_row(...)`` —
      future-proofs against a refactor to module-aliased imports.
    """
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == _WRITER_NAME:
            out.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == _WRITER_NAME:
            out.append(node)
    return out


def _collect_wrapper_aliases(tree: ast.AST) -> dict[str, str]:
    """Local name → canonical wrapper-helper name.

    Tracks ``from <module> import <wrapper> [as <local>]`` patterns
    where ``<wrapper>`` is in ``_WRAPPER_HELPERS``. Closes the
    cross-module aliasing blind spot Codex P2 flagged on 2026-05-06:
    a callsite ``await asyncio.to_thread(deny_audit, ...)`` — where
    ``deny_audit`` is the import alias for ``_write_deny_audit`` —
    would otherwise pass the cross-file wrapper-callsite check
    silently. Module-level ``ImportFrom`` only; local imports inside a
    function are not tracked, matching the sqlite3-import scope used
    elsewhere in this lint.
    """
    aliases: dict[str, str] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _WRAPPER_HELPERS:
                    local_name = alias.asname or alias.name
                    aliases[local_name] = alias.name
    return aliases


def _wrapper_callsites(
    tree: ast.AST,
    wrapper_name: str,
    aliases: dict[str, str] | None = None,
) -> list[ast.Call]:
    """Every callsite of *wrapper_name*. Covers:

    * Direct call ``wrapper_name(...)``.
    * Aliased call ``<local>(...)`` where ``<local>`` was bound via
      ``from X import wrapper_name as <local>``.
    * Attribute call ``<anything>.wrapper_name(...)`` — mirrors the
      defensive matching used by ``_writer_calls``.
    * Indirect via ``asyncio.to_thread(wrapper_name, ...)`` /
      ``asyncio.to_thread(<local>, ...)`` /
      ``asyncio.to_thread(<module>.wrapper_name, ...)`` — wrapper
      passed as positional arg.
    * Indirect via ``runner(fn=wrapper_name)`` (keyword form), with
      the same alias / attribute coverage.

    The wrapping ``Call`` (the to_thread / runner one, not the wrapper
    itself) is the unit we treat as protected, since that's where the
    caller can attach a try/except.
    """
    aliases = aliases or {}
    matching_local_names: set[str] = {wrapper_name} | {
        local
        for local, canonical in aliases.items()
        if canonical == wrapper_name
    }

    def _matches(expr: ast.expr) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in matching_local_names
        if isinstance(expr, ast.Attribute):
            return expr.attr == wrapper_name
        return False

    out: list[ast.Call] = []
    seen: set[int] = set()

    def _record(node: ast.Call) -> None:
        if id(node) not in seen:
            out.append(node)
            seen.add(id(node))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _matches(node.func):
            _record(node)
            continue
        for arg in node.args:
            if _matches(arg):
                _record(node)
                break
        for kw in node.keywords:
            if _matches(kw.value):
                _record(node)
                break
    return out


# ---------------------------------------------------------------------------
# Top-level visitor
# ---------------------------------------------------------------------------


def _audit_violations(source: str, filename: str) -> list[int]:
    """Run the invariant check over *source*. Return sorted line
    numbers of every unwrapped audit-write call site. Empty list = the
    invariant holds.
    """
    tree = ast.parse(source, filename=filename)
    parents = _build_parent_map(tree)
    module_aliases, name_aliases = _collect_sqlite_imports(tree)
    wrapper_aliases = _collect_wrapper_aliases(tree)

    violations: set[int] = set()
    for call in _writer_calls(tree):
        func = _enclosing_function(call, parents)
        if func is not None and func.name in _WRAPPER_HELPERS:
            for ws_call in _wrapper_callsites(
                tree, func.name, wrapper_aliases
            ):
                if not _enclosing_failsafe_try(
                    ws_call, parents, module_aliases, name_aliases
                ):
                    violations.add(ws_call.lineno)
            continue
        if not _enclosing_failsafe_try(
            call, parents, module_aliases, name_aliases
        ):
            violations.add(call.lineno)

    # Cross-module wrapper-callsite check. The loop above only fires
    # when a writer is found INSIDE an allowlisted wrapper in this
    # file — so a sibling module that imports e.g. ``_write_deny_audit``
    # and calls it unwrapped would otherwise pass silently. Walk every
    # allowlisted wrapper name through ``_wrapper_callsites`` regardless
    # of where the wrapper is defined; alias resolution + attribute
    # matching close the rename / module-attribute blind spots Codex
    # flagged. Same-file overlap is deduped by the set accumulator.
    for wrapper_name in _WRAPPER_HELPERS:
        for ws_call in _wrapper_callsites(
            tree, wrapper_name, wrapper_aliases
        ):
            if not _enclosing_failsafe_try(
                ws_call, parents, module_aliases, name_aliases
            ):
                violations.add(ws_call.lineno)

    return sorted(violations)


# ---------------------------------------------------------------------------
# Real-tree lint
# ---------------------------------------------------------------------------


def _iter_api_files() -> list[Path]:
    """Every ``*.py`` under ``src/api/``, sorted for deterministic
    failure messages.
    """
    return sorted(p for p in _API_DIR.rglob("*.py") if p.is_file())


def test_api_audit_writes_are_failsafe() -> None:
    """Lock the canonical fail-secure pattern at
    ``src/api/console.py:333-372``. Every ``write_console_audit_row(...)``
    callsite under ``src/api/**/*.py`` (and every callsite of an
    allow-listed wrapper) must sit inside a ``try.body`` whose
    handlers include only ``sqlite3.Error`` / ``DatabaseError`` /
    ``OperationalError`` / ``IntegrityError`` / ``DataError`` /
    ``NotSupportedError``.
    """
    files = _iter_api_files()
    assert files, f"No Python files found under {_API_DIR}"

    violations: dict[str, list[int]] = {}
    for path in files:
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        bad = _audit_violations(source, str(path))
        if bad:
            violations[str(rel)] = bad

    assert not violations, (
        "Unwrapped audit-write call sites under src/api/**:\n"
        + "\n".join(
            f"  {rel}:\n"
            + "\n".join(f"    - line {ln}" for ln in lns)
            for rel, lns in sorted(violations.items())
        )
        + "\n\nWrap each in:\n"
        "    try:\n"
        "        write_console_audit_row(...)\n"
        "    except sqlite3.DatabaseError as exc:\n"
        "        logger.warning(...)\n"
    )


# ---------------------------------------------------------------------------
# Negative self-tests — every one of these locks in that the visitor
# catches a specific failure mode rather than silently passing.
# ---------------------------------------------------------------------------


def _violations_in(source: str) -> list[int]:
    return _audit_violations(textwrap.dedent(source).strip(), "<synthetic>")


def test_lint_detects_unwrapped_call() -> None:
    """One wrapped + one unwrapped call. Expect exactly one violation."""
    violations = _violations_in(
        """
        import sqlite3

        def good():
            try:
                write_console_audit_row(conn, request, action="ok")
            except sqlite3.DatabaseError:
                pass

        def bad():
            write_console_audit_row(conn, request, action="leaks")
        """
    )
    assert len(violations) == 1, violations


def test_lint_rejects_bare_except_and_overbroad_exception() -> None:
    """``except:`` and ``except Exception:`` are NOT failsafe."""
    violations = _violations_in(
        """
        import sqlite3

        def bare_except():
            try:
                write_console_audit_row(conn, request, action="bare")
            except:
                pass

        def overbroad():
            try:
                write_console_audit_row(conn, request, action="broad")
            except Exception:
                pass
        """
    )
    assert len(violations) == 2, violations


def test_lint_rejects_mixed_tuple_handler() -> None:
    """``except (sqlite3.Error, Exception):`` masks programming bugs.
    Every tuple element must be a sqlite3-allowed type.
    """
    violations = _violations_in(
        """
        import sqlite3

        def mixed_tuple():
            try:
                write_console_audit_row(conn, request, action="x")
            except (sqlite3.OperationalError, Exception):
                pass

        def all_sqlite():
            try:
                write_console_audit_row(conn, request, action="y")
            except (sqlite3.OperationalError, sqlite3.IntegrityError):
                pass
        """
    )
    assert len(violations) == 1, violations


def test_lint_rejects_writer_inside_nested_function() -> None:
    """A writer call inside a nested ``def`` declared in a Try.body
    is NOT protected — the inner function may be invoked later,
    outside the outer try's protection.
    """
    violations = _violations_in(
        """
        import sqlite3

        def outer():
            try:
                def inner():
                    write_console_audit_row(conn, request, action="deferred")
                save_to_global(inner)
            except sqlite3.DatabaseError:
                pass
        """
    )
    assert len(violations) == 1, violations


def test_lint_detects_unwrapped_wrapper_keyword_callsite() -> None:
    """Wrapper passed as a keyword arg to an outer call must still
    sit inside a failsafe try (mirrors the
    ``runner(fn=_write_command_dispatch_audit)`` pattern).
    """
    violations = _violations_in(
        """
        import sqlite3

        def _write_command_dispatch_audit(*args, **kwargs):
            write_console_audit_row(conn, request, action="cmd.dispatch")

        def good():
            try:
                runner(fn=_write_command_dispatch_audit)
            except sqlite3.OperationalError:
                pass

        def bad():
            runner(fn=_write_command_dispatch_audit)
        """
    )
    assert len(violations) == 1, violations


def test_lint_rejects_bare_name_not_from_sqlite3() -> None:
    """``except OperationalError:`` where ``OperationalError`` is NOT
    imported from sqlite3 must be rejected — closes the
    namespace-collision risk where another library's exception of
    the same name would silently satisfy the lint.
    """
    violations = _violations_in(
        """
        from some_other_orm import OperationalError

        def looks_safe_but_isnt():
            try:
                write_console_audit_row(conn, request, action="x")
            except OperationalError:
                pass
        """
    )
    assert len(violations) == 1, violations


def test_lint_accepts_bare_name_from_sqlite3() -> None:
    """``from sqlite3 import OperationalError`` permits bare-name
    ``except OperationalError:`` because the binding is provably
    sqlite3-rooted.
    """
    violations = _violations_in(
        """
        from sqlite3 import OperationalError

        def safe():
            try:
                write_console_audit_row(conn, request, action="x")
            except OperationalError:
                pass
        """
    )
    assert violations == [], violations


def test_lint_accepts_sqlite3_module_alias() -> None:
    """``import sqlite3 as sql; except sql.DatabaseError:`` is
    failsafe — the module alias is provably sqlite3.
    """
    violations = _violations_in(
        """
        import sqlite3 as sql

        def aliased():
            try:
                write_console_audit_row(conn, request, action="x")
            except sql.DatabaseError:
                pass
        """
    )
    assert violations == [], violations


def test_lint_rejects_sibling_broad_handler() -> None:
    """A Try with both a sqlite3-typed handler AND a broad sibling
    (``except Exception:``) is rejected — the sibling masks
    programming bugs even though a valid sqlite handler is present.
    All handlers must be sqlite3-allowed.
    """
    violations = _violations_in(
        """
        import sqlite3

        def has_broad_sibling():
            try:
                write_console_audit_row(conn, request, action="x")
            except sqlite3.DatabaseError:
                pass
            except Exception:
                pass
        """
    )
    assert len(violations) == 1, violations


def test_lint_rejects_handler_when_sqlite_not_imported() -> None:
    """``except sqlite3.DatabaseError:`` in a file without
    ``import sqlite3`` is unsound (``sqlite3`` isn't bound at runtime).
    The lint must not certify it.
    """
    violations = _violations_in(
        """
        def looks_safe_but_isnt():
            try:
                write_console_audit_row(conn, request, action="x")
            except sqlite3.DatabaseError:
                pass
        """
    )
    assert len(violations) == 1, violations


def test_lint_detects_attribute_form_writer_call() -> None:
    """Refactor to ``<module>.write_console_audit_row(...)`` must
    still be checked. Function-name uniqueness in the codebase makes
    the false-positive risk on the attribute form negligible.
    """
    violations = _violations_in(
        """
        from src.api.auth import audit

        def bad():
            audit.write_console_audit_row(conn, request, action="aliased")
        """
    )
    assert len(violations) == 1, violations


# ---------------------------------------------------------------------------
# HEIM-38 — Multi-file scan + extended wrapper-helper allowlist
# ---------------------------------------------------------------------------


def test_lint_aggregates_violations_per_file() -> None:
    """Independent per-file parse: one synthetic source carries a
    violation, another is clean. Each is parsed separately so the
    sqlite3 import scope is per-file.
    """
    dirty = textwrap.dedent(
        """
        import sqlite3

        def bad():
            write_console_audit_row(conn, request, action="leaks")
        """
    ).strip()
    clean = textwrap.dedent(
        """
        import sqlite3

        def good():
            try:
                write_console_audit_row(conn, request, action="ok")
            except sqlite3.DatabaseError:
                pass
        """
    ).strip()

    assert _audit_violations(dirty, "<dirty>")
    assert _audit_violations(clean, "<clean>") == []


def test_lint_allowlists_login_with_conn_wrapper() -> None:
    """``_login_with_conn`` is the entire login workflow, not a thin
    audit helper, but its single caller wraps the call in a failsafe
    try/except. Allowlisting is intentional — see ``_WRAPPER_HELPERS``
    docstring for the §3.1.a rationale.
    """
    violations = _violations_in(
        """
        import sqlite3

        async def _login_with_conn(*, request, body, conn, ip, redis_client):
            with conn:
                write_console_audit_row(conn, request, action="auth.login_failed")

        async def login(request, body):
            try:
                return await _login_with_conn(
                    request=request, body=body, conn=None, ip=None, redis_client=None
                )
            except sqlite3.OperationalError:
                return None
        """
    )
    assert violations == [], violations


def test_lint_allowlists_write_deny_audit_wrapper() -> None:
    """``_write_deny_audit`` (permissions.py) mirrors the
    ``_write_command_dispatch_audit`` pattern: thin audit-only helper
    invoked via ``asyncio.to_thread`` from inside a failsafe try.body
    in the ``require_permission`` decorator.
    """
    violations = _violations_in(
        """
        import asyncio
        import sqlite3

        def _write_deny_audit(request, permission, role_hint, operator_id, session_id):
            write_console_audit_row(conn, request, action="auth.permission_denied")

        async def wrapper(request, permission, role_hint, operator_id, session_id):
            try:
                await asyncio.to_thread(
                    _write_deny_audit, request, permission, role_hint, operator_id, session_id,
                )
            except sqlite3.OperationalError:
                pass
        """
    )
    assert violations == [], violations


def test_lint_flags_unwrapped_login_with_conn_callsite() -> None:
    """If a future refactor drops the outer try/except around the
    ``_login_with_conn`` call, the lint must catch it — the
    allowlist redirects from inner-call to caller-call, but the
    caller-call must still be wrapped.
    """
    violations = _violations_in(
        """
        import sqlite3

        async def _login_with_conn(*, request, body, conn, ip, redis_client):
            with conn:
                write_console_audit_row(conn, request, action="auth.login_failed")

        async def login(request, body):
            return await _login_with_conn(
                request=request, body=body, conn=None, ip=None, redis_client=None
            )
        """
    )
    assert len(violations) == 1, violations


def test_lint_flags_cross_module_wrapper_callsite() -> None:
    """A sibling module that imports an allowlisted wrapper and
    calls it unwrapped must still be flagged. Codex P2 (2026-05-06):
    the inner-call check only fires when the writer body is in
    THIS file, so cross-module callers were previously a blind
    spot. The independent wrapper-callsite pass closes that gap.
    """
    violations = _violations_in(
        """
        from src.api.auth.permissions import _write_deny_audit

        async def some_handler(request, permission, role_hint, oid, sid):
            await asyncio.to_thread(
                _write_deny_audit, request, permission, role_hint, oid, sid,
            )
        """
    )
    assert len(violations) == 1, violations


def test_lint_flags_aliased_cross_module_wrapper_callsite() -> None:
    """Codex P2 round 2 (2026-05-06): a renamed import like
    ``from src.api.auth.permissions import _write_deny_audit as
    deny_audit`` must still trip the wrapper-callsite check, even
    though the local name no longer matches the canonical wrapper
    name. Alias resolution in ``_collect_wrapper_aliases`` closes
    this.
    """
    violations = _violations_in(
        """
        from src.api.auth.permissions import _write_deny_audit as deny_audit

        async def some_handler(request, permission, role_hint, oid, sid):
            await asyncio.to_thread(
                deny_audit, request, permission, role_hint, oid, sid,
            )
        """
    )
    assert len(violations) == 1, violations


def test_lint_flags_attribute_form_wrapper_callsite() -> None:
    """Codex P2 round 2 (2026-05-06): a module-attribute form
    ``permissions._write_deny_audit`` must still trip the
    wrapper-callsite check. Mirrors the defensive attribute matching
    already applied to the writer name in ``_writer_calls``.
    """
    violations = _violations_in(
        """
        from src.api.auth import permissions

        async def some_handler(request, permission, role_hint, oid, sid):
            await asyncio.to_thread(
                permissions._write_deny_audit, request, permission, role_hint, oid, sid,
            )
        """
    )
    assert len(violations) == 1, violations


def test_lint_accepts_aliased_cross_module_wrapper_when_wrapped() -> None:
    """Aliased + wrapped should pass. Symmetric to the unwrapped
    variant — the alias-resolution must NOT introduce false
    positives when the callsite IS protected.
    """
    violations = _violations_in(
        """
        import sqlite3
        from src.api.auth.permissions import _write_deny_audit as deny_audit

        async def some_handler(request, permission, role_hint, oid, sid):
            try:
                await asyncio.to_thread(
                    deny_audit, request, permission, role_hint, oid, sid,
                )
            except sqlite3.OperationalError:
                pass
        """
    )
    assert violations == [], violations
