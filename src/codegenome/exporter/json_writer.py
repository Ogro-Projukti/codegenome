"""JSON writer with an atomic, Windows-friendly replace strategy."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from codegenome.exporter.context import ExportContext


class JsonWriter:
    """Write the canonical graph JSON payload."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        payload = ctx.json_payload()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(
            f"{output_path.suffix}.{uuid.uuid4().hex[:8]}.tmp"
        )
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        success = False
        for _ in range(10):
            try:
                temp_path.replace(output_path)
                success = True
                break
            except OSError:
                time.sleep(0.1)

        if not success:
            try:
                shutil.copy2(temp_path, output_path)
            except OSError:
                pass
            try:
                temp_path.unlink()
            except OSError:
                pass

        return output_path
