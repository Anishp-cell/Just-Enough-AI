"""Differential AST Scope Lock.

Mayank (Security Lead): Prevent open-weight models from causing collateral damage
by mutating functions outside their assigned task scope.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Union
import ast
import copy


@dataclass
class ScopeLockResult:
    applied_code: str
    unauthorized_mutations_reverted: List[str] = field(default_factory=list)
    in_scope_symbols: List[str] = field(default_factory=list)


ASTSymbolNode = Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]


def _is_symbol_node(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def apply_ast_scope_lock(
    original_code: str,
    proposed_code: str,
    target_symbol_names: List[str],
) -> ScopeLockResult:
    """Compare ASTs, lock immutable symbols outside target_symbol_names, and revert unauthorized edits."""
    in_scope = list(target_symbol_names)
    target_set = set(target_symbol_names)
    reverted_mutations: List[str] = []

    # 1. Parse both original and proposed code
    try:
        orig_tree = ast.parse(original_code)
    except SyntaxError as e:
        # Original code cannot be parsed; fallback to proposed or error
        raise ValueError(f"Original code contains syntax error: {e}")

    try:
        prop_tree = ast.parse(proposed_code)
    except SyntaxError as e:
        # Proposed code has syntax error: reject all changes and return original code
        return ScopeLockResult(
            applied_code=original_code,
            unauthorized_mutations_reverted=[f"Rejected invalid proposed syntax: {e}"],
            in_scope_symbols=in_scope,
        )

    # 2. Index top-level symbols (functions, async functions, classes) in original AST
    orig_symbols: Dict[str, ASTSymbolNode] = {}
    for node in orig_tree.body:
        if _is_symbol_node(node):
            orig_symbols[node.name] = node

    # 3. Index top-level symbols in proposed AST
    prop_symbols: Dict[str, ASTSymbolNode] = {}
    prop_symbol_indices: Dict[str, int] = {}
    for idx, node in enumerate(prop_tree.body):
        if _is_symbol_node(node):
            prop_symbols[node.name] = node
            prop_symbol_indices[node.name] = idx

    # 4. Identify immutable symbols (symbols in original_code not in target_symbol_names)
    immutable_symbols = [name for name in orig_symbols if name not in target_set]

    # 5. Check and enforce immutability
    for name in immutable_symbols:
        orig_node = orig_symbols[name]
        orig_unparsed = ast.unparse(orig_node).strip()

        if name not in prop_symbols:
            # Case A: Immutable symbol was deleted or renamed in proposed code -> Restore it!
            prop_tree.body.append(copy.deepcopy(orig_node))
            reverted_mutations.append(
                f"Restored deleted immutable symbol '{name}' back to original definition."
            )
        else:
            # Case B: Immutable symbol was modified in proposed code
            prop_node = prop_symbols[name]
            prop_unparsed = ast.unparse(prop_node).strip()

            if orig_unparsed != prop_unparsed:
                # Discard proposed node and re-insert original node
                idx = prop_symbol_indices[name]
                prop_tree.body[idx] = copy.deepcopy(orig_node)
                reverted_mutations.append(
                    f"Reverted unauthorized mutation to out-of-scope symbol '{name}'."
                )

    # 6. Unparse sanitized AST
    applied_code = ast.unparse(prop_tree)

    return ScopeLockResult(
        applied_code=applied_code,
        unauthorized_mutations_reverted=reverted_mutations,
        in_scope_symbols=in_scope,
    )
