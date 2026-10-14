"""List functions that are not implemented yet.

    python -m btb.status      (make status)

Scans src/btb for functions whose body is still just `raise NotImplementedError`,
grouped by module, plus TODO sections left in the app.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "btb"
SKIP = {"standins.py", "status.py"}


def _is_stub(fn: ast.FunctionDef) -> bool:
    body = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))]
    return (len(body) == 1 and isinstance(body[0], ast.Raise) and body[0].exc is not None
            and "NotImplementedError" in ast.unparse(body[0].exc))


def stubs() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        if path.name in SKIP:
            continue
        tree = ast.parse(path.read_text())
        names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and _is_stub(n)]
        if names:
            out[str(path.relative_to(SRC))] = names
    return out


def main():
    left = stubs()
    todos = (ROOT / "app" / "streamlit_app.py").read_text().count("# TODO")
    if not left and not todos:
        print("Everything is implemented. Run `make demo`.")
        return
    for module, names in left.items():
        print(f"{module}")
        for n in names:
            print(f"    {n}")
    if todos:
        print(f"app/streamlit_app.py\n    {todos} TODO sections")
    print(f"\n{sum(len(v) for v in left.values())} functions not implemented yet.")


if __name__ == "__main__":
    main()
