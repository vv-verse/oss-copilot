import re
from pathlib import Path
from tools.gemini import ask
from tools.git_tools import get_diff, create_branch
from database import get_conn, log


def read_file(repo_path: str, filename: str) -> str:
    p = Path(repo_path) / filename
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    return ""


def write_file(repo_path: str, filename: str, content: str):
    p = Path(repo_path) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def extract_code(response: str, filename: str) -> str:
    # Try to extract code from markdown code block
    patterns = [
        r"```(?:python|javascript|html|css|typescript|js|ts)?\n(.*?)```",
        r"```\n(.*?)```",
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()

    # If no code block found, return the whole response stripped
    return response.strip()


def run_coder(repo_knowledge: dict, plan: dict) -> dict:
    print(f"\n[Stage 3] Coding with Gemini...")

    repo_path = repo_knowledge["local_path"]
    affected_files = plan["affected_files"]
    aider_task = plan["aider_task"]
    branch_name = plan["branch_name"]
    contribution_id = plan["contribution_id"]

    # Create git branch
    try:
        create_branch(repo_path, branch_name)
    except Exception as e:
        print(f"  Branch already exists, continuing: {e}")

    all_diffs = []
    files_changed = []

    for filename in affected_files:
        print(f"\n  Working on: {filename}")

        # Read current file content
        current_content = read_file(repo_path, filename)

        if not current_content:
            print(f"  File not found: {filename} — skipping")
            continue

        # Ask Gemini to modify the file
        prompt = f"""You are a software engineer implementing a change in a {repo_knowledge['framework']} project.

TASK:
{aider_task}

CURRENT FILE: {filename}
{current_content[:6000]}

Instructions:
- Implement the requested change in this file
- Keep all existing functionality intact
- Match the existing code style exactly
- Make minimal, clean changes
- Return ONLY the complete updated file content inside a code block
- Do not explain, just return the code

Return the complete updated {filename} content:"""

        print(f"  Asking Gemini to implement changes...")
        response = ask(prompt)

        # Extract the code from response
        new_content = extract_code(response, filename)

        if not new_content or len(new_content) < 50:
            print(f"  Gemini returned empty response for {filename}")
            continue

        if new_content == current_content:
            print(f"  No changes made to {filename}")
            continue

        # Write the updated file
        write_file(repo_path, filename, new_content)
        files_changed.append(filename)
        print(f"  Updated {filename} ({len(new_content)} chars)")

    # Get the full diff
    diff = get_diff(repo_path)

    if diff:
        print(f"\n  Total diff: {len(diff)} chars across {len(files_changed)} files")
    else:
        print("\n  No changes detected in diff")

    code_result = {
        "success": len(diff) > 0,
        "diff": diff,
        "branch_name": branch_name,
        "affected_files": affected_files,
        "files_changed": files_changed,
        "had_changes": len(diff) > 0
    }

    # Save to DB
    conn = get_conn()
    conn.execute(
        "UPDATE contributions SET diff = ?, status = ? WHERE id = ?",
        (diff, "coded", contribution_id)
    )
    conn.commit()
    conn.close()

    log(contribution_id, "coder", f"Done. Changed {len(files_changed)} files.")

    return code_result


if __name__ == "__main__":
    from pipeline.understander import understand_repo
    from pipeline.analyser import analyse

    # Reset repo first
    import git
    from config import REPOS_DIR
    import hashlib
    url = "https://github.com/Arnav-Singh-5080/CricScope"
    repo_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    repo_path = str(REPOS_DIR / repo_hash)
    try:
        r = git.Repo(repo_path)
        r.git.checkout("main")
    except Exception as e:
        print(f"Reset note: {e}")

    repo = understand_repo(url)
    plan = analyse(
        repo,
        mode="feature",
        user_input="Add a dark mode toggle to the Streamlit dashboard"
    )
    result = run_coder(repo, plan)

    print(f"\n--- CODER RESULT ---")
    print(f"Success      : {result['success']}")
    print(f"Files changed: {result['files_changed']}")
    print(f"Diff preview :\n{result['diff'][:600]}")