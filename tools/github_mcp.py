from github import Github, Auth, GithubException
from config import GITHUB_TOKEN


def get_client():
    auth = Auth.Token(GITHUB_TOKEN)
    return Github(auth=auth)

def get_repo(repo_url: str):
    # Extract owner/repo from URL
    # e.g. https://github.com/Arnav-Singh-5080/CricScope -> Arnav-Singh-5080/CricScope
    parts = repo_url.rstrip("/").split("github.com/")[-1]
    client = get_client()
    return client.get_repo(parts)


def create_issue(repo_url: str, title: str, body: str, labels: list = None) -> dict:
    print(f"  Creating GitHub issue...")
    try:
        repo = get_repo(repo_url)
        kwargs = {"title": title, "body": body}
        if labels:
            try:
                kwargs["labels"] = labels
            except Exception:
                pass  # Labels may not exist on repo
        issue = repo.create_issue(**kwargs)
        print(f"  Issue created: #{issue.number} — {issue.title}")
        print(f"  URL: {issue.html_url}")
        return {
            "success": True,
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url
        }
    except GithubException as e:
        print(f"  Issue creation failed: {e}")
        return {"success": False, "number": None, "url": None, "error": str(e)}


def create_pull_request(repo_url: str, title: str, body: str,
                        branch_name: str, base_branch: str = "main") -> dict:
    print(f"  Creating GitHub PR...")
    try:
        repo = get_repo(repo_url)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=base_branch
        )
        print(f"  PR created: #{pr.number} — {pr.title}")
        print(f"  URL: {pr.html_url}")
        return {
            "success": True,
            "number": pr.number,
            "title": pr.title,
            "url": pr.html_url
        }
    except GithubException as e:
        print(f"  PR creation failed: {e.data.get('message', str(e))}")
        # Common reason: no permission to push to someone else's repo
        # User needs to fork first
        return {"success": False, "number": None, "url": None, "error": str(e)}


def get_default_branch(repo_url: str) -> str:
    try:
        repo = get_repo(repo_url)
        return repo.default_branch
    except Exception:
        return "main"


if __name__ == "__main__":
    print("Testing GitHub connection...")
    client = get_client()
    user = client.get_user()
    print(f"Connected as: {user.login}")
    print(f"Public repos: {user.public_repos}")