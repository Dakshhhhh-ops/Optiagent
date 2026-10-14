"""Write the OpenAPI schema to a file: python -m optiagent_api.openapi <path>."""

import json
import sys
from pathlib import Path

from optiagent_api.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
