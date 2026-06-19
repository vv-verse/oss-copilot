import json
import re
import uuid
from pathlib import Path
from tools.gemini import ask
from database import get_conn, log


def load_prompt(filename):
    return Path(f"prompts/{filename}").read_text(encoding="utf-8")


def format_file_contents(files, max_chars=8000):
    result = ""
    total = 0
    for name, content in files.items():
        chunk = f"\n=== {name} ===\n{content}\n"
        if total + len(chunk) > max_chars:
            break
        result += chunk
        total += len(chunk)
    return result


def parse_json_response(response):
    if "JSONSTART" in response and "JSONEND" in response:
        match = re.search(r"JSONSTART\s*(.*?)\s*JSONEND", response, re.DOTALL)
        if match:
            json_str = "{" + match.group(1).strip() + "}"
            try:
                return json.loads(json_str)
            except Exception as e:
                print(f"  JSONSTART parse failed: {e}")

    clean = re.sub(r"```json|```", "", response).strip()

    if clean:
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    print(f"  Raw response was:\n{response[:400]}")
    raise ValueError(f"Could not parse JSON from response")


def analyse(repo_knowledge, mode, user_input):
    print(f"\n[Stage 2] Analysing ({mode} mode)...")
    print(f"  Input: {user_input[:80]}")

    repo_name = repo_knowledge["name"]
    framework = repo_knowledge["framework"]
    language = repo_knowledge["language"]
    summary = repo_knowledge["summary"]
    files = repo_knowledge.get("files", {})
    file_contents = format_file_contents(files)

    if mode == "bug":
        template = load_prompt("analyse_bug.txt")
    else:
        template = load_prompt("analyse_feature.txt")

    prompt = template.format(
        repo_name=repo_name,
        framework=framework,
        language=language,
        repo_summary=summary,
        file_contents=file_contents,
        user_input=user_input
    )

    print("  Sending to Gemini...")
    response = ask(prompt)

    print("  Parsing response...")
    parsed = parse_json_response(response)

    # Filter out lock files from affected_files — these should never be hand-edited
    lock_files = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock")
    if "affected_files" in parsed:
        parsed["affected_files"] = [
            f for f in parsed["affected_files"] if not f.endswith(lock_files)
        ]

    slug = re.sub(r"[^a-z0-9]+", "-", user_input[:30].lower()).strip("-")
    branch_name = f"copilot/{mode}/{slug}"

    if mode == "bug":
        aider_task = (
            f"Fix this bug in {repo_name}.\n"
            f"Bug: {user_input}\n"
            f"Root cause: {parsed.get('root_cause', '')}\n"
            f"Fix strategy: {parsed.get('fix_strategy', '')}\n"
            f"Minimum changes only. Match existing code style exactly."
        )
    else:
        aider_task = (
            f"Implement this feature in {repo_name}.\n"
            f"Feature: {user_input}\n"
            f"Plan: {parsed.get('implementation_plan', '')}\n"
            f"Follow existing code style and architecture. Keep it minimal and clean."
        )

    plan = {
        "contribution_id": str(uuid.uuid4()),
        "mode": mode,
        "user_input": user_input,
        "branch_name": branch_name,
        "affected_files": parsed.get("affected_files", []),
        "aider_task": aider_task,
        "fix_strategy": parsed.get("fix_strategy") or parsed.get("implementation_plan", ""),
        "complexity": parsed.get("complexity", "MEDIUM"),
        "confidence": parsed.get("confidence", 0.5),
        "acceptance_probability": parsed.get("acceptance_probability", "MEDIUM"),
    }

    conn = get_conn()
    conn.execute(
        "INSERT INTO contributions "
        "(id, repo_id, mode, user_input, status, affected_files, plan, branch_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            plan["contribution_id"],
            repo_knowledge["id"],
            mode,
            user_input,
            "analysed",
            json.dumps(plan["affected_files"]),
            plan["fix_strategy"],
            branch_name
        )
    )
    conn.commit()
    conn.close()

    log(plan["contribution_id"], "analyser", f"Done. Complexity: {plan['complexity']}")

    print(f"  Affected files: {plan['affected_files']}")
    print(f"  Complexity: {plan['complexity']}")
    print(f"  Confidence: {plan['confidence']}")

    return plan


def auto_discover(repo_knowledge: dict) -> list:
    print(f"\n[Auto Discovery] Scanning {repo_knowledge['name']} for issues...")

    files = repo_knowledge.get("files", {})
    file_contents = format_file_contents(files, max_chars=10000)
    framework = repo_knowledge["framework"]
    language = repo_knowledge["language"]
    summary = repo_knowledge["summary"]

    prompt = f"""You are an expert code reviewer analysing a {framework} project.

REPO SUMMARY:
{summary}

SOURCE FILES:
{file_contents}

Your job: Find real, fixable issues in this codebase.

Look for:
- Missing features that are obviously needed (search, filters, pagination, loading states)
- UI/UX improvements (accessibility, mobile responsiveness, empty states)
- Code bugs (unhandled errors, broken logic, missing validation)
- Performance issues (missing caching, unnecessary operations)
- Security issues (exposed keys, missing input sanitisation)
- Documentation gaps (missing README sections, no contributing guide)
- Missing error handling around API calls or file operations
- Hardcoded values that should be configurable

Find 5 specific, actionable issues. Be concrete about exactly what file to change and what to add.

Respond in this exact format:
DISCOVERYSTART
[
  {{
    "id": 1,
    "type": "feature",
    "title": "short title under 60 chars",
    "description": "specific description of exactly what to fix and how",
    "severity": "HIGH",
    "effort": "LOW",
    "files": ["file1.py"]
  }},
  {{
    "id": 2,
    "type": "bug",
    "title": "short title under 60 chars",
    "description": "specific description of exactly what to fix and how",
    "severity": "MEDIUM",
    "effort": "LOW",
    "files": ["file1.py"]
  }}
]
DISCOVERYEND

Return exactly 5 issues. type must be either bug or feature."""

    print("  Asking Gemini to scan the codebase...")
    response = ask(prompt)

    issues = []
    if "DISCOVERYSTART" in response and "DISCOVERYEND" in response:
        match = re.search(r"DISCOVERYSTART\s*(.*?)\s*DISCOVERYEND", response, re.DOTALL)
        if match:
            try:
                issues = json.loads(match.group(1).strip())
            except Exception as e:
                print(f"  Parse error: {e}")

    if not issues:
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            try:
                issues = json.loads(match.group())
            except Exception:
                pass

    print(f"  Found {len(issues)} potential issues")
    return issues


if __name__ == "__main__":
    from pipeline.understander import understand_repo

    repo = understand_repo("https://github.com/Arnav-Singh-5080/CricScope")
    issues = auto_discover(repo)
    for i in issues:
        print(f"\n{i['id']}. [{i['type'].upper()}] {i['title']}")
        print(f"   {i['description']}")