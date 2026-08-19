"""One-off: add identity=DEMO_IDENTITY to start_demo_grid() calls in tests."""
from __future__ import annotations

import re
from pathlib import Path

FILES = [
    "tests/unit/application/test_demo_trading.py",
    "tests/unit/application/test_authorization.py",
]

IDENT_BLOCK = (
    "\n"
    "# [A-H12] Test identity (identity is REQUIRED).\n"
    "DEMO_IDENTITY = Identity(\n"
    '    identity_id="test-user",\n'
    '    identity_type="HUMAN",\n'
    "    role=Role.DEMO_OPERATOR,\n"
    '    allowed_environments=("DEMO",),\n'
    ")\n"
)


def process(rel: str) -> None:
    p = Path(rel)
    if not p.exists():
        print(f"SKIP {rel}: not found")
        return

    text = p.read_text(encoding="utf-8")

    # 1. Ensure authorization import
    if "from trading_grid.application.services.authorization import Identity, Role" not in text:
        lines = text.split("\n")
        trading_imports = [
            i for i, l in enumerate(lines) if l.startswith("from trading_grid")
        ]
        if not trading_imports:
            print(f"SKIP {rel}: no trading_grid imports")
            return
        anchor = trading_imports[-1]
        lines.insert(anchor + 1, "from trading_grid.application.services.authorization import Identity, Role")
        text = "\n".join(lines)

    # 2. Ensure DEMO_IDENTITY constant
    if "DEMO_IDENTITY" not in text:
        lines = text.split("\n")
        imports = [
            i for i, l in enumerate(lines)
            if l.startswith("from ") or l.startswith("import ")
        ]
        if not imports:
            print(f"SKIP {rel}: no imports found")
            return
        lines.insert(imports[-1] + 1, IDENT_BLOCK)
        text = "\n".join(lines)

    # 3. Inject identity=DEMO_IDENTITY into start_demo_grid(...) calls
    # Regex matches `start_demo_grid(` and captures args until the matching close.
    # We use a simple pattern that handles single-line and multi-line calls
    # where args do NOT already contain identity=.
    lines = text.split("\n")
    added = 0
    i = 0
    while i < len(lines):
        if "start_demo_grid(" in lines[i] and "identity=" not in lines[i]:
            depth = 0
            j = i
            while j < len(lines):
                depth += lines[j].count("(") - lines[j].count(")")
                if j > i and depth <= 0:
                    break
                j += 1
            if j < len(lines):
                # Found closing line `j`; insert identity before it
                indent = re.match(r"^(\s*)", lines[j]).group(1)
                stripped = lines[j].strip()
                if stripped == ")":
                    lines[j] = indent + "identity=DEMO_IDENTITY,  # [A-H12] required\n" + indent + ")"
                else:
                    rfind = lines[j].rfind(")")
                    lines[j] = lines[j][:rfind].rstrip() + ", identity=DEMO_IDENTITY  # [A-H12] required)"
                added += 1
                i = j + 1
                continue
        i += 1

    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"{rel}: added identity to {added} start_demo_grid call(s)")


for f in FILES:
    process(f)