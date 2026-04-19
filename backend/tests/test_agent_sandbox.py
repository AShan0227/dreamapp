"""Agent DSL sandbox — RCE-prevention tests.

`_evaluate_condition` is fail-CLOSED by design: on any error (AST parse,
disallowed node, NameError, etc.) it returns False rather than raising.
This test verifies BOTH invariants:
  (1) safe expressions evaluate to their actual boolean value
  (2) dangerous expressions evaluate to False — never True, never RCE

A sandbox escape = full server RCE. If any "rejects_*" test suddenly
returns True, that's a CVE.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agent_runtime import _evaluate_condition, _SafeEvaluator  # noqa: E402

import pytest  # noqa: E402


# ---- Allowed cases — explicit return values ------------------------------

def test_plain_constant_comparisons():
    assert _evaluate_condition("5 > 3", {}) is True
    assert _evaluate_condition("1 == 2", {}) is False


def test_variable_comparisons():
    assert _evaluate_condition("streak > 7", {"streak": 10}) is True
    assert _evaluate_condition("streak > 7", {"streak": 3}) is False


def test_dotted_access_via_flatten():
    assert _evaluate_condition(
        "user.streak > 7 and user.name == 'Sylvan'",
        {"user": {"streak": 10, "name": "Sylvan"}},
    ) is True


def test_in_operator_on_list():
    assert _evaluate_condition(
        "'fear' in tags", {"tags": ["joy", "fear", "awe"]}
    ) is True


def test_boolean_logic():
    assert _evaluate_condition(
        "(a or b) and not c",
        {"a": True, "b": False, "c": False},
    ) is True


# ---- The attack surface — every dangerous expression MUST return False ---

DANGEROUS_EXPRS = [
    "open('/etc/passwd')",             # function call
    "__builtins__",                    # builtin name access
    "os.system('rm -rf /')",           # Attribute on unknown name
    "x[0]",                            # Subscript not whitelisted
    "(lambda x: x)(5) == 5",           # Lambda not whitelisted
    "[i for i in range(5)]",           # Comprehension not whitelisted
    "os",                              # Unknown name
    "user.__class__",                  # Attribute access
    "().__class__.__bases__[0].__subclasses__()",  # classic escape chain
    "getattr(object, 'x')",            # builtin function
    "exec('import os')",               # exec as a name → call
    "compile('1', 'f', 'eval')",       # compile builtin
    "1 if open else 0",                # IfExp + name access
]


@pytest.mark.parametrize("expr", DANGEROUS_EXPRS)
def test_dangerous_expression_returns_false(expr):
    """Fail-CLOSED: every disallowed construct must evaluate to False,
    NEVER True and NEVER let a side-effect leak (file open, os call)."""
    result = _evaluate_condition(expr, {"user": {}})
    assert result is False, f"SANDBOX ESCAPE: {expr!r} returned {result!r}"


@pytest.mark.parametrize("expr", ["yield 5", "(x := 5)"])
def test_syntactic_garbage_returns_false(expr):
    """Walrus + yield are SyntaxErrors at parse time in eval mode → False."""
    assert _evaluate_condition(expr, {}) is False


# ---- The inner evaluator DOES raise — used to build the outer fail-closed ----

def test_safe_evaluator_raises_on_call():
    """Inner _SafeEvaluator is STRICT (raises). Outer _evaluate_condition
    wraps it in try/except. This test pins the inner contract — if it
    stops raising, the outer fail-closed semantics break."""
    with pytest.raises(ValueError):
        _SafeEvaluator({}).evaluate("open('x')")


def test_safe_evaluator_raises_on_unknown_name():
    with pytest.raises(ValueError):
        _SafeEvaluator({}).evaluate("os")


def test_safe_evaluator_raises_on_lambda():
    with pytest.raises(ValueError):
        _SafeEvaluator({}).evaluate("(lambda: 1)()")
