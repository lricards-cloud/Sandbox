"""Command-line interface for docfiler."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from .config import Config
from .drive_client import DriveClient
from .obsidian_filer import ObsidianFiler
from .poller import Poller, ProcessedState

console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def _build_poller(cfg: Config) -> Poller:
    drive_cfg = cfg.drive
    if not drive_cfg.get("inbox_folder_id"):
        console.print("[red]drive.inbox_folder_id is not set in your config.[/]")
        raise SystemExit(1)
    obs_cfg = cfg.obsidian
    if not obs_cfg.get("vault_path"):
        console.print("[red]obsidian.vault_path is not set in your config.[/]")
        raise SystemExit(1)

    drive = DriveClient(drive_cfg["credentials_file"])
    filer = ObsidianFiler(
        vault_path=obs_cfg["vault_path"],
        filing_root=obs_cfg.get("filing_root", "Filing"),
        attachments_dirname=obs_cfg.get("attachments_dirname", "_attachments"),
        categories=cfg.categories,
    )
    state = ProcessedState(cfg.poll.get("state_file", "docfiler_state.json"))
    return Poller(
        drive=drive,
        filer=filer,
        inbox_folder_id=drive_cfg["inbox_folder_id"],
        done_folder_id=drive_cfg.get("done_folder_id") or None,
        state=state,
    )


@click.group()
@click.option("--config", "config_path", default="docfiler.yaml", help="Path to config YAML.")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
@click.pass_context
def cli(ctx: click.Context, config_path: str, verbose: bool) -> None:
    """docfiler — files classified documents from a Drive inbox into Obsidian."""
    _setup_logging(verbose)
    ctx.obj = {"cfg": Config.load(config_path)}


@cli.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Process everything currently waiting in the inbox, once, then exit."""
    poller = _build_poller(ctx.obj["cfg"])
    n = poller.run_once()
    console.print(f"[green]Filed {n} document(s).[/]" if n else "[dim]Nothing new to file.[/]")


@cli.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Poll the inbox on a loop (Ctrl-C to stop)."""
    cfg: Config = ctx.obj["cfg"]
    poller = _build_poller(cfg)
    interval = int(cfg.poll.get("interval_sec", 120))
    console.print(f"[cyan]Watching Drive inbox every {interval}s. Ctrl-C to stop.[/]")
    try:
        poller.run_forever(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/]")


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Sanity-check config and Drive connectivity."""
    cfg: Config = ctx.obj["cfg"]

    vault = Path(cfg.obsidian.get("vault_path", ""))
    console.print(f"Vault path: {'[green]ok[/]' if vault.is_dir() else '[red]MISSING[/]'} ({vault})")

    try:
        poller = _build_poller(cfg)
        files = poller.drive.list_folder(poller.inbox_folder_id)
        console.print(f"Drive inbox: [green]ok[/] ({len(files)} item(s) waiting)")
    except Exception as exc:  # noqa: BLE001
        console.print(f"Drive inbox: [red]FAILED[/] ({exc})")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
