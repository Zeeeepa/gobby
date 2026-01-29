"""Safe expression evaluation utilities.

Provides AST-based expression evaluation without using eval(),
and lazy boolean evaluation for deferred computation.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

__all__ = ["LazyBool", "SafeExpressionEvaluator"]


class LazyBool:
    """Lazy boolean that defers computation until first access.

    Used to avoid expensive operations (git status, DB queries) when
    evaluating block_tools conditions that don't reference certain values.

    The computation is triggered when the value is used in a boolean context
    (e.g., `if lazy_val:` or `not lazy_val`), which happens during eval().
    """

    __slots__ = ("_thunk", "_computed", "_value")

    def __init__(self, thunk: Callable[[], bool]) -> None:
        self._thunk = thunk
        self._computed = False
        self._value = False

    def __bool__(self) -> bool:
        if not self._computed:
            self._value = self._thunk()
            self._computed = True
        return self._value

    def __repr__(self) -> str:
        if self._computed:
            return f"LazyBool({self._value})"
        return "LazyBool(<not computed>)"


class SafeExpressionEvaluator(ast.NodeVisitor):
    """Safe expression evaluator using AST.

    Evaluates simple Python expressions without using eval().
    Supports boolean operations, comparisons, attribute access, subscripts,
    and a limited set of allowed function calls.
    """

    # Comparison operators mapping
    CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    def __init__(
        self, context: dict[str, Any], allowed_funcs: dict[str, Callable[..., Any]]
    ) -> None:
        self.context = context
        self.allowed_funcs = allowed_funcs

    def evaluate(self, expr: str) -> bool:
        """Evaluate expression and return boolean result."""
        try:
            tree = ast.parse(expr, mode="eval")
            return bool(self.visit(tree.body))
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}") from e

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        """Handle 'and' / 'or' operations."""
        if isinstance(node.op, ast.And):
            return all(self.visit(v) for v in node.values)
        elif isinstance(node.op, ast.Or):
            return any(self.visit(v) for v in node.values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> bool:
        """Handle comparison operations (==, !=, <, >, in, not in, etc.)."""
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.visit(comparator)
            op_func = self.CMP_OPS.get(type(op))
            if op_func is None:
                raise ValueError(f"Unsupported comparison: {type(op).__name__}")
            if not op_func(left, right):
                return False
            left = right
        return True

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """Handle unary operations (not, -, +)."""
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        elif isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_Name(self, node: ast.Name) -> Any:
        """Handle variable names."""
        name = node.id
        # Built-in constants
        if name == "True":
            return True
        if name == "False":
            return False
        if name == "None":
            return None
        # Context variables
        if name in self.context:
            return self.context[name]
        raise ValueError(f"Unknown variable: {name}")

    def visit_Constant(self, node: ast.Constant) -> Any:
        """Handle literal values (strings, numbers, booleans, None)."""
        return node.value

    def visit_Call(self, node: ast.Call) -> Any:
        """Handle function calls (only allowed functions)."""
        # Get function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like tool_input.get('key')
            obj = self.visit(node.func.value)
            method_name = node.func.attr
            if method_name == "get" and isinstance(obj, dict):
                args = [self.visit(arg) for arg in node.args]
                return obj.get(*args)
            raise ValueError(f"Unsupported method call: {method_name}")
        else:
            raise ValueError(f"Unsupported call type: {type(node.func).__name__}")

        # Check if function is allowed
        if func_name not in self.allowed_funcs:
            raise ValueError(f"Function not allowed: {func_name}")

        # Evaluate arguments
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}

        return self.allowed_funcs[func_name](*args, **kwargs)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        """Handle attribute access (e.g., obj.attr)."""
        obj = self.visit(node.value)
        attr = node.attr
        if isinstance(obj, dict):
            # Allow dict-style attribute access for convenience
            if attr in obj:
                return obj[attr]
            raise ValueError(f"Key not found: {attr}")
        if hasattr(obj, attr):
            return getattr(obj, attr)
        raise ValueError(f"Attribute not found: {attr}")

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        """Handle subscript access (e.g., obj['key'] or obj[0])."""
        obj = self.visit(node.value)
        key = self.visit(node.slice)
        try:
            return obj[key]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Subscript access failed: {e}") from e

    def visit_List(self, node: ast.List) -> list[Any]:
        """Handle list literals (e.g., ['a', 'b', 'c'])."""
        return [self.visit(elt) for elt in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        """Handle tuple literals (e.g., ('a', 'b', 'c'))."""
        return tuple(self.visit(elt) for elt in node.elts)

    def generic_visit(self, node: ast.AST) -> Any:
        """Reject any unsupported AST nodes."""
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")
