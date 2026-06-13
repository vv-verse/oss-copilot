import git
import hashlib
from pathlib import Path
from config import REPOS_DIR, GITHUB_TOKEN


def clone_repo(url: str) -> str:
    repo_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    local_path = REPOS_DIR / repo_hash

    if local_path.exists():
        print(f"Repo already cloned. Pulling latest changes...")
        repo = git.Repo(local_path)
        repo.remotes.origin.pull()
    else:
        print(f"Cloning {url}...")
        auth_url = url.replace("https://", f"https://{GITHUB_TOKEN}@")
        git.Repo.clone_from(auth_url, local_path)
        print(f"Cloned to {local_path}")

    return str(local_path)


def get_file_contents(repo_path: str, max_files: int = 20) -> dict:
    p = Path(repo_path)
    contents = {}

    extensions = [".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                  ".py", ".json", ".md", ".txt", ".yml", ".yaml"]

    skip_dirs = {"node_modules", ".git", "venv", "__pycache__",
                 "dist", "build", ".next", "coverage"}

    count = 0
    for file_path in p.rglob("*"):
        if count >= max_files:
            break
        if any(skip in file_path.parts for skip in skip_dirs):
            continue
        if file_path.suffix in extensions and file_path.is_file():
            try:
                contents[str(file_path.relative_to(p))] = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )[:3000]
                count += 1
            except Exception:
                continue

    return contents


def get_diff(repo_path: str) -> str:
    repo = git.Repo(repo_path)
    return repo.git.diff()


def create_branch(repo_path: str, branch_name: str):
    repo = git.Repo(repo_path)
    repo.git.checkout("-b", branch_name)
    print(f"Created and switched to branch: {branch_name}")


def commit_all(repo_path: str, message: str):
    repo = git.Repo(repo_path)
    repo.git.add("-A")
    repo.git.commit("-m", message)
    print(f"Committed: {message}")


def push_branch(repo_path: str, branch_name: str):
    repo = git.Repo(repo_path)
    repo.remotes.origin.push(branch_name)
    print(f"Pushed branch: {branch_name}")


def reset_changes(repo_path: str):
    repo = git.Repo(repo_path)
    repo.git.checkout("--", ".")
    print("All uncommitted changes reset.")


if __name__ == "__main__":
    print("git_tools.py loaded successfully.")
    print("Functions: clone_repo, get_file_contents, get_diff,")
    print("           create_branch, commit_all, push_branch, reset_changes")