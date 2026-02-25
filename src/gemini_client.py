import os
import json
from google import genai
from google.genai import types
from .models import Grant, Classification, ScreeningResult
from .serp_searcher import search_foundation


CONFIG_FILE = "screener_config.json"


class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.client     = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"
        self.cfg        = self._load_config()

    # ── Config loading ────────────────────────────────────────────────────

    @staticmethod
    def _load_config() -> dict:
        """Load screener_config.json if present; fall back to .env values."""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        # Legacy fallback — .env-based config
        return {
            "org": {
                "name":          os.getenv("ORG_NAME", "Our Nonprofit"),
                "mission":       os.getenv("ORG_MISSION", "providing STEM education to underserved youth"),
                "state":         os.getenv("ORG_STATE", "NJ"),
                "target_cities": os.getenv("ORG_TARGET_CITIES", "local cities"),
            },
            "grant_size":      {"min": 0, "max": 0},
            "green_threshold": 4,
            "red_flags": [
                'R1a. Status explicitly says "not accepting applications" or "permanently closed" → Hard RED.',
                'R1b. Status says "invitation only" → Soft flag.',
                "R2.  Only funds a state that is not " + os.getenv("ORG_STATE", "NJ"),
                "R3.  Zero " + os.getenv("ORG_STATE", "NJ") + " grantees found",
                "R4.  Only funds colleges/hospitals/adults — no K-12 or youth",
                "R5.  Mission contradicts actual grant focus",
                "R6.  Only Environment, Animals, or Health — no education",
                "R7.  Max grant < $2,500 or min grant > $100,000",
                "R8.  Last grant awarded more than 2 years ago",
            ],
            "green_flags": [
                "G1.  Mission mentions STEM, coding, robotics, or girls in STEM",
                "G2.  Past grantees include STEM programs or coding orgs",
                "G3.  Based in or funds " + os.getenv("ORG_STATE", "NJ"),
                "G4.  Past grants in " + os.getenv("ORG_TARGET_CITIES", "local cities"),
                "G5.  Age group: middle school, grades 6-8, youth, or K-12",
                "G6.  Equity: underserved, low-income, or Title I",
                "G7.  Typical grant $5,000–$50,000",
                "G8.  Grants awarded in the last 12 months",
            ],
            "custom_context": "",
        }

    def _build_prompt(self, grant: Grant, serp_section: str) -> str:
        """Build the chain-of-thought screening prompt from loaded config."""
        cfg  = self.cfg
        org  = cfg["org"]
        size = cfg["grant_size"]
        threshold = cfg.get("green_threshold", 4)
        custom    = cfg.get("custom_context", "")

        red_flags_text   = "\n        ".join(cfg["red_flags"])
        green_flags_text = "\n        ".join(cfg["green_flags"])
        n_green = len(cfg["green_flags"])

        size_rule = (
            f"R-size. Grant size outside ${size['min']:,}–${size['max']:,}"
            if size["min"] or size["max"] else ""
        )

        return f"""
        You are an expert Grant Screener for {org['name']}, a nonprofit {org['mission']}.
        {('Additional context: ' + custom) if custom else ''}

        ══════════════════════════════════════════
        GRANT TO SCREEN
        ══════════════════════════════════════════
        Foundation : {grant.foundation_name}
        Org Name   : {grant.name}
        Website    : {grant.website if grant.website else 'N/A'}
        Amount     : {grant.amount}

        {serp_section}

        ══════════════════════════════════════════
        STEP 1 — CHECK RED FLAGS
        ══════════════════════════════════════════
        Go through each flag. Mark YES if found, NO if not:
        {red_flags_text}
        {size_rule}

        Rules:
        → R1a triggered → RED (hard, no workaround)
        → R1b triggered (invite-only) + any green flags → YELLOW (Inquiry Required)
        → R1b triggered + zero green flags → RED
        → Any other red flag → RED

        ══════════════════════════════════════════
        STEP 2 — COUNT GREEN FLAGS (if no hard red flags)
        ══════════════════════════════════════════
        Evaluate with YES / NO / UNCLEAR and cite evidence:
        {green_flags_text}

        Count YES only. UNCLEAR = NO.

        ══════════════════════════════════════════
        STEP 3 — CLASSIFY
        ══════════════════════════════════════════
        Decision rule (strict):
        • RED    → any hard red flag (R1a or R2+)
        • YELLOW → R1b (invite-only) + green >= 1
                   OR 0 red flags AND green_count < {threshold}
        • GREEN  → 0 red flags AND green_count >= {threshold}

        Rationale must include:
        - Which R-flags triggered (or "None")
        - Green flag count: "Green flags: X/{n_green} (G1✓ G2✓...)"
        - One plain-English sentence of context

        ══════════════════════════════════════════
        OUTPUT — ONLY this JSON:
        ══════════════════════════════════════════
        {{
            "classification": "RED" | "YELLOW" | "GREEN",
            "rationale": "Red flags: <list or None>. Green flags: <X>/{n_green} (<which>). <sentence>",
            "confidence": 0.0 to 1.0,
            "next_application_date": "YYYY-MM-DD" or null
        }}
        """

    def screen_grant(self, grant: Grant) -> ScreeningResult:
        """
        Screen a grant using SerpAPI + Gemini with Google Search grounding.
        Prompt is built dynamically from screener_config.json (or .env fallback).
        """
        # ── Step 1: SerpAPI targeted search ─────────────────────────────────
        serp_context = ""
        serp_sources = []
        try:
            print(f"  [SerpAPI] Searching priority sources...")
            serp_results = search_foundation(
                foundation_name=grant.foundation_name,
                website=grant.website,
            )

            # Build source list from SerpAPI hits
            for source_key in ("propublica", "granted", "candid", "causeiq", "general"):
                for r in serp_results.get(source_key, []):
                    if r.get("link"):
                        domain = r["link"].replace("https://", "").replace("http://", "").split("/")[0]
                        serp_sources.append(f"{domain} ({r['link']})")

            serp_context = serp_results.get("summary", "")
        except Exception as e:
            print(f"  [SerpAPI] Warning: {e}. Falling back to Gemini search only.")

        # ── Step 2: Build prompt with pre-fetched context ────────────────────
        serp_section = (
            f"""
        PRE-FETCHED SEARCH RESULTS (from ProPublica & Granted - highest priority):
        ---
        {serp_context}
        ---
        Use the above as your PRIMARY evidence. Supplement with your own Google Search 
        ONLY if the above results are insufficient.
        """
            if serp_context and serp_context != "No results found."
            else "No priority-source results found. Use your Google Search tool to research."
        )

        prompt = self._build_prompt(grant, serp_section)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0,  # deterministic - same input = same output
                )
            )

            text_response = response.text

            # Robust JSON extraction
            try:
                start_index = text_response.find('{')
                end_index   = text_response.rfind('}')
                if start_index != -1 and end_index != -1 and end_index > start_index:
                    json_str = text_response[start_index:end_index + 1]
                    data = json.loads(json_str)
                else:
                    raise ValueError("No JSON object found in response")
            except Exception as e:
                print(f"  JSON Parse Error: {e}. Raw: {text_response[:120]}...")
                data = {"classification": "YELLOW", "rationale": text_response[:500], "confidence": 0.0}

            classification_str = data.get("classification", "YELLOW").upper()
            try:
                classification = Classification[classification_str]
            except KeyError:
                classification = Classification.YELLOW

            # Merge: SerpAPI sources first (priority), Gemini fills remaining slots up to 5 total
            sources = list(dict.fromkeys(serp_sources))   # deduplicate SerpAPI sources
            gemini_slots = max(1, 5 - len(sources))       # at least 1, fill to reach 5
            if response.candidates and response.candidates[0].grounding_metadata:
                gm = response.candidates[0].grounding_metadata
                if hasattr(gm, "grounding_chunks") and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks[:gemini_slots]:
                        if hasattr(chunk, "web") and chunk.web:
                            src = f"{chunk.web.title} ({chunk.web.uri})"
                            if src not in sources:
                                sources.append(src)

            return ScreeningResult(
                grant=grant,
                classification=classification,
                rationale=data.get("rationale", "No rationale provided."),
                confidence_score=data.get("confidence", 0.0),
                sources=sources,
            )

        except Exception as e:
            print(f"  Error screening {grant.foundation_name}: {e}")
            return ScreeningResult(
                grant=grant,
                classification=Classification.YELLOW,
                rationale=f"Error during screening: {e}",
                confidence_score=0.0,
                sources=serp_sources,
            )
