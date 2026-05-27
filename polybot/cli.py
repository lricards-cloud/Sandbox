"""Command-line interface for polybot."""
from __future__ import annotations

import logging
import sys

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .clients.clob import ClobClient
from .config import Config, Secrets
from .copytrader import CopyTrader
from .dashboard import Dashboard
from .discovery import Discovery
from .monitor import Monitor
from .scoring import passes_filters
from .store import Store

console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="Path to config YAML.")
@click.option("--mode", type=click.Choice(["paper", "live"]), default=None, help="Override trading mode.")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
@click.pass_context
def cli(ctx: click.Context, config_path: str, mode: str | None, verbose: bool) -> None:
    """Polybot — copy-trade profitable Polymarket wallets."""
    load_dotenv()
    _setup_logging(verbose)
    cfg = Config.load(config_path)
    if mode:
        cfg.mode = mode
    ctx.obj = {"cfg": cfg, "store": Store(cfg.database)}


@cli.command()
@click.option("--follow/--no-follow", default=True, help="Mark the top-N eligible wallets as followed.")
@click.pass_context
def discover(ctx: click.Context, follow: bool) -> None:
    """Find profitable wallets, score them, and persist the ranking."""
    cfg: Config = ctx.obj["cfg"]
    store: Store = ctx.obj["store"]
    disc = Discovery(cfg)

    with console.status("[cyan]Scanning Polymarket for profitable wallets…"):
        ranked = disc.rank(progress=lambda a: None)

    eligible = disc.eligible(ranked)
    for s in ranked:
        store.upsert_wallet(s)

    if follow and eligible:
        top_n = int(cfg.copy.get("follow_top_n", 7))
        followed = [s.address for s in eligible[:top_n]]
        store.set_followed_top(0)  # clear
        for addr in followed:
            store.set_followed(addr, True)
        console.print(f"[green]Now following {len(followed)} wallet(s).[/]")

    _print_wallet_table(ranked[:25], cfg)
    console.print(
        f"\nScored [bold]{len(ranked)}[/] wallets, [bold green]{len(eligible)}[/] passed filters."
    )


@cli.command()
@click.option("--limit", default=25, help="How many to show.")
@click.pass_context
def wallets(ctx: click.Context, limit: int) -> None:
    """Show ranked wallets from the local store."""
    store: Store = ctx.obj["store"]
    rows = store.top_wallets(limit=limit)
    if not rows:
        console.print("[yellow]No wallets yet — run 'polybot discover'.[/]")
        return
    _print_stored_table(rows)


@cli.command()
@click.argument("address")
@click.pass_context
def track(ctx: click.Context, address: str) -> None:
    """Manually follow a wallet ADDRESS."""
    ctx.obj["store"].set_followed(address.lower(), True)
    console.print(f"[green]Following[/] {address}")


@cli.command()
@click.argument("address")
@click.pass_context
def untrack(ctx: click.Context, address: str) -> None:
    """Stop following a wallet ADDRESS."""
    ctx.obj["store"].set_followed(address.lower(), False)
    console.print(f"[yellow]Unfollowed[/] {address}")


@cli.command()
@click.confirmation_option(
    prompt="Live mode places REAL orders with REAL funds. Continue?",
    help="Skip the confirmation prompt.",
)
@click.pass_context
def monitor(ctx: click.Context) -> None:
    """Run the headless monitor + copy loop (logs to stderr)."""
    cfg: Config = ctx.obj["cfg"]
    store: Store = ctx.obj["store"]
    _guard_live(cfg)
    copytrader = CopyTrader(cfg, store)
    mon = Monitor(cfg, store, copytrader)
    console.print(f"[cyan]Starting monitor in [bold]{cfg.mode}[/] mode. Ctrl-C to stop.[/]")
    try:
        mon.run()
    except KeyboardInterrupt:
        mon.stop()
        console.print("\n[yellow]Stopped.[/]")


@cli.command()
@click.pass_context
def dashboard(ctx: click.Context) -> None:
    """Run the live monitoring terminal (TUI)."""
    cfg: Config = ctx.obj["cfg"]
    store: Store = ctx.obj["store"]
    _guard_live(cfg)
    copytrader = CopyTrader(cfg, store)
    mon = Monitor(cfg, store, copytrader)
    Dashboard(cfg, store, copytrader, mon).run()


