"""Agent Runtime — executes user-defined dream workflow agents."""

import ast
import re
import json
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.agent import AgentRun, RunStatus
from services.llm import chat_completion


# Available actions (whitelist)
AVAILABLE_ACTIONS = {
    "query_dreams", "query_entities", "query_health",
    "interpret_dream", "rewrite_dream", "generate_video",
    "create_incubation", "llm_analyze", "notify_user",
    "condition", "loop",
}


async def run_agent(
    agent_id: str, user_id: str, steps: list[dict],
    trigger_event: dict, db: AsyncSession,
) -> dict:
    """Execute an agent's steps sequentially."""
    run = AgentRun(
        agent_id=agent_id,
        user_id=user_id,
        trigger_event=trigger_event,
        status=RunStatus.running,
    )
    db.add(run)
    await db.commit()

    variables: dict = {}
    steps_log = []

    try:
        for i, step in enumerate(steps):
            action = step.get("action", "")
            params = _resolve_templates(step.get("params", {}), variables)
            output_var = step.get("output_var")

            if action not in AVAILABLE_ACTIONS:
                raise ValueError(f"Unknown action: {action}")

            # Execute step
            result = await _execute_step(action, params, user_id, db)

            # Store output
            if output_var:
                variables[output_var] = result

            # Handle conditions
            if action == "condition":
                check = params.get("check", "")
                passed = _evaluate_condition(check, variables)
                if not passed:
                    on_false = step.get("on_false", "stop")
                    if on_false == "stop":
                        steps_log.append({"step": i, "action": action, "status": "skipped_rest", "check": check})
                        break

            steps_log.append({
                "step": i,
                "action": action,
                "status": "ok",
                "output_preview": str(result)[:200] if result else None,
            })

        run.status = RunStatus.completed
    except Exception as e:
        run.status = RunStatus.failed
        run.error = str(e)[:500]
        steps_log.append({"step": len(steps_log), "action": "error", "error": str(e)[:200]})

    run.steps_log = steps_log
    run.completed_at = datetime.utcnow()
    await db.commit()

    return {
        "run_id": run.id,
        "status": run.status.value,
        "steps_completed": len(steps_log),
        "error": run.error,
    }


async def _execute_step(action: str, params: dict, user_id: str, db: AsyncSession) -> dict:
    """Execute a single agent step."""
    if action == "query_dreams":
        limit = params.get("limit", 10)
        sort = params.get("sort", "created_at")
        result = await db.execute(
            select(DreamRecord)
            .where(DreamRecord.user_id == user_id)
            .order_by(DreamRecord.created_at.desc())
            .limit(limit)
        )
        dreams = result.scalars().all()
        return {
            "count": len(dreams),
            "dreams": [
                {"id": d.id, "title": d.title, "emotion_valence": d.emotion_valence, "status": d.status.value}
                for d in dreams
            ],
        }

    elif action == "query_entities":
        from models.entities import DreamEntity
        entity_type = params.get("entity_type")
        min_count = params.get("min_count", 2)
        from sqlalchemy import func
        result = await db.execute(
            select(DreamEntity.canonical_name, func.count(DreamEntity.id))
            .where(DreamEntity.user_id == user_id)
            .group_by(DreamEntity.canonical_name)
            .having(func.count(DreamEntity.id) >= min_count)
        )
        return {"entities": [{"name": n, "count": c} for n, c in result.all()]}

    elif action == "query_health":
        from services.health_index import compute_health_index
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=params.get("days", 30))
        return await compute_health_index(user_id, start, end, db)

    elif action == "interpret_dream":
        dream_id = params.get("dream_id")
        if not dream_id:
            return {"error": "No dream_id provided"}
        dream = await db.get(DreamRecord, dream_id)
        if not dream or not dream.dream_script:
            return {"error": "Dream not found or not ready"}
        from services.interpreter import DreamInterpreter
        interp = DreamInterpreter()
        result = await interp.interpret(dream.dream_script, dream.chat_history or [])
        dream.interpretation = result
        await db.commit()
        return result

    elif action == "rewrite_dream":
        dream_id = params.get("dream_id")
        if not dream_id:
            return {"error": "No dream_id provided"}
        dream = await db.get(DreamRecord, dream_id)
        if not dream or not dream.dream_script:
            return {"error": "Dream not found"}
        script_text = json.dumps(dream.dream_script, ensure_ascii=False)
        raw = await chat_completion(
            messages=[{"role": "user", "content": f"Rewrite this nightmare with a healing ending:\n{script_text}\nOutput JSON."}],
            system="Dream therapy assistant. Rewrite nightmares into empowering narratives.",
            max_tokens=3000,
        )
        from services.interpreter import _repair_json
        return {"rewritten_script": _repair_json(raw)}

    elif action == "llm_analyze":
        prompt = params.get("prompt", "")
        raw = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system="You are a dream analysis assistant.",
            max_tokens=params.get("max_tokens", 1000),
        )
        return {"analysis": raw}

    elif action == "notify_user":
        # In production: push notification, email, etc.
        return {"notified": True, "message": params.get("message", "")}

    elif action == "condition":
        return {}  # Handled in the main loop

    return {"status": "unknown_action"}


def _resolve_templates(params: dict, variables: dict) -> dict:
    """Replace {{var.field}} templates with actual values."""
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and "{{" in value:
            for var_name, var_value in variables.items():
                pattern = f"{{{{{var_name}"
                if pattern in value:
                    if isinstance(var_value, dict):
                        # Handle {{var.field}} access
                        for field in var_value:
                            value = value.replace(f"{{{{{var_name}.{field}}}}}", str(var_value[field]))
                    value = value.replace(f"{{{{{var_name}}}}}", str(var_value))
            resolved[key] = value
        else:
            resolved[key] = value
    return resolved


