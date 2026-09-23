"""coderag command line."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from coderag import db
from coderag.config import get_settings
from coderag.embedder import get_embedder
from coderag.context import (
    file_context as run_file_context,
    symbol_context as run_symbol_context,
    what_breaks as run_what_breaks,
    what_tests as run_what_tests,
    who_calls as run_who_calls,
)
from coderag import eval as evaluation
from coderag.indexer import index_repo
from coderag.retriever import search as run_search

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Index a codebase into Neo4j and query it without flooding context.",
)
console = Console()


def _repo_name(root: Path, repo: str | None) -> str:
    return repo or root.resolve().name


def _resolve_repo(repo: str | None) -> str:
    """Which repo a query command should answer about.

    Explicit --repo wins. Otherwise prefer the directory you are standing
    in, then fall back to the only indexed repo if there is exactly one.
    The previous default was the name of a bundled sample, so anyone who
    indexed their own project and ran a query was told, confusingly, that
    nothing matched in 'bookstore-python'.
    """
    if repo:
        return repo
    db.wait_until_ready()
    names = [r["name"] for r in db.read("MATCH (r:Repo) RETURN r.name AS name ORDER BY r.name")]
    if not names:
        console.print("[red]nothing indexed yet[/red] -- run: coderag index <path>")
        raise typer.Exit(1)
    here = Path.cwd().resolve().name
    if here in names:
        return here
    if len(names) == 1:
        return names[0]
    console.print(
        "[red]several repos indexed; say which with --repo[/red]: " + ", ".join(names)
    )
    raise typer.Exit(1)


@app.command()
def init(
    reset: Annotated[bool, typer.Option(help="Drop and recreate indexes.")] = False,
) -> None:
    """Create schema and pre-warm the embedding model."""
    embedder = get_embedder()
    with console.status("waiting for Neo4j..."):
        db.wait_until_ready()
    if reset:
        console.print("[yellow]dropping existing indexes[/yellow]")
        db.drop_schema()
    db.ensure_schema(embedder.dim)
    console.print(f"schema ready (vector dim {embedder.dim}, embedder '{embedder.name}')")

    with console.status(f"warming embedding model '{embedder.name}'..."):
        embedder.warm()
    console.print("[green]ready[/green]")


@app.command()
def index(
    path: Annotated[Path, typer.Argument(help="Repository root to index.")],
    repo: Annotated[str | None, typer.Option(help="Name to index under.")] = None,
    only: Annotated[str | None, typer.Option(help="Restrict to a subdirectory.")] = None,
    force: Annotated[bool, typer.Option(help="Reindex everything, ignoring hashes.")] = False,
) -> None:
    """Index a source tree."""
    embedder = get_embedder()
    db.wait_until_ready()
    db.ensure_schema(embedder.dim)
    name = _repo_name(path, repo)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}"), TimeElapsedColumn(),
        console=console,
    ) as progress:
        tasks = {
            "parse": progress.add_task("parsing", total=None),
            "embed": progress.add_task("embedding", total=None),
        }

        def report(phase: str, count: int) -> None:
            if phase in tasks:
                progress.advance(tasks[phase], count)

        stats = index_repo(
            path, repo=name, only=only, force=force,
            embedder=embedder, progress=report,
        )

    table = Table(title=f"indexed '{stats.repo}'", show_header=False, box=None)
    table.add_row("files indexed", str(stats.files_indexed))
    table.add_row("files skipped (unchanged)", str(stats.files_skipped))
    if stats.files_pruned:
        table.add_row("files pruned (deleted)", str(stats.files_pruned))
    table.add_row("symbols", str(stats.symbols))
    table.add_row("chunks", str(stats.chunks))
    table.add_row("edges", str(stats.edges))
    table.add_row("unresolved call ratio", f"{stats.unresolved_ratio:.1%}")
    table.add_row("git history", "yes" if stats.has_history else "no (co-change unavailable)")
    console.print(table)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="What you are looking for.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
    k: Annotated[int, typer.Option(help="Max results.")] = 8,
    scope: Annotated[str | None, typer.Option(help="Restrict to a path prefix.")] = None,
    include_tests: Annotated[bool, typer.Option(help="Do not demote test code.")] = False,
    budget: Annotated[int | None, typer.Option(help="Token ceiling for the response.")] = None,
) -> None:
    """Search the index and print a budgeted context pack."""
    embedder = get_embedder()
    db.wait_until_ready()
    repo = _resolve_repo(repo)
    pack = run_search(
        query, repo=repo, embedder=embedder, k=k, scope=scope,
        include_tests=include_tests, expand=True, budget_tokens=budget,
    )
    console.print(pack.render(), markup=False, highlight=False)
    console.print(f"[dim]~{pack.tokens()} tokens[/dim]")


@app.command()
def stats(
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
) -> None:
    """Show what is in the index."""
    repo = _resolve_repo(repo)
    rows = db.read(
        """
        MATCH (r:Repo {name: $repo})
        RETURN r.embedder AS embedder, r.dim AS dim, r.commit AS commit,
               r.has_history AS has_history, r.indexed_at AS indexed_at,
               """ + db.repo_counts_clause("$repo") + """
        """,
        repo=repo,
    )
    if not rows or rows[0]["files"] == 0:
        console.print(f"[yellow]nothing indexed under '{repo}'[/yellow]")
        raise typer.Exit(1)

    info = rows[0]
    edges = db.read(
        """
        MATCH (:Symbol {repo: $repo})-[r]->(:Symbol {repo: $repo})
        RETURN type(r) AS kind, count(r) AS n ORDER BY n DESC
        """,
        repo=repo,
    )

    table = Table(title=f"index '{repo}'", show_header=False, box=None)
    table.add_row("embedder", f"{info['embedder']} (dim {info['dim']})")
    table.add_row("files", str(info["files"]))
    table.add_row("symbols", str(info["symbols"]))
    table.add_row("chunks", str(info["chunks"]))
    for row in edges:
        table.add_row(f"  {row['kind']}", str(row["n"]))
    table.add_row("git history", "yes" if info["has_history"] else "no")
    table.add_row("indexed at", str(info["indexed_at"]))
    console.print(table)


def _emit(pack) -> None:
    console.print(pack.render(), markup=False, highlight=False)
    console.print(f"[dim]~{pack.tokens()} tokens[/dim]")


@app.command()
def context(
    qname: Annotated[str, typer.Argument(help="Qualified or plain symbol name.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
    budget: Annotated[int | None, typer.Option(help="Token ceiling.")] = None,
) -> None:
    """Everything needed to change one symbol safely."""
    db.wait_until_ready()
    _emit(run_symbol_context(_resolve_repo(repo), qname, budget_tokens=budget))


@app.command(name="what-breaks")
def what_breaks_cmd(
    qname: Annotated[str, typer.Argument(help="Symbol you intend to change.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
    depth: Annotated[int, typer.Option(help="Caller hops to follow.")] = 2,
    budget: Annotated[int | None, typer.Option(help="Token ceiling.")] = None,
) -> None:
    """Blast radius: callers, tests and co-changed files."""
    db.wait_until_ready()
    _emit(run_what_breaks(_resolve_repo(repo), qname, depth=depth, budget_tokens=budget))


@app.command(name="what-tests")
def what_tests_cmd(
    qname: Annotated[str, typer.Argument(help="Symbol to find tests for.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
) -> None:
    """Which tests cover a symbol."""
    db.wait_until_ready()
    _emit(run_what_tests(_resolve_repo(repo), qname))


@app.command()
def why(
    qname: Annotated[str, typer.Argument(help="Symbol to trace callers of.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
    depth: Annotated[int, typer.Option(help="Caller hops to follow.")] = 2,
) -> None:
    """Who calls this, and how far up the chain."""
    db.wait_until_ready()
    _emit(run_who_calls(_resolve_repo(repo), qname, depth=depth))


@app.command()
def outline(
    path: Annotated[str, typer.Argument(help="File path, or a suffix of one.")],
    repo: Annotated[str | None, typer.Option(help="Indexed repo name. Defaults to the current directory's, or the only indexed repo.")] = None,
    budget: Annotated[int | None, typer.Option(help="Token ceiling.")] = None,
) -> None:
    """A file's symbols and line ranges, without its bodies."""
    db.wait_until_ready()
    _emit(run_file_context(_resolve_repo(repo), path, budget_tokens=budget))


