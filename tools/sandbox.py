import subprocess
import os


def run(cmd: list, cwd: str, timeout: int = 60, env: dict = None) -> dict:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env or os.environ.copy()
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {e}",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }


if __name__ == "__main__":
    result = run(["python", "--version"], cwd=".")
    print(f"Success: {result['success']}")
    print(f"Output: {result['stdout'] or result['stderr']}")