_ALLOWED_NODES = (
    # Expression boilerplate
    "Expression", "Module", "Expr", "Load",
    # Literals
    "Constant", "List", "Tuple", "Set", "Dict",
    # Operators (boolean + comparison + simple arithmetic only)
    "BoolOp", "And", "Or", "Not", "UnaryOp",
    "Compare", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "In", "NotIn", "Is", "IsNot",
    "BinOp", "Add", "Sub", "Mult", "Div", "Mod", "FloorDiv",
    "Name",  # Only resolved against `variables` whitelist below
)


class _SafeEvaluator(ast.NodeVisitor):
    """Whitelist-based AST evaluator.

    Only constants, named variables (from a passed-in dict), and a small set
    of boolean / comparison / arithmetic operators are permitted. Attribute
    access, subscripts, calls, lambdas, comprehensions, imports, etc. all
    raise — preventing the RCE chain that ``eval(..., {'__builtins__': {}})``
    is known to allow.
    """

    def __init__(self, variables: dict):
        self.variables = variables

    def generic_visit(self, node):  # noqa: D401
        if type(node).__name__ not in _ALLOWED_NODES:
            raise ValueError(f"Disallowed AST node: {type(node).__name__}")
        return super().generic_visit(node)

    def evaluate(self, expression: str):
        tree = ast.parse(expression, mode="eval")
        # Walk the whole tree first to reject anything not on the allowlist
        self.visit(tree)
        return self._eval(tree.body)

    def _eval(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                raise ValueError(f"Unknown variable: {node.id}")
            return self.variables[node.id]
        if isinstance(node, ast.UnaryOp):
            v = self._eval(node.operand)
            if isinstance(node.op, ast.Not): return not v
            if isinstance(node.op, ast.USub): return -v
            if isinstance(node.op, ast.UAdd): return +v
            raise ValueError(f"Disallowed unary op: {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            vals = [self._eval(v) for v in node.values]
            if isinstance(node.op, ast.And): return all(vals)
            if isinstance(node.op, ast.Or):  return any(vals)
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval(comp)
                op_name = type(op).__name__
                # Lazy dispatch — eager dict-build was raising on In/NotIn
                # for non-iterables before the chosen branch ran.
                if op_name == "Eq":      ok = left == right
                elif op_name == "NotEq": ok = left != right
                elif op_name == "Lt":    ok = left < right
                elif op_name == "LtE":   ok = left <= right
                elif op_name == "Gt":    ok = left > right
                elif op_name == "GtE":   ok = left >= right
                elif op_name == "In":    ok = left in right
                elif op_name == "NotIn": ok = left not in right
                elif op_name == "Is":    ok = left is right
                elif op_name == "IsNot": ok = left is not right
                else: raise ValueError(f"Disallowed compare op: {op_name}")
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp):
            l = self._eval(node.left); r = self._eval(node.right)
            op_name = type(node.op).__name__
            return {
                "Add": l + r, "Sub": l - r, "Mult": l * r,
                "Div": l / r, "Mod": l % r, "FloorDiv": l // r,
            }[op_name]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return type(node).__name__ == "Set" and {self._eval(e) for e in node.elts} \
                or type(node).__name__ == "Tuple" and tuple(self._eval(e) for e in node.elts) \
                or [self._eval(e) for e in node.elts]
        if isinstance(node, ast.Dict):
            return {self._eval(k): self._eval(v) for k, v in zip(node.keys, node.values)}
        raise ValueError(f"Cannot evaluate: {type(node).__name__}")


_DOTTED_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def _flatten_variables_and_expression(check: str, variables: dict) -> tuple[str, dict]:
    """Convert ``user.id`` style references to flat names BEFORE parsing.

    AST-level attribute traversal is the exact attack surface that made the
    original eval() vulnerable. By rewriting the dotted reference to a flat
    identifier (``user__id``) and exposing it as a flat key in the env, we
    keep the convenient agent-DSL syntax without ever permitting Attribute
    nodes in the AST.
    """
    flat_env: dict = {}
    # First, flatten dict variables: {user: {id: 'x'}} → {user__id: 'x'}
    for k, v in (variables or {}).items():
        if isinstance(v, dict):
            for fk, fv in v.items():
                flat_env[f"{k}__{fk}"] = fv
        flat_env[k] = v
    # Then rewrite ``a.b`` in the expression string to ``a__b`` so the
    # parser sees a Name node, not an Attribute node.
    rewritten = _DOTTED_NAME_RE.sub(r"\1__\2", check)
    return rewritten, flat_env


def _evaluate_condition(check: str, variables: dict) -> bool:
    """Safely evaluate a simple boolean expression.

    Replaces an earlier ``eval(check, {'__builtins__': {}}, {})`` which was
    vulnerable to attribute-chain RCE. Now uses a whitelist AST walker
    plus dotted-name pre-flattening so only Name lookups survive into the
    AST.
    """
    if not check or not check.strip():
        return True
    try:
        rewritten, env = _flatten_variables_and_expression(check, variables or {})
        return bool(_SafeEvaluator(env).evaluate(rewritten))
    except Exception:
        # Conservative: malformed/disallowed expressions evaluate to False
        # (matches the prior behavior, doesn't surface internal errors).
        return False