# The sample tree holds one implementation per language. Each is indexed as
# its own repo, which is how the tool is actually used: you point it at a
# project, not at a folder of unrelated projects.
SAMPLE_REPOS: dict[str, str] = {
    "bookstore-python": "python",
    "bookstore-typescript": "typescript",
    "bookstore-go": "go",
    "bookstore-java": "java",
    "bookstore-rust": "rust",
}


@app.command()
def repos() -> None:
    """List every indexed repository."""
    db.wait_until_ready()
    rows = db.read(
        """
        MATCH (r:Repo)
        RETURN r.name AS name, r.root AS root, r.embedder AS embedder,
               coalesce(r.has_history, false) AS history,
               toString(r.indexed_at) AS indexed_at,
               """ + db.repo_counts_clause() + """
        ORDER BY r.name
        """
    )
    if not rows:
        console.print("[yellow]nothing indexed[/yellow]")
        return
    table = Table(title="indexed repositories")
    for column in ("repo", "files", "symbols", "chunks", "git", "indexed at"):
        table.add_column(column, justify="right" if column in
                         ("files", "symbols", "chunks") else "left")
    for row in rows:
        table.add_row(
            row["name"], f"{row['files']:,}", f"{row['symbols']:,}",
            f"{row['chunks']:,}", "yes" if row["history"] else "no",
            (row["indexed_at"] or "")[:19],
        )
    console.print(table)


