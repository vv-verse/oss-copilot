import json
import uuid
from pathlib import Path
from tools.gemini import ask
from tools.git_tools import clone_repo, get_file_contents
from database import get_conn, log


def detect_framework(files: dict) -> dict:
    framework = "unknown"
    language = "unknown"
    test_command = ""
    lint_command = ""

    if "package.json" in files:
        language = "javascript"
        try:
            pkg = json.loads(files["package.json"])
            scripts = pkg.get("scripts", {})
            test_command = scripts.get("test", "npm test")
            lint_command = scripts.get("lint", "")
            deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {})
            }
            if "next" in deps:
                framework = "nextjs"
            elif "react" in deps:
                framework = "react"
            elif "vue" in deps:
                framework = "vue"
            elif "express" in deps:
                framework = "express"
            else:
                framework = "javascript"
        except Exception:
            framework = "javascript"

    elif "requirements.txt" in files or "pyproject.toml" in files:
        language = "python"
        test_command = "pytest"
        lint_command = "flake8"
        framework = "python"

    elif any(f.endswith(".html") for f in files):
        language = "html"
        framework = "static"

    return {
        "framework": framework,
        "language": language,
        "test_command": test_command,
        "lint_command": lint_command
    }


def summarise_repo(files: dict, framework: str) -> str:
    file_content = ""
    for name, content in list(files.items())[:10]:
        file_content += f"\n\n=== {name} ===\n{content[:2000]}"

    prompt = (
        f"You are analysing a {framework} repository.\n"
        f"Here are its key files:\n{file_content}\n\n"
        "In 200 words or less, summarise:\n"
        "1. What this project does\n"
        "2. Its main components or pages\n"
        "3. The tech stack\n"
        "Be specific and factual. No fluff."
    )
    return ask(prompt)


def understand_repo(repo_url: str) -> dict:
    print(f"\n[Stage 1] Understanding repo: {repo_url}")

    # Clone
    local_path = clone_repo(repo_url)
    print(f"  Local path: {local_path}")

    # Read files
    print("  Reading files...")
    files = get_file_contents(local_path)
    print(f"  Found {len(files)} files")

    # Detect framework
    detected = detect_framework(files)
    print(f"  Framework: {detected['framework']} / {detected['language']}")

    # Gemini summary
    print("  Asking Gemini to summarise architecture...")
    summary = summarise_repo(files, detected["framework"])

    # Build knowledge object
    repo_id = str(uuid.uuid4())
    repo_name = repo_url.rstrip("/").split("/")[-1]

    knowledge = {
        "id": repo_id,
        "url": repo_url,
        "name": repo_name,
        "framework": detected["framework"],
        "language": detected["language"],
        "test_command": detected["test_command"],
        "lint_command": detected["lint_command"],
        "summary": summary,
        "local_path": local_path,
        "files": files
    }

    # Save to DB
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO repositories
        (id, url, name, framework, language, test_command, lint_command, summary, local_path)
        VALUES (:id, :url, :name, :framework, :language, :test_command, :lint_command, :summary, :local_path)
    """, {k: v for k, v in knowledge.items() if k != "files"})
    conn.commit()
    conn.close()

    log(repo_id, "understander", f"Understood repo: {repo_name} ({detected['framework']})")
    print(f"  Saved to database.")
    print(f"\n--- REPO SUMMARY ---\n{summary}\n")

    return knowledge


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/psf/requests"
    result = understand_repo(url)
    print(f"Framework : {result['framework']}")
    print(f"Language  : {result['language']}")
    print(f"Test cmd  : {result['test_command']}")