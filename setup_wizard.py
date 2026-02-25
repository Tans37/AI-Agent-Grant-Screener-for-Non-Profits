"""
setup_wizard.py
---------------
One-time interactive CLI setup for the AI Grant Screener.
Asks the user about their org and grant criteria, then uses Gemini to
convert their answers into a structured chain-of-thought screening prompt.
Saves everything to screener_config.json.

Run: python setup_wizard.py
"""

import os, json, sys, textwrap
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

CONFIG_FILE = "screener_config.json"

# ── Helpers ────────────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    """Print a prompt and return user input (stripped)."""
    suffix = f" [{default}]" if default else ""
    response = input(f"\n{prompt}{suffix}\n> ").strip()
    return response if response else default


def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def build_config_with_llm(answers: dict) -> dict:
    """Send user answers to Gemini and get back a structured config."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are a grant screening configuration builder.

A user has described their nonprofit and grant screening requirements below.
Your job is to convert their answers into a structured JSON configuration
that will be used to build a chain-of-thought grant screening prompt.

USER ANSWERS:
{json.dumps(answers, indent=2)}

OUTPUT a valid JSON object with this exact structure:
{{
  "org": {{
    "name": "...",
    "mission": "...",
    "state": "...",
    "target_cities": "..."
  }},
  "grant_size": {{
    "min": 0,
    "max": 0
  }},
  "red_flags": [
    "R1a. <hard disqualifier: not accepting / permanently closed>",
    "R1b. <soft flag: invitation-only>",
    "R2. <another disqualifier from user input>",
    "..."
  ],
  "green_flags": [
    "G1. <positive signal from user input>",
    "G2. <another positive signal>",
    "..."
  ],
  "green_threshold": 4,
  "classification_rules": {{
    "red": [
      "R1a triggered (foundation closed/not accepting)",
      "Any of R2+ triggered",
      "<any extra RED conditions from user>"
    ],
    "yellow": [
      "R1b triggered (invite-only) AND green_count >= 1 — worth reaching out",
      "0 red flags AND green_count < threshold",
      "<any user-defined YELLOW conditions>"
    ],
    "green": [
      "0 red flags AND green_count >= threshold"
    ]
  }},
  "custom_context": "One sentence of additional context about this org's needs"
}}

Rules:
- Always include R1a (closed/not accepting → hard RED) and R1b (invitation only → soft flag) as first two red flags.
- Generate 4–8 red flags (R2+) from the user's disqualifiers.
- Generate 6–10 green flags (G1+) from the user's positive signals.
- Use the user's green_threshold_raw value for green_threshold (convert to int, default 4).
- Use user's yellow_conditions to populate the yellow classification_rules list.
- Use user's extra_red_raw to add extra entries to the red classification_rules list.
- Output ONLY the JSON, no extra text.
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )

    text = response.text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().rstrip("```").strip()

    return json.loads(text)


# ── Wizard questions ────────────────────────────────────────────────────────

def run_wizard() -> dict:
    print("\n" + "=" * 55)
    print("  AI Grant Screener — Setup Wizard")
    print("=" * 55)
    print(textwrap.dedent("""
    Welcome! Answer a few questions about your organization and
    what you're looking for in grants. The AI will turn your
    answers into a smart screening prompt.

    Press Enter to skip any question.
    """))

    section("1 / 4  —  Your Organization")
    org_name    = ask("What is your organization's name?")
    org_mission = ask("In one sentence, what does your org do? (e.g. 'providing coding education to underserved high school girls')")
    org_state   = ask("What state/region are you based in or primarily serve? (e.g. 'NJ', 'Texas', 'Greater Boston')")
    org_cities  = ask("List your key target cities or counties (comma-separated, or press Enter to skip)")

    section("2 / 4  —  Grant Requirements")
    grant_focus  = ask("What type of funding are you looking for? (e.g. 'STEM education', 'workforce development', 'arts programs')")
    grant_min    = ask("Minimum grant size you'd consider? (e.g. 5000)", "0")
    grant_max    = ask("Maximum grant size? (e.g. 50000)", "0")
    target_group = ask("Who do you serve? (e.g. 'middle school students', 'adult immigrants', 'veterans')")
    equity_focus = ask("Any equity / demographic focus? (e.g. 'low-income', 'girls', 'Title I schools', or press Enter to skip)")

    section("3 / 4  —  Red Flags (Instant Disqualifiers)")
    red_input = ask(
        "What would immediately rule out a grant for you?\n"
        "  (e.g. 'only funds colleges', 'no NJ orgs', 'health/environment focus only', 'inactive 2+ years')\n"
        "  Describe in your own words — separate multiple with commas"
    )

    section("4 / 5  —  Green Flags (Strong Positive Signals)")
    green_input = ask(
        "What makes a grant a great fit?\n"
        "  (e.g. 'mentions Girls Who Code or robotics', 'past grants in Newark', 'simple online application', 'active last 12 months')\n"
        "  Describe in your own words — separate multiple with commas"
    )

    section("5 / 5  —  Classification Rules")
    print("  You keep GREEN / YELLOW / RED as the three classes.")
    print("  Now define what each should mean for your org:\n")
    yellow_input = ask(
        "What situations should be YELLOW instead of RED?\n"
        "  (e.g. 'invite-only but aligns with our mission', 'low confidence result', 'deadline unknown')\n"
        "  YELLOW means: worth a manual look or outreach"
    )
    red_input_extra = ask(
        "Any extra conditions that should ALWAYS be RED?\n"
        "  (beyond the disqualifiers you already listed — e.g. 'grant size under $1,000', 'no online application')\n"
        "  Press Enter to skip"
    )
    green_threshold_input = ask(
        "How many green flags should a grant need to be classified GREEN? (default: 4)", "4"
    )

    return {
        "org_name":            org_name,
        "org_mission":         org_mission,
        "org_state":           org_state,
        "org_cities":          org_cities,
        "grant_focus":         grant_focus,
        "grant_min":           grant_min,
        "grant_max":           grant_max,
        "target_group":        target_group,
        "equity_focus":        equity_focus,
        "red_flags_raw":       red_input,
        "green_flags_raw":     green_input,
        "yellow_conditions":   yellow_input,
        "extra_red_raw":       red_input_extra,
        "green_threshold_raw": green_threshold_input,
    }


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    answers = run_wizard()

    print("\n\nGenerating your screening configuration with AI...")
    try:
        config = build_config_with_llm(answers)
    except json.JSONDecodeError as e:
        print(f"Error parsing AI response: {e}")
        sys.exit(1)

    # Save to file
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"\n✓ Configuration saved to {CONFIG_FILE}")
    print("\nHere's a preview of your screening rules:\n")

    print(f"  Org    : {config['org']['name']} — {config['org']['mission']}")
    print(f"  State  : {config['org']['state']} | Cities: {config['org']['target_cities'] or 'N/A'}")
    print(f"  Size   : ${config['grant_size']['min']:,} – ${config['grant_size']['max']:,}")
    print(f"\n  Red Flags ({len(config['red_flags'])}):")
    for r in config["red_flags"]:
        print(f"    • {r}")
    print(f"\n  Green Flags ({len(config['green_flags'])}) — threshold: {config['green_threshold']}+:")
    for g in config["green_flags"]:
        print(f"    • {g}")

    print(f"\nRun  python main.py  to start screening grants.")


if __name__ == "__main__":
    main()
