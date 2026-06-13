import json
import re
from tools.gemini import ask
from tools.github_mcp import create_issue
from database import get_conn, log


def generate_issue_content(repo_knowledge: dict, plan: dict) -> dict:
    mode = plan["mode"]
    user_input = plan["user_input"]
    repo_name = repo_knowledge["name"]
    framework = repo_knowledge["framework"]
    fix_strategy = plan.get("fix_strategy", "")

    if mode == "bug":
        prompt = f"""Write a GitHub issue report for a bug in a {framework} project called {repo_name}.

Bug description: {user_input}
Root cause found: {fix_strategy}

Write a clear, professional issue in this format:
ISSUESTART
  "title": "bug: clear short title under 60 chars",
  "body": "## Bug Description\\n\\n{user_input}\\n\\n## Root Cause\\n\\n{fix_strategy}\\n\\n## Steps to Reproduce\\n\\n1. Step one\\n2. Step two\\n\\n## Expected Behavior\\n\\nWhat should happen.\\n\\n## Actual Behavior\\n\\nWhat actually happens.\\n\\n## Environment\\n\\n- Framework: {framework}\\n- Repo: {repo_name}"
ISSUEEND

Title must start with: bug:"""
    else:
        prompt = f"""Write a GitHub feature request issue for a {framework} project called {repo_name}.

Feature request: {user_input}
Implementation plan: {fix_strategy}

Write a clear, professional issue in this format:
ISSUESTART
  "title": "feat: clear short title under 60 chars",
  "body": "## Feature Request\\n\\n{user_input}\\n\\n## Motivation\\n\\nWhy this feature would be valuable.\\n\\n## Proposed Implementation\\n\\n{fix_strategy}\\n\\n## Acceptance Criteria\\n\\n- [ ] Criteria 1\\n- [ ] Criteria 2"
ISSUEEND

Title must start with: feat:"""

    response = ask(prompt)

    # Parse ISSUESTART/ISSUEEND
    if "ISSUESTART" in response and "ISSUEEND" in response:
        match = re.search(r"ISSUESTART\s*(.*?)\s*ISSUEEND", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads("{" + match.group(1).strip() + "}")
                return parsed
            except Exception:
                pass

    # Fallback
    clean = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(clean)
    except Exception:
        pass

    # Last resort defaults
    return {
        "title": f"{'bug' if mode == 'bug' else 'feat'}: {user_input[:50]}",
        "body": f"## Description\n\n{user_input}\n\n## Plan\n\n{fix_strategy}"
    }


def create_github_issue(repo_knowledge: dict, plan: dict) -> dict:
    print(f"\n[Issue Creator] Generating issue for GitHub...")

    issue_content = generate_issue_content(repo_knowledge, plan)
    title = issue_content.get("title", f"{plan['mode']}: {plan['user_input'][:50]}")
    body = issue_content.get("body", plan["user_input"])

    print(f"  Title: {title}")

    result = create_issue(
        repo_url=repo_knowledge["url"],
        title=title,
        body=body
    )

    if result["success"]:
        # Save issue number to DB
        conn = get_conn()
        conn.execute(
            "UPDATE contributions SET status = ? WHERE id = ?",
            ("issue_created", plan["contribution_id"])
        )
        conn.commit()
        conn.close()
        log(plan["contribution_id"], "issue_creator",
            f"Issue #{result['number']} created: {result['url']}")

    return {
        "issue_number": result.get("number"),
        "issue_url": result.get("url"),
        "issue_title": title,
        "success": result["success"]
    }