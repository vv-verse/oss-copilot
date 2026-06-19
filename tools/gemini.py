from google import genai
import time
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = "gemini-2.5-flash-lite"

# Build client list from all available keys
_keys = []
for var in ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
    k = os.getenv(var)
    if k:
        _keys.append(k)

_clients = [genai.Client(api_key=k) for k in _keys]
print(f"Gemini: {len(_clients)} account(s) loaded")


def ask(prompt: str, context: str = "", max_retries: int = 3) -> str:
    full_prompt = f"{context}\n\n{prompt}" if context else prompt

    # Try each client + each model before giving up
    models_to_try = [GEMINI_MODEL]
    if FALLBACK_MODEL != GEMINI_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    for model in models_to_try:
        for idx, client in enumerate(_clients):
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=full_prompt
                    )
                    if response.text:
                        return response.text
                    else:
                        print(f"  Empty response from account {idx+1}, model {model}")
                        break
                except Exception as e:
                    error = str(e)

                    if "limit: 0" in error:
                        print(f"  Zero quota on {model} (account {idx+1}). Skipping immediately.")
                        break

                    elif "429" in error or "RESOURCE_EXHAUSTED" in error:
                        if attempt < max_retries - 1:
                            print(f"  Rate limited (account {idx+1}, {model}). Waiting 35s...")
                            time.sleep(35)
                        else:
                            print(f"  Account {idx+1} exhausted on {model}. Trying next...")
                        break

                    elif "503" in error or "UNAVAILABLE" in error:
                        print(f"  Model {model} temporarily overloaded. Trying next...")
                        break

                    else:
                        raise

    print("  All accounts and models exhausted for today.")
    print("  Quota resets at midnight Pacific time (~1:30 PM IST).")
    raise Exception("All Gemini quotas exhausted")


if __name__ == "__main__":
    print("Testing Gemini connection...")
    response = ask("Reply with exactly: SYSTEM OK")
    print(f"Response: {response}")