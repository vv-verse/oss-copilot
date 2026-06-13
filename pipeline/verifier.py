import json
import re
from pathlib import Path
from tools.gemini import ask
from tools.sandbox import run
from database import get_conn, log


def run_tests(repo_path: str, test_command: str) -> dict:
    if not test_command:
        return {"ran": False, "passed": None, "output": "No test command found"}

    print(f"  Running tests: {test_command}")
    result = run(test_command.split(), cwd=repo_path, timeout=120)

    return {
        "ran": True,
        "passed": result["success"],
        "output": (result["stdout"] + result["stderr"])[:1000]
    }


def run_lint(repo_path: str, lint_command: str) -> dict:
    if not lint_command:
        return {"ran": False, "passed": None, "output": "No lint command found"}

    print(f"  Running lint: {lint_command}")
    result = run(lint_command.split(), cwd=repo_path, timeout=60)

    return {
        "ran": True,
        "passed": result["success"],
        "output": (result["stdout"] + result["stderr"])[:500]
    }


def review_diff(diff: str, framework: str) -> dict:
    if not diff:
        return {
            "score": 0,
            "verdict": "REVISE",
            "concerns": ["No changes were made"],
            "summary": "No diff to review"
        }

    prompt_path = Path("prompts/review_diff.txt")
    template = prompt_path.read_text(encoding="utf-8")

    prompt = template.format(
        framework=framework,
        diff=diff[:4000]
    )

    print("  Asking Gemini to review the diff...")
    response = ask(prompt)

    # Try REVIEWSTART/REVIEWEND markers first
    if "REVIEWSTART" in response and "REVIEWEND" in response:
        match = re.search(r"REVIEWSTART\s*(.*?)\s*REVIEWEND", response, re.DOTALL)
        if match:
            try:
                parsed = json.loads("{" + match.group(1).strip() + "}")
                return {
                    "score": parsed.get("score", 5),
                    "verdict": parsed.get("verdict", "REVISE"),
                    "concerns": parsed.get("concerns", []),
                    "summary": parsed.get("summary", "")
                }
            except Exception:
                pass

    # Fallback: strip fences and parse
    clean = re.sub(r"```json|```", "", response).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        parsed = {}
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception:
                pass

    return {
        "score": parsed.get("score", 5),
        "verdict": parsed.get("verdict", "REVISE"),
        "concerns": parsed.get("concerns", []),
        "summary": parsed.get("summary", "Review could not be parsed")
    }


def verify(repo_knowledge: dict, plan: dict, code_result: dict) -> dict:
    print(f"\n[Stage 4] Verifying changes...")

    repo_path = repo_knowledge["local_path"]
    diff = code_result.get("diff", "")
    contribution_id = plan["contribution_id"]

    # Run tests
    test_result = run_tests(repo_path, repo_knowledge.get("test_command", ""))
    print(f"  Tests: {'PASS' if test_result['passed'] else 'SKIP/FAIL'}")

    # Run lint
    lint_result = run_lint(repo_path, repo_knowledge.get("lint_command", ""))
    print(f"  Lint: {'PASS' if lint_result['passed'] else 'SKIP/FAIL'}")

    # Review diff with Gemini
    review = review_diff(diff, repo_knowledge["framework"])
    print(f"  Review score: {review['score']}/10")
    print(f"  Verdict: {review['verdict']}")

    if review["concerns"]:
        print(f"  Concerns:")
        for c in review["concerns"]:
            print(f"    - {c}")

    verification = {
        "test_result": test_result,
        "lint_result": lint_result,
        "review_score": review["score"],
        "review_verdict": review["verdict"],
        "review_concerns": review["concerns"],
        "review_summary": review["summary"],
        "ready_for_human": review["score"] >= 5
    }

    # Save to DB
    conn = get_conn()
    conn.execute(
        "UPDATE contributions SET test_result = ?, review_score = ?, review_notes = ?, status = ? WHERE id = ?",
        (
            json.dumps(test_result),
            review["score"],
            review["summary"],
            "verified",
            contribution_id
        )
    )
    conn.commit()
    conn.close()

    log(contribution_id, "verifier", f"Score: {review['score']}/10 — {review['verdict']}")

    return verification


if __name__ == "__main__":
    from pipeline.understander import understand_repo
    from pipeline.analyser import analyse
    from pipeline.coder import run_coder

    url = "https://github.com/Arnav-Singh-5080/CricScope"
    repo = understand_repo(url)
    plan = analyse(repo, mode="feature",
                   user_input="Add a dark mode toggle to the Streamlit dashboard")
    code_result = run_coder(repo, plan)
    verification = verify(repo, plan, code_result)

    print(f"\n--- VERIFICATION RESULT ---")
    print(f"Score   : {verification['review_score']}/10")
    print(f"Verdict : {verification['review_verdict']}")
    print(f"Summary : {verification['review_summary']}")
    print(f"Ready   : {verification['ready_for_human']}")