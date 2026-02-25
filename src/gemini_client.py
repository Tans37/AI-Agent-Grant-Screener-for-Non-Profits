import os
import json
from google import genai
from google.genai import types
from .models import Grant, Classification, ScreeningResult
from .serp_searcher import search_foundation


class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"

    def screen_grant(self, grant: Grant) -> ScreeningResult:
        """
        Screen a grant using SerpAPI + Gemini with Google Search grounding.
        Org context is read from .env (ORG_NAME, ORG_MISSION, ORG_STATE, ORG_TARGET_CITIES).
        """
        # Org context — configure in .env
        org_name     = os.getenv("ORG_NAME", "Our Nonprofit")
        org_mission  = os.getenv("ORG_MISSION", "providing STEM education to underserved youth")
        org_state    = os.getenv("ORG_STATE", "NJ")
        org_cities   = os.getenv("ORG_TARGET_CITIES", "local cities")

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

        prompt = f"""
        You are an expert Grant Screener for {org_name}, a nonprofit {org_mission}.

        ══════════════════════════════════════════
        GRANT TO SCREEN
        ══════════════════════════════════════════
        Foundation : {grant.foundation_name}
        Org Name   : {grant.name}
        Website    : {grant.website if grant.website else "N/A"}
        Amount     : {grant.amount}

        {serp_section}

        ══════════════════════════════════════════
        STEP 1 — CHECK RED FLAGS (stop immediately if any are true)
        ══════════════════════════════════════════
        Go through each flag. Mark YES if found, NO if not:
        R1a. Status explicitly says "not accepting applications" or "permanently closed"
             → Hard RED — no workaround.
        R1b. Status says "invitation only" or "by invitation to preselected organizations only"
             → Soft flag — see STEP 3 for how to handle.
        R2.  Explicit geography block — only funds a specific state that is NOT NJ
        R3.  Zero NJ grantees found anywhere in search results
        R4.  Focus is ONLY colleges/grad schools/hospitals/adults — NO K-12 or youth
        R5.  Stated mission (e.g. Education) contradicts actual grants (e.g. Religious/Health)
        R6.  Cause area is Environment, Animals, or Health ONLY — zero education focus
        R7.  Max grant < $2,500 OR minimum grant > $100,000
        R8.  Last grant awarded more than 2 years ago

        ══════════════════════════════════════════
        STEP 2 — COUNT GREEN FLAGS (only if no hard red flags)
        ══════════════════════════════════════════
        Evaluate each green flag with a YES / NO / UNCLEAR and cite your evidence:
        G1. Mission mentions STEM, technology education, coding, robotics, or girls in STEM
        G2. Past grantees (if any) include STEM programs, Girls Who Code, robotics clubs, or coding orgs
        G3. Foundation is based in NJ OR explicitly states it funds NJ nonprofits
        G4. Past grants awarded in Newark, Camden, Jersey City, Elizabeth, or any NJ location
        G5. Age group: schools, middle school, grades 6-8, youth, or K-12
        G6. Equity focus: underserved, low-income, Title I, or marginalized communities
        G7. Typical grant size is $5,000 - $50,000
        G8. Grants awarded within the last 12 months (active grantmaker)

        Count YES answers only. UNCLEAR = NO.

        ══════════════════════════════════════════
        STEP 3 — CLASSIFY
        ══════════════════════════════════════════
        Decision rule (strict — do not deviate):
        • RED    → R1a triggered (permanently closed / not accepting)
                   OR any of R2–R8 triggered
                   OR R1b triggered AND green_count = 0 (invite-only but zero alignment)
        • YELLOW → R1b triggered (invitation-only/preselected) AND green_count >= 1
                   → rationale must say: "Inquiry Required — invitation-only, JerseySTEM should reach out."
                   OR 0 red flags AND green_count <= 3
        • GREEN  → 0 red flags AND green_count >= 4

        Rationale must include:
        - Which R-flags were found (or "None")
        - Exact green flag count: "Green flags: X/8 (G1✓ G3✓ G5✓ ...)"
        - One sentence of context

        ══════════════════════════════════════════
        OUTPUT — respond with ONLY this JSON:
        ══════════════════════════════════════════
        {{
            "classification": "RED" | "YELLOW" | "GREEN",
            "rationale": "Red flags: <list or None>. Green flags: <X>/10 (<which ones>). <context sentence>",
            "confidence": 0.0 to 1.0,
            "next_application_date": "YYYY-MM-DD" or null
        }}
        """

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
