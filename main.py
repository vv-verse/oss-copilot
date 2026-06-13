import argparse
import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich import box

from database import init_db
from pipeline.understander import understand_repo
from pipeline.analyser import analyse
from pipeline.coder import run_coder
from pipeline.verifier import verify
from tools.git_tools import commit_all, push_branch, reset_changes

console = Console()


def show_diff(diff: str):
    if not diff:
        console.print("[yellow]No diff to show[/yellow]")
        return
    preview = diff[:3000]
    if len(diff) > 3000:
        preview += f"\n... ({len(diff) - 3000} more chars)"
    console.print(Syntax(preview, "diff", theme="monokai"))


def show_summary(repo, plan, code_result, verification):
    console.rule("[bold]Summary[/bold]")

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value")

    table.add_row("Repo", repo["name"])
    table.add_row("Mode", plan["mode"])
    table.add_row("Request", plan["user_input"][:60])
    table.add_row("Branch", plan["branch_name"])
    table.add_row("Files changed", ", ".join(code_result.get("files_changed", [])))
    table.add_row("Complexity", plan["complexity"])
    table.add_row("Confidence", str(plan["confidence"]))
    table.add_row("Review score", f"{verification['review_score']}/10")
    table.add_row("Verdict", verification["review_verdict"])

    console.print(table)

    if verification["review_concerns"]:
        console.print("\n[yellow]Reviewer concerns:[/yellow]")
        for c in verification["review_concerns"]:
            console.print(f"  • {c}")

    console.print(Panel(
        verification["review_summary"],
        title="Review summary",
        border_style="yellow"
    ))


def generate_pr_draft(repo, plan, verification) -> dict:
    from tools.gemini import ask
    from pathlib import Path
    import re

    template = Path("prompts/generate_pr.txt").read_text(encoding="utf-8")

    prompt = template.format(
        repo_name=repo["name"],
        framework=repo["framework"],
        mode=plan["mode"],
        user_input=plan["user_input"],
        fix_strategy=plan["fix_strategy"],
        review_summary=verification["review_summary"]
    )

    response = ask(prompt)

    # Parse — handle JSONSTART/JSONEND or raw JSON
    if "JSONSTART" in response and "JSONEND" in response:
        match = re.search(r"JSONSTART\s*(.*?)\s*JSONEND", response, re.DOTALL)
        if match:
            try:
                return json.loads("{" + match.group(1).strip() + "}")
            except Exception:
                pass

    clean = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass

    # Fallback
    return {
        "title": f"{plan['mode']}: {plan['user_input'][:50]}",
        "body": f"## What does this PR do?\n\n{plan['fix_strategy']}\n\n## Review\n\n{verification['review_summary']}",
        "commit_message": f"{plan['mode']}: {plan['user_input'][:50]}"
    }


def human_gate(repo, plan, code_result, verification, dry_run=False) -> str:
    console.rule("[bold green]Human Approval Gate[/bold green]")

    # Show diff
    console.print("\n[cyan]Changes made:[/cyan]")
    show_diff(code_result.get("diff", ""))

    # Show summary
    show_summary(repo, plan, code_result, verification)

    # Generate PR draft
    console.print("\n[cyan]Generating PR draft...[/cyan]")
    pr_draft = generate_pr_draft(repo, plan, verification)

    console.print(Panel(
        f"[bold]{pr_draft.get('title', '')}[/bold]\n\n{pr_draft.get('body', '')}",
        title="PR Draft",
        border_style="blue"
    ))

    console.print(f"\n[dim]Commit message: {pr_draft.get('commit_message', '')}[/dim]")

    # Decision
    console.print("\n[bold]What do you want to do?[/bold]")
    console.print("  [green]A[/green] — Create issue + commit + push + open PR")
    console.print("  [red]R[/red] — Reject, reset all changes")
    console.print("  [yellow]S[/yellow] — Skip for now (keep local changes)")

    decision = console.input("\nYour choice (A/R/S): ").strip().upper()

    if decision == "A":
        if dry_run:
            console.print("[yellow]Dry run — skipping issue/commit/push[/yellow]")
            return "dry_run"

        from pipeline.issue_creator import create_github_issue
        from tools.github_mcp import create_pull_request, get_default_branch

        # Step 1: Create GitHub issue
        console.print("\n[cyan]Step 1: Creating GitHub issue...[/cyan]")
        issue = create_github_issue(repo, plan)

        if issue["success"]:
            console.print(f"[green]Issue #{issue['issue_number']} created: {issue['issue_url']}[/green]")
            # Append issue reference to PR body
            pr_body = pr_draft.get("body", "")
            pr_body += f"\n\n---\nCloses #{issue['issue_number']}"
            pr_draft["body"] = pr_body
        else:
            console.print("[yellow]Issue creation failed — continuing without issue link[/yellow]")

        # Step 2: Commit and push
        console.print("\n[cyan]Step 2: Committing and pushing...[/cyan]")
        try:
            commit_msg = pr_draft.get("commit_message", "feat: changes")
            if issue.get("issue_number"):
                commit_msg += f" (#{issue['issue_number']})"
            commit_all(repo["local_path"], commit_msg)
            push_branch(repo["local_path"], plan["branch_name"])
            console.print(f"[green]Pushed: {plan['branch_name']}[/green]")
        except Exception as e:
            console.print(f"[red]Push failed: {e}[/red]")
            console.print("[yellow]You may need to fork the repo first. See note below.[/yellow]")
            return "push_failed"

        # Step 3: Create PR
        console.print("\n[cyan]Step 3: Creating pull request...[/cyan]")
        base = get_default_branch(repo["url"])
        pr = create_pull_request(
            repo_url=repo["url"],
            title=pr_draft.get("title", "feat: changes"),
            body=pr_draft.get("body", ""),
            branch_name=plan["branch_name"],
            base_branch=base
        )

        if pr["success"]:
            console.print(f"\n[bold green]PR #{pr['number']} created![/bold green]")
            console.print(f"[blue]{pr['url']}[/blue]")

            # Save PR URL to DB
            conn = get_conn()
            conn.execute(
                "UPDATE contributions SET pr_url = ?, status = ? WHERE id = ?",
                (pr["url"], "submitted", plan["contribution_id"])
            )
            conn.commit()
            conn.close()
        else:
            console.print(f"[red]PR creation failed: {pr.get('error', '')}[/red]")
            console.print("\n[yellow]To create the PR manually:[/yellow]")
            console.print(f"  Go to: https://github.com/{repo['url'].split('github.com/')[-1]}/compare/{plan['branch_name']}")

        return "approved"

    elif decision == "R":
        try:
            reset_changes(repo["local_path"])
            console.print("[red]All changes reset.[/red]")
        except Exception as e:
            console.print(f"[yellow]Reset note: {e}[/yellow]")
        return "rejected"

    else:
        console.print("[yellow]Skipped. Local changes kept.[/yellow]")
        return "skipped"

