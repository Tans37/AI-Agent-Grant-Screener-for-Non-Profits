"""
update_config.py
----------------
Update specific sections of your screener config without re-running the full wizard.
Run: python update_config.py

Options:
  --org        Re-configure organization details
  --rules      Re-generate red/green flag rules
  --size       Update grant size range
  --threshold  Update the green flag threshold (how many = GREEN)
  --show       Display current config
  --full       Re-run the full setup wizard
"""

import os, sys, json, textwrap, argparse
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

CONFIG_FILE = "screener_config.json"


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"No config found. Run  python setup_wizard.py  first.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Config saved to {CONFIG_FILE}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"\n{prompt}{suffix}\n> ").strip()
    return val if val else default


def show_config(config: dict):
    print("\nCurrent Configuration:")
    print(f"  Org    : {config['org']['name']} — {config['org']['mission']}")
    print(f"  State  : {config['org']['state']} | Cities: {config['org'].get('target_cities', 'N/A')}")
    print(f"  Size   : ${config['grant_size']['min']:,} – ${config['grant_size']['max']:,}")
    print(f"  Green threshold: {config['green_threshold']} flags needed for GREEN")
    print(f"\n  Red Flags ({len(config['red_flags'])}):")
    for r in config["red_flags"]:
        print(f"    • {r}")
    print(f"\n  Green Flags ({len(config['green_flags'])}):")
    for g in config["green_flags"]:
        print(f"    • {g}")


def update_org(config: dict) -> dict:
    print("\n── Update Organization Details ──")
    org = config["org"]
    org["name"]          = ask("Org name", org["name"])
    org["mission"]       = ask("Mission (one sentence)", org["mission"])
    org["state"]         = ask("State/region", org["state"])
    org["target_cities"] = ask("Target cities (comma-separated)", org.get("target_cities", ""))
    config["org"] = org
    return config


def update_size(config: dict) -> dict:
    print("\n── Update Grant Size Range ──")
    config["grant_size"]["min"] = int(ask("Minimum grant size ($)", str(config["grant_size"]["min"])))
    config["grant_size"]["max"] = int(ask("Maximum grant size ($)", str(config["grant_size"]["max"])))
    return config


def update_threshold(config: dict) -> dict:
    print("\n── Update Green Flag Threshold ──")
    print(f"  Current: {config['green_threshold']} green flags needed to classify as GREEN")
    config["green_threshold"] = int(ask("New threshold (recommended: 3-5)", str(config["green_threshold"])))
    return config


def update_rules_with_llm(config: dict) -> dict:
    """Re-generate red/green flags using Gemini based on new freeform input."""
    from google import genai
    from google.genai import types

    print("\n── Update Screening Rules ──")
    print("Describe what should disqualify or qualify a grant. The AI will update your rules.")

    red_input   = ask("What should DISQUALIFY a grant? (describe in plain language)")
    green_input = ask("What should make a grant a GREAT fit? (describe in plain language)")

    api_key = os.getenv("GEMINI_API_KEY")
    client  = genai.Client(api_key=api_key)

    prompt = f"""
You are a grant screening configuration builder.
The user wants to update the red and green flag rules for their org: {config['org']['name']}.

Their org mission: {config['org']['mission']}
State: {config['org']['state']}

New disqualifiers (user input): {red_input}
New positive signals (user input): {green_input}

Current red flags: {json.dumps(config['red_flags'])}
Current green flags: {json.dumps(config['green_flags'])}

Generate UPDATED red_flags and green_flags lists.
Always keep R1a (permanently closed → hard RED) and R1b (invitation only → soft flag) as first two red flags.
Incorporate the user's new input. Keep any existing rules that still make sense.

Output ONLY valid JSON:
{{
  "red_flags": ["R1a. ...", "R1b. ...", "R2. ...", ...],
  "green_flags": ["G1. ...", "G2. ...", ...]
}}
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )

    text = response.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    updated = json.loads(text)
    config["red_flags"]   = updated["red_flags"]
    config["green_flags"] = updated["green_flags"]
    return config


def main():
    parser = argparse.ArgumentParser(description="Update your grant screener configuration.")
    parser.add_argument("--org",       action="store_true", help="Update org details")
    parser.add_argument("--rules",     action="store_true", help="Re-generate red/green flag rules")
    parser.add_argument("--size",      action="store_true", help="Update grant size range")
    parser.add_argument("--threshold", action="store_true", help="Update green flag threshold")
    parser.add_argument("--show",      action="store_true", help="Show current config")
    parser.add_argument("--full",      action="store_true", help="Re-run the full setup wizard")
    args = parser.parse_args()

    if args.full:
        import subprocess
        subprocess.run([sys.executable, "setup_wizard.py"])
        return

    config = load_config()

    if args.show or not any(vars(args).values()):
        show_config(config)
        return

    if args.org:
        config = update_org(config)
    if args.size:
        config = update_size(config)
    if args.threshold:
        config = update_threshold(config)
    if args.rules:
        config = update_rules_with_llm(config)

    save_config(config)
    print("\nUpdated config:")
    show_config(config)


if __name__ == "__main__":
    main()
