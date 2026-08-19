"""One-off: add identity=DEMO_IDENTITY to start_demo_grid() CALLS in test files.

Only matches actual call statements — not docstrings or function definitions.
"""
from __future__ import annotations

import re
from pathlib import Path

FILES = [
    "tests/unit/application/test_demo_trading.py",
]

IMPORT_LINE = "from trading_grid.application.services.authorization import Identity, Role"

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
    if IMPORT_LINE not in text:
        lines = text.split("\n")
        trading_imports = [
            i for i, l in enumerate(lines) if l.startswith("from trading_grid")
        ]
        if not trading_imports:
            print(f"SKIP {rel}: no trading_grid imports")
            return
        lines.insert(trading_imports[-1] + 1, IMPORT_LINE)
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

    # 3. Replace only actual call statements: `await service.start_demo_grid(args)`
    #    or `started = await service.start_demo_grid(args)`.
    #    This regex requires the call to be preceded by `await ` and the arg
    #    list to not already contain `identity=`.
    pattern = re.compile(
        r"(await service\.start_demo_grid\()([^)]*?)\)"
    )

    def repl(m: re.Match[str]) -> str:
        args = m.group(2).strip()
        if "identity=" in args:
            return m.group(0)
        if args.endswith(","):
            return f"{m.group(1)}{args} identity=DEMO_IDENTITY)"  # [A-H12]
        return f"{m.group(1)}{args}, identity=DEMO_IDENTITY)"  # [A-H12]

    new_text, count = pattern.subn(repl, text)
    if count == 0 and "start_demo_grid" in text:
        # No `await` pattern found — try bare call sites like `service.start_demo_grid(...)`
        pattern2 = re.compile(
            r"(service\.start_demo_grid\()([^)]*?)\)"
        )

        def repl2(m: re.Match[str]) -> str:
            args = m.group(2).strip()
            if "identity=" in args:
                return m.group(0)
            if args.endswith(","):
                return f"{m.group(1)}{args} identity=DEMO_IDENTITY)"  # [A-H12]
            return f"{m.group(1)}{args}, identity=DEMO_IDENTITY)"  # [A-H12]

        new_text, count = pattern2.subn(repl2, text)

    p.write_text(new_text, encoding="utf-8")
    print(f"{rel}: applied identity to {count} start_demo_grid call(s)")


for f in FILES:
    process(f)