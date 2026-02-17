#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.config_loader import load_tenant_config
from src.core.runtime_config import build_runtime_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate tenant config and build versioned runtime payload")
    parser.add_argument("tenant_slug", help="Tenant slug (directory under tenants/)")
    parser.add_argument("--tenants-dir", default="tenants")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    tenant_path = Path(args.tenants_dir) / args.tenant_slug
    cfg = load_tenant_config(tenant_path)
    runtime = build_runtime_config(cfg, tenant_slug=args.tenant_slug)

    text = json.dumps(runtime, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