def pick_issue(issues: list) -> dict:
    from rich.table import Table
    from rich import box

    console.rule("[bold]Issues Found[/bold]")

    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Type", width=8)
    table.add_column("Severity", width=10)
    table.add_column("Effort", width=8)
    table.add_column("Title", width=40)
    table.add_column("Files")

    severity_colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}

    for issue in issues:
        sev = issue.get("severity", "MEDIUM")
        color = severity_colors.get(sev, "white")
        table.add_row(
            str(issue["id"]),
            issue.get("type", ""),
            f"[{color}]{sev}[/{color}]",
            issue.get("effort", ""),
            issue.get("title", ""),
            ", ".join(issue.get("files", []))
        )

    console.print(table)

    console.print("\n[dim]Details:[/dim]")
    for issue in issues:
        console.print(f"\n  [cyan]{issue['id']}.[/cyan] {issue['title']}")
        console.print(f"     {issue['description']}")

    choice = console.input(
        f"\nPick an issue to fix (1-{len(issues)}), or Q to quit: "
    ).strip().upper()

    if choice == "Q":
        return None

    try:
        idx = int(choice) - 1
        return issues[idx]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice[/red]")
        return None


def main():
    parser = argparse.ArgumentParser(description="OSS Copilot — AI-assisted contributions")
    parser.add_argument("--repo", required=True, help="GitHub repo URL")
    parser.add_argument("--mode", choices=["bug", "feature", "auto"], required=True)
    parser.add_argument("--input", required=False, default="",
                        help="Bug description or feature request (not needed for auto mode)")
    parser.add_argument("--dry-run", action="store_true", help="Stop before pushing")
    args = parser.parse_args()

    init_db()
    console.rule("[bold]OSS Engineering Copilot[/bold]")
    console.print(f"Repo  : {args.repo}")
    console.print(f"Mode  : {args.mode}\n")

    # Stage 1 — always runs
    repo = understand_repo(args.repo)

    # Auto mode — discover issues and let user pick
    if args.mode == "auto":
        from pipeline.analyser import auto_discover
        issues = auto_discover(repo)

        if not issues:
            console.print("[red]No issues discovered. Try manual mode.[/red]")
            return

        chosen = pick_issue(issues)
        if not chosen:
            console.print("[yellow]Exited.[/yellow]")
            return

        # Convert chosen issue into plan inputs
        mode = chosen["type"]        # "bug" or "feature"
        user_input = chosen["description"]
        console.print(f"\n[green]Working on: {chosen['title']}[/green]\n")
    else:
        if not args.input:
            console.print("[red]--input is required for bug and feature modes[/red]")
            return
        mode = args.mode
        user_input = args.input

    # Stage 2
    plan = analyse(repo, mode, user_input)

    # Stage 3
    code_result = run_coder(repo, plan)

    if not code_result["had_changes"]:
        console.print("[red]No code changes were made. Exiting.[/red]")
        return

    # Stage 4
    verification = verify(repo, plan, code_result)

    # Human gate
    decision = human_gate(repo, plan, code_result, verification, dry_run=args.dry_run)
    console.print(f"\nFinal decision: [bold]{decision}[/bold]")


if __name__ == "__main__":
    main()