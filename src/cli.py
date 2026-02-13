"""
AgentBox CLI — command-line interface for managing agents.

Usage:
    agentbox init <tenant-slug>          — create tenant from template
    agentbox agent start <tenant-slug>   — start agent (register in DB + start polling)
    agentbox agent stop <tenant-slug>    — stop agent (deactivate)
    agentbox agent status                — show all agents and their status
    agentbox agent sync <tenant-slug>    — sync YAML config to DB
    agentbox test <tenant-slug>          — run golden tests for a tenant
    agentbox secrets set <tenant> <name> <value> — save a secret
    agentbox secrets list <tenant>       — list secrets for a tenant
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def cli(verbose: bool):
    """AgentBox — AI agent platform CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


@cli.command()
@click.argument("tenant_slug")
@click.option("--name", "-n", default=None, help="Display name for the tenant")
def init(tenant_slug: str, name: str | None):
    """Create a new tenant from template."""
    template_dir = Path("tenants/_template")
    target_dir = Path(f"tenants/{tenant_slug}")

    if target_dir.exists():
        click.echo(f"Error: tenants/{tenant_slug} already exists", err=True)
        raise SystemExit(1)

    shutil.copytree(template_dir, target_dir)

    # Update agent.yaml with the slug.
    agent_yaml = target_dir / "agent.yaml"
    content = agent_yaml.read_text(encoding="utf-8")
    content = content.replace('id: "change-me"', f'id: "{tenant_slug}-sales"')
    if name:
        content = content.replace('name: "My Agent"', f'name: "{name}"')
    agent_yaml.write_text(content, encoding="utf-8")

    # Create secrets directory.
    secrets_dir = Path(f"secrets/{tenant_slug}")
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    click.echo(f"✓ Created tenants/{tenant_slug}/")
    click.echo(f"✓ Created secrets/{tenant_slug}/")
    click.echo("\nNext steps:")
    click.echo(f"  1. Edit tenants/{tenant_slug}/agent.yaml")
    click.echo(f"  2. Add knowledge files to tenants/{tenant_slug}/knowledge/")
    click.echo(f"  3. Set secrets: agentbox secrets set {tenant_slug} openai_key sk-...")
    click.echo(f"  4. Start: agentbox agent start {tenant_slug}")


@cli.group()
def agent():
    """Manage agents."""


@agent.command("start")
@click.argument("tenant_slug")
def agent_start(tenant_slug: str):
    """Start an agent (register in DB if needed, activate)."""
    asyncio.run(_agent_start(tenant_slug))


async def _agent_start(tenant_slug: str):
    from src.core.config_loader import load_tenant_config
    from src.core.crud import create_agent, create_tenant, get_agent, get_tenant_by_slug
    from src.db import async_session

    tenant_cfg = load_tenant_config(f"tenants/{tenant_slug}")

    async with async_session() as db:
        tenant = await get_tenant_by_slug(db, tenant_slug)
        if not tenant:
            tenant = await create_tenant(
                db,
                slug=tenant_slug,
                name=tenant_cfg.agent.name,
                owner_email="",
            )
            click.echo(f"✓ Created tenant: {tenant_slug}")

        agent_obj = await get_agent(db, tenant.id, tenant_cfg.agent.id)
        if not agent_obj:
            agent_obj = await create_agent(
                db,
                tenant_id=tenant.id,
                slug=tenant_cfg.agent.id,
                name=tenant_cfg.agent.name,
                config=tenant_cfg.agent.model_dump(),
                dialogue_policy=tenant_cfg.dialogue_policy.model_dump(),
                actions_config={"actions": [a.model_dump() for a in tenant_cfg.actions]},
            )
            click.echo(f"✓ Created agent: {tenant_cfg.agent.id}")
        else:
            agent_obj.config = tenant_cfg.agent.model_dump()
            agent_obj.dialogue_policy = tenant_cfg.dialogue_policy.model_dump()
            agent_obj.actions_config = {"actions": [a.model_dump() for a in tenant_cfg.actions]}
            agent_obj.is_active = True
            click.echo(f"✓ Synced agent: {tenant_cfg.agent.id}")

        await db.commit()

    click.echo(f"\n✓ Agent '{tenant_cfg.agent.id}' is active and ready.")
    click.echo("  Polling will start on next celery beat tick.")


