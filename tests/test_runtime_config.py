import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.runtime import RuntimeConfig, RuntimeConfigurationError


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def invalid(**kwargs):
    try: RuntimeConfig(**kwargs)
    except RuntimeConfigurationError: return True
    return False


def main():
    config = RuntimeConfig()
    check("Valid default local config", config.port == 8000 and config.timezone_name == "Asia/Kolkata")
    check("Invalid port", invalid(port=0))
    check("Invalid host", invalid(host="bad host"))
    check("Invalid timezone", invalid(timezone_name="UTC"))
    check("Invalid DB path", invalid(db_path=""))
    check("Invalid log level", invalid(log_level="TRACE"))
    os.environ["JARVIS_PORT"] = "bad"
    try:
        try: RuntimeConfig.from_environment()
        except RuntimeConfigurationError: parsed = True
        else: parsed = False
    finally: os.environ.pop("JARVIS_PORT", None)
    check("Malformed port rejected", parsed)
    os.environ["JARVIS_LLM_ENABLED"] = "false"
    check("Gemini disabled", not RuntimeConfig.from_environment().llm.enabled)
    os.environ["JARVIS_LLM_ENABLED"] = "true"
    try: check("Gemini enabled missing key", RuntimeConfig.from_environment().llm.enabled and not os.getenv("GEMINI_API_KEY"))
    finally: os.environ.pop("JARVIS_LLM_ENABLED", None)
    check("Optional provider does not kill core config", RuntimeConfig().port == 8000)
    check("LIVE remains unsupported", RuntimeConfig().safe_status()["live_execution_supported"] is False)
    example = Path(__file__).resolve().parent.parent / ".env.example"
    text = example.read_text(encoding="utf-8")
    check("Env example contains no credential values", all(line.endswith("=") or "127.0.0.1" in line or "Asia/Kolkata" in line or "gemini-2.5-flash" in line for line in text.splitlines() if "KEY=" in line or "PIN=" in line or "TOTP=" in line))
    status = RuntimeConfig().safe_status(False)
    check("Secret status boolean only", isinstance(status["llm_configured"], bool) and "API_KEY" not in str(status))
    check("CORS local defaults safe", "*" not in RuntimeConfig().cors_origins)
    check("Runtime DB ignored by Git policy", "*.db" in (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8"))
    print("TEST SUMMARY: 15/15 PASS")

if __name__ == "__main__": main()