@app.command()
def drop(
    repo: Annotated[list[str], typer.Argument(help="Repo name(s) to remove.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Remove indexed repositories. Deletes their files, symbols and chunks."""
    db.wait_until_ready()
    known = {r["name"] for r in db.read("MATCH (r:Repo) RETURN r.name AS name")}
    targets = [name for name in repo if name in known]
    missing = [name for name in repo if name not in known]
    for name in missing:
        console.print(f"[yellow]not indexed, skipping: {name}[/yellow]")
    if not targets:
        raise typer.Exit(1 if missing else 0)

    if not yes:
        console.print("about to delete: " + ", ".join(targets))
        if not typer.confirm("proceed?"):
            raise typer.Abort()
    for name in targets:
        with console.status(f"dropping {name}..."):
            db.wipe_repo(name)
        console.print(f"  dropped [bold]{name}[/bold]")


@app.command()
def demo(
    root: Annotated[Path, typer.Option(help="Generated sample repo.")]
        = Path(".cache/sample-repo"),
    skip_eval: Annotated[bool, typer.Option(help="Index only, do not score.")] = False,
) -> None:
    """Build the sample repo, index every language, and score the result."""
    if not root.exists():
        console.print(f"[yellow]{root} missing - run scripts/make_sample_history.py[/yellow]")
        raise typer.Exit(1)

    embedder = get_embedder()
    with console.status("waiting for Neo4j..."):
        db.wait_until_ready()
    db.ensure_schema(embedder.dim)
    with console.status(f"warming '{embedder.name}'..."):
        embedder.warm()

    for name, subdir in SAMPLE_REPOS.items():
        path = root / subdir
        if not path.exists():
            continue
        with console.status(f"indexing {name}..."):
            stats = index_repo(path, repo=name, force=True, embedder=embedder)
        console.print(
            f"  [green]{name}[/green]: {stats.files_indexed} files, "
            f"{stats.symbols} symbols, {stats.chunks} chunks, {stats.edges} edges, "
            f"{stats.test_edges} test links, {stats.cochange_edges} co-change pairs"
        )
    console.print()
    if not skip_eval:
        eval_cmd()


@app.command(name="eval")
def eval_cmd(
    repo: Annotated[str, typer.Option(help="Default repo for questions that omit one.")]
        = "bookstore-python",
    root: Annotated[Path, typer.Option(help="Sample root, for the grep baseline.")]
        = Path(".cache/sample-repo"),
    spec: Annotated[Path, typer.Option(help="Golden question set.")]
        = Path("eval/golden.yaml"),
    no_graph: Annotated[bool, typer.Option("--no-graph", help="Score without the graph pass.")] = False,
) -> None:
    """Measure token cost against a simulated grep-and-read baseline."""
    db.wait_until_ready()
    embedder = get_embedder()
    results = evaluation.run(spec, repo, root.resolve(), embedder, use_graph=not no_graph)

    table = Table(title=f"coderag eval  ({'no graph' if no_graph else 'hybrid+graph'})")
    table.add_column("id")
    table.add_column("question", max_width=38)
    table.add_column("grep", justify="right")
    table.add_column("coderag", justify="right")
    table.add_column("saving", justify="right")
    table.add_column("recall", justify="right")
    table.add_column("", justify="center")

    for r in results:
        saving = f"{r.reduction:.0f}x" if r.reduction >= 1 else f"{r.reduction:.2f}x"
        table.add_row(
            r.id, r.question,
            f"{r.baseline_tokens:,}", f"{r.coderag_tokens:,}",
            saving, f"{r.recall:.2f}",
            "[green]pass[/green]" if r.passed else "[red]FAIL[/red]",
        )
    console.print(table)

    reductions = [r.reduction for r in results if r.baseline_tokens > 0]
    failures = [r for r in results if not r.passed]
    med = evaluation.median(reductions)
    console.print(
        f"median token saving: [bold]{med:.0f}x[/bold] across "
        f"{len(reductions)} questions with a baseline"
    )
    console.print(f"passed: {len(results) - len(failures)}/{len(results)}")
    for r in failures:
        console.print(f"  [red]{r.id}[/red]: {r.detail}")
    if failures:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
