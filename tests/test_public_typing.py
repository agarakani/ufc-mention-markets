"""Keep callable inputs and outputs documented without importing model modules."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted([*ROOT.glob("ufc_mentions/*.py"), *ROOT.glob("scripts/live/*.py")])


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_public_functions_have_input_and_return_annotations(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.append(node)
        elif isinstance(node, ast.ClassDef):
            functions.extend(child for child in node.body if isinstance(child, ast.FunctionDef))
    missing = []
    for function in functions:
        if function.name.startswith("_") and function.name != "__init__":
            continue
        args = function.args
        for argument in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if argument.arg not in {"self", "cls"} and argument.annotation is None:
                missing.append(f"{function.name}.{argument.arg}")
        if function.returns is None:
            missing.append(f"{function.name} return")
    assert not missing, "Missing annotations: " + ", ".join(missing)