@agent.command("stop")
@click.argument("tenant_slug")
def agent_stop(tenant_slug: str):
    """Stop an agent (deactivate)."""
    asyncio.run(_agent_stop(tenant_slug))


async def _agent_stop(tenant_slug: str):
    from sqlalchemy import select

    from src.db import async_session
    from src.models import Agent, Tenant

    async with async_session() as db:
        result = await db.execute(select(Agent).join(Tenant).where(Tenant.slug == tenant_slug))
        agents = result.scalars().all()

        for a in agents:
            a.is_active = False

        await db.commit()

    click.echo(f"✓ Stopped {len(agents)} agent(s) for {tenant_slug}")


@agent.command("status")
def agent_status():
    """Show all agents and their status."""
    asyncio.run(_agent_status())


async def _agent_status():
    from sqlalchemy import select

    from src.db import async_session
    from src.models import Agent, Tenant

    async with async_session() as db:
        result = await db.execute(
            select(Agent, Tenant).join(Tenant, Agent.tenant_id == Tenant.id).order_by(Tenant.slug)
        )
        rows = result.all()

    if not rows:
        click.echo("No agents registered.")
        return

    click.echo(f"{'Tenant':<25} {'Agent':<25} {'Active':<10}")
    click.echo("-" * 60)
    for agent_obj, tenant in rows:
        status = "✓ active" if agent_obj.is_active else "✗ stopped"
        click.echo(f"{tenant.slug:<25} {agent_obj.slug:<25} {status:<10}")


@agent.command("sync")
@click.argument("tenant_slug")
def agent_sync(tenant_slug: str):
    """Sync YAML config to DB for a tenant."""
    asyncio.run(_agent_start(tenant_slug))
    click.echo("✓ Config synced.")


@cli.group()
def secrets():
    """Manage secrets."""


@secrets.command("set")
@click.argument("tenant_slug")
@click.argument("secret_name")
@click.argument("secret_value")
def secrets_set(tenant_slug: str, secret_name: str, secret_value: str):
    """Save a secret for a tenant."""
    secrets_dir = Path(f"secrets/{tenant_slug}")
    secrets_dir.mkdir(parents=True, exist_ok=True)

    gitignore = secrets_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    secret_file = secrets_dir / secret_name
    secret_file.write_text(secret_value, encoding="utf-8")

    click.echo(f"✓ Saved secret: secrets/{tenant_slug}/{secret_name}")


@secrets.command("list")
@click.argument("tenant_slug")
def secrets_list(tenant_slug: str):
    """List secrets for a tenant."""
    secrets_dir = Path(f"secrets/{tenant_slug}")
    if not secrets_dir.exists():
        click.echo(f"No secrets directory for {tenant_slug}")
        return

    files = [f.name for f in secrets_dir.iterdir() if f.is_file() and f.name != ".gitignore"]
    if not files:
        click.echo(f"No secrets for {tenant_slug}")
        return

    click.echo(f"Secrets for {tenant_slug}:")
    for name in sorted(files):
        click.echo(f"  • {name}")


@cli.command("test")
@click.argument("tenant_slug")
def test(tenant_slug: str):
    """Run golden tests for a tenant."""
    import subprocess

    golden_dir = Path(f"tests/golden/{tenant_slug.replace('-studio', '')}")
    if not golden_dir.exists():
        click.echo(f"No golden tests found at {golden_dir}", err=True)
        raise SystemExit(1)

    result = subprocess.run(
        ["pytest", "tests/test_golden.py", "-v", "--tb=short"],
        capture_output=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    cli()

