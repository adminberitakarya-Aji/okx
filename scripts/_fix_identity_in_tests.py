"""One-off: add identity=DEMO_IDENTITY to execute_order() calls in tests."""
from __future__ import annotations

import re
from pathlib import Path

FILES = [
    "tests/unit/application/test_execution_engine.py",
    "tests/unit/application/test_risk_validation.py",
    "tests/e2e/test_end_to_end_flow.py",
]

IDENT = (
    "\n"
    "# [A-H12] Test identity for execute_order (identity is REQUIRED).\n"
    "DEMO_IDENTITY = Identity(\n"
    '    identity_id="test-user",\n'
    '    identity_type="HUMAN",\n'
    "    role=Role.DEMO_OPERATOR,\n"
    '    allowed_environments=("DEMO",),\n'
    ")\n"
)


def inject(lines: list[str], idx: int) -> int:
    """Inject identity arg before the call's closing paren. Returns 1 on success."""
    depth = 0
    for i in range(idx, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if "identity=" in lines[i]:
            return 0
        if depth <= 0:
            line = lines[i]
            indent = re.match(r"^(\s*)", line).group(1)
            stripped = line.strip()
            if stripped == ")":
                lines[i] = indent + "identity=DEMO_IDENTITY,  # [A-H12] required\n" + indent + ")"
                return 1
            rfind = line.rfind(")")
            head = line[:rfind].rstrip()
            if head.endswith(",") or head.endswith("("):
                lines.insert(i, indent + "identity=DEMO_IDENTITY,  # [A-H12] required")
                return 1
            lines[i] = head + ", identity=DEMO_IDENTITY  # [A-H12] required)"
            return 1
    return 0


for rel in FILES:
    p = Path(rel)
    if not p.exists():
        print(f"SKIP {rel}")
        continue
    text = p.read_text(encoding="utf-8")

    # 1. Ensure authorization import
    if "from trading_grid.application.services.authorization import" not in text:
        lines = text.split("\n")
        anchor = max(i for i, l in enumerate(lines) if l.startswith("from trading_grid"))
        lines.insert(anchor + 1, "from trading_grid.application.services.authorization import Identity, Role")
        text = "\n".join(lines)

    # 2. Ensure DEMO_IDENTITY constant
    if "DEMO_IDENTITY" not in text:
        lines = text.split("\n")
        last_import = max(
            i for i, l in enumerate(lines)
            if l.startswith("from ") or l.startswith("import ")
        )
        lines.insert(last_import + 1, IDENT)
        text = "\n".join(lines)

    # 3. Inject identity into all execute_order calls
    lines = text.split("\n")
    added = 0
    i = 0
    while i < len(lines):
        if "execute_order(" in lines[i]:
            added += inject(lines, i)
        i += 1

    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"{rel}: injected {added}")