@cli.command()
@click.option("--limit", default=20, help="How many recent orders to show.")
@click.pass_context
def status(ctx: click.Context, limit: int) -> None:
    """Show followed wallets, recent copy orders, and exposure."""
    store: Store = ctx.obj["store"]
    followed = store.followed_wallets()
    console.print(f"[bold]Following:[/] {len(followed)} wallet(s)")

    orders = store.recent_copies(limit=limit)
    if orders:
        t = Table(title="Recent copy orders", border_style="magenta")
        for col in ("time", "mode", "status", "side", "market", "$", "@", "from"):
            t.add_column(col)
        import time as _t
        for o in orders:
            t.add_row(
                _t.strftime("%m-%d %H:%M", _t.localtime(o["ts"])),
                o["mode"], o["status"], o["side"],
                (o["title"] or o["condition_id"])[:30],
                f"{o['usdc']:.0f}", f"{o['price']:.3f}", _short(o["source_wallet"]),
            )
        console.print(t)

    exposure = store.open_exposure()
    net = sum(v for v in exposure.values())
    console.print(f"[bold]Net exposure:[/] ${net:,.2f} across {len(exposure)} market(s)")


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Sanity-check connectivity and (for live) credentials."""
    cfg: Config = ctx.obj["cfg"]
    from .clients.data_api import DataAPI
    from .clients.gamma_api import GammaAPI

    gamma = GammaAPI()
    markets = gamma.active_markets(limit=1)
    console.print(f"Gamma API: {'[green]ok[/]' if markets else '[red]no data[/]'}")

    clob = ClobClient()
    if markets:
        cid = markets[0].get("conditionId")
        console.print(f"Sample active market: {markets[0].get('question', cid)}")

    secrets = Secrets.from_env()
    if cfg.mode == "live":
        console.print(
            f"Trading key: {'[green]present[/]' if secrets.has_trading_key else '[red]MISSING[/]'}"
        )
    else:
        console.print("Mode: [green]paper[/] (no keys required)")


# ----- helpers ---------------------------------------------------------------
def _guard_live(cfg: Config) -> None:
    if cfg.mode == "live":
        secrets = Secrets.from_env()
        if not secrets.has_trading_key:
            console.print("[red]Live mode needs POLYMARKET_PRIVATE_KEY in .env.[/]")
            raise SystemExit(1)


def _short(addr: str) -> str:
    return f"{addr[:6]}…{addr[-4:]}" if addr and len(addr) > 12 else (addr or "?")


def _print_wallet_table(stats_list, cfg: Config) -> None:
    t = Table(title="Top wallets", border_style="blue")
    for col in ("wallet", "score", "win%", "PnL $", "ROI", "vol $", "trades", "idle d", "ok"):
        t.add_column(col)
    for s in stats_list:
        ok = "[green]✓[/]" if passes_filters(s, cfg.scoring) else "[dim]–[/]"
        t.add_row(
            _short(s.address), f"{s.score:.2f}", f"{s.win_rate * 100:.0f}",
            f"{s.total_pnl:,.0f}", f"{s.roi * 100:.0f}%", f"{s.volume:,.0f}",
            str(s.num_trades), f"{s.idle_days:.1f}", ok,
        )
    console.print(t)


def _print_stored_table(rows) -> None:
    t = Table(title="Ranked wallets", border_style="blue")
    for col in ("wallet", "score", "win%", "PnL $", "vol $", "trades", "followed"):
        t.add_column(col)
    for w in rows:
        closed = w["num_closed"] or 0
        winr = (w["num_wins"] / closed * 100) if closed else 0.0
        pnl = (w["realized_pnl"] or 0) + (w["unrealized_pnl"] or 0)
        t.add_row(
            _short(w["address"]), f"{(w['score'] or 0):.2f}", f"{winr:.0f}",
            f"{pnl:,.0f}", f"{(w['volume'] or 0):,.0f}", str(w["num_trades"] or 0),
            "[green]yes[/]" if w["followed"] else "no",
        )
    console.print(t)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
