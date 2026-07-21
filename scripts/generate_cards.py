#!/usr/bin/env python3
"""Generate 3 new Neuroitch cards with the Claude API and append to cards.json.

Runs inside GitHub Actions. Never writes a pack that fails validation.
"""
import json
import os
import random
import re
import sys
import urllib.request

CARDS_PATH = "cards.json"
MODEL = os.environ.get("MODEL", "claude-sonnet-5")
API_KEY = os.environ["ANTHROPIC_API_KEY"]

DOMAINS = [
    # formal + natural sciences
    "mathematics", "probability", "statistics", "topology", "number theory",
    "physics", "thermodynamics", "quantum mechanics", "fluid dynamics",
    "chemistry", "biology", "evolutionary biology", "genetics", "ecology",
    "immunology", "neuroscience", "epidemiology", "mycology", "botany",
    "astronomy", "geology", "seismology", "materials science", "metallurgy",
    # mind + behaviour
    "psychology", "cognitive science", "behavioural economics", "psychoanalysis",
    "developmental psychology", "social psychology", "decision theory",
    "perception", "memory", "emotion", "habit formation",
    # society + humanities
    "anthropology", "sociology", "economics", "game theory", "auction theory",
    "law", "political theory", "history", "archaeology", "linguistics",
    "philosophy", "ethics", "logic", "rhetoric", "theology", "religion",
    # myth, story, culture
    "mythology", "folklore", "comparative mythology", "storytelling",
    "narrative theory", "poetry", "drama", "comedy", "fairy tales",
    "ritual", "symbolism", "iconography",
    # arts + craft
    "music theory", "harmony", "rhythm", "architecture", "typography",
    "painting", "sculpture", "dance", "cinema", "photography", "cooking",
    "fermentation", "textiles", "ceramics", "woodworking", "perfumery",
    "origami mathematics", "calligraphy",
    # systems + making
    "engineering", "control theory", "information theory", "signal processing",
    "cryptography", "queueing theory", "logistics", "supply chains",
    "urban planning", "cartography", "networks", "computer science",
    "systems thinking", "cybernetics",
    # human skills + practices
    "negotiation", "leadership", "teaching", "coaching", "improvisation",
    "chess theory", "poker strategy", "martial arts", "sailing", "gardening",
    "medicine", "surgery", "nursing", "firefighting", "diplomacy",
    "journalism", "advertising", "sales", "accounting", "meditation",
    # ways of thinking (methods, not just subjects)
    "first-principles reasoning", "analogy", "abstraction", "forecasting",
    "experimentation", "modelling", "heuristics", "counterfactual reasoning",
]

LENS_FAMILY = {
    "isomorphism": "structural", "homology": "structural",
    "structural_mapping": "structural", "abstraction": "structural",
    "transfer_learning": "structural", "inversion": "transformative",
    "constraint_removal": "transformative", "scale_shift": "transformative",
    "time_shift": "transformative", "perspective_shift": "transformative",
    "contrast": "dialectical", "paradox": "dialectical",
    "dialectic": "dialectical", "irony": "dialectical",
    "counterfactual": "generative", "thought_experiment": "generative",
    "first_principles": "generative",
}

PERSONA_BRIEF = {
    "student": "a university student juggling lectures, deadlines and part-time work",
    "founder": "a startup founder worrying about runway, hiring and product",
    "healthcare": "a nurse or doctor working long clinical shifts on a busy ward",
    "teacher": "a schoolteacher managing a classroom, marking and lesson plans",
    "parent": "a busy parent running a household and raising young children",
    "engineer": "a software engineer shipping code, on-call rotas and reviews",
}

FIELDS_17 = [
    "id", "fieldA", "fieldB", "title", "hook", "connection", "mechanism",
    "mentalModel", "realWorld", "historical", "business", "personal",
    "openQuestion", "reading", "tags", "difficulty", "readMinutes",
]


def validate(cards):
    errs = []
    ids = [c.get("id") for c in cards]
    if len(set(ids)) != len(ids):
        errs.append("duplicate ids")
    pairs = {}
    for c in cards:
        for k in FIELDS_17:
            if k not in c:
                errs.append(f"{c.get('id')}: missing {k}")
        for k in ["id", "fieldA", "fieldB", "title", "hook", "connection",
                  "mechanism", "mentalModel", "realWorld", "historical",
                  "business", "personal", "openQuestion"]:
            v = c.get(k)
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{c.get('id')}: bad {k}")
        for k in ["connection", "mechanism"]:
            if len(c.get(k, "")) <= 60:
                errs.append(f"{c.get('id')}: {k} too short")
        for k in ["reading", "tags"]:
            v = c.get(k)
            if not isinstance(v, list) or not v or not all(
                    isinstance(x, str) and x.strip() for x in v):
                errs.append(f"{c.get('id')}: bad {k}")
        if not isinstance(c.get("difficulty"), int) or not 1 <= c["difficulty"] <= 3:
            errs.append(f"{c.get('id')}: difficulty")
        if not isinstance(c.get("readMinutes"), int) or not 1 <= c["readMinutes"] <= 20:
            errs.append(f"{c.get('id')}: readMinutes")
        if c.get("fieldA") == c.get("fieldB"):
            errs.append(f"{c.get('id')}: fieldA == fieldB")
        if "fields" in c:
            fl = c["fields"]
            if (not isinstance(fl, list) or len(fl) < 2
                    or len(set(fl)) != len(fl)
                    or not all(isinstance(x, str) and x.strip() for x in fl)
                    or c.get("fieldA") not in fl or c.get("fieldB") not in fl):
                errs.append(f"{c.get('id')}: bad fields list")
        key = "|".join(sorted([str(c.get("fieldA")), str(c.get("fieldB"))]))
        pairs[key] = pairs.get(key, 0) + 1
    for p, n in pairs.items():
        if n > 3:
            errs.append(f"pair overused: {p} x{n}")
    return errs


def validate_lens(cards):
    """Lens dimension checks, applied to the whole pack."""
    errs = []
    lens_counts = {}
    for c in cards:
        lens = c.get("lens")
        if lens not in LENS_FAMILY:
            errs.append(f"{c.get('id')}: invalid lens {lens!r}")
            continue
        if c.get("lensFamily") != LENS_FAMILY[lens]:
            errs.append(f"{c.get('id')}: lensFamily mismatch")
        for k in ("whereItFails", "whereElse", "opposite", "plainly"):
            v = c.get(k, "")
            if not isinstance(v, str) or len(v) <= 60:
                errs.append(f"{c.get('id')}: {k} too short")
        ex = c.get("example", "")
        if not isinstance(ex, str) or len(ex) <= 80:
            errs.append(f"{c.get('id')}: example too short")
        if "relation" not in c or not isinstance(c["relation"], str):
            errs.append(f"{c.get('id')}: relation missing")
        lens_counts[lens] = lens_counts.get(lens, 0) + 1
    total = len(cards)
    for lens, n in lens_counts.items():
        if total and n / total > 0.40:
            errs.append(f"lens {lens} exceeds 40% ({n}/{total})")
    return errs


def _post(body):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def call_claude(prompt):
    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": MODEL,
        "max_tokens": 16000,
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 6,
        }],
        "messages": messages,
    }
    res = _post(body)
    # Server-side web search can pause the turn; continue until finished.
    rounds = 0
    while res.get("stop_reason") == "pause_turn" and rounds < 6:
        messages.append({"role": "assistant", "content": res["content"]})
        body["messages"] = messages
        res = _post(body)
        rounds += 1
    print("stop_reason:", res.get("stop_reason"), "| rounds:", rounds + 1)
    texts = [b.get("text", "") for b in res.get("content", [])
             if b.get("type") == "text"]
    return "\n".join(texts)


def extract_json_array(text):
    fenced = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    candidates = fenced if fenced else []
    if not candidates:
        start = text.find("[")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:i + 1])
                        break
    for c in reversed(candidates):
        try:
            arr = json.loads(c)
            if isinstance(arr, list) and 1 <= len(arr) <= 5:
                return arr
        except json.JSONDecodeError:
            continue
    return None


def parse_brew(title):
    body = re.sub(r"^\s*brew\s*:\s*", "", title, flags=re.I)
    parts = [p.strip() for p in re.split(r"\s*[×+,|]\s*|\s+x\s+", body) if p.strip()]
    if not 2 <= len(parts) <= 8:
        sys.exit(f"brew needs 2-8 fields, got {parts!r}")
    return parts


def main():
    brew = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--brew":
        brew = parse_brew(sys.argv[2])
        print("BREW REQUEST:", brew)
    pack = json.load(open(CARDS_PATH, encoding="utf-8"))
    cards = pack["cards"]
    ids = [c["id"] for c in cards]
    titles = [c["title"] for c in cards]
    pair_counts = {}
    for c in cards:
        k = "|".join(sorted([c["fieldA"], c["fieldB"]]))
        pair_counts[k] = pair_counts.get(k, 0) + 1
    full_pairs = sorted(k for k, n in pair_counts.items() if n >= 3)
    lens_counts = {}
    for c in cards:
        if c.get("lens"):
            lens_counts[c["lens"]] = lens_counts.get(c["lens"], 0) + 1
    near_cap = sorted(l for l, n in lens_counts.items()
                      if (len(cards) and n / len(cards) > 0.33))
    rare = sorted(l for l in LENS_FAMILY if lens_counts.get(l, 0) <= 1)
    sample = json.dumps(cards[-2:], indent=2, ensure_ascii=False)
    seeds = random.sample(DOMAINS, 4)

    prompt = f"""You write idea cards for Neuroitch, an app of structural
analogies between unrelated fields of human knowledge. Each card claims two
fields are the same thing underneath and backs it with the actual mechanism.

Use web search to research REAL published cross-disciplinary mechanisms,
isomorphisms or shared mathematics. Verify the mechanism is accurate and cite
2-3 real books or papers (format "Title - Author") in the reading list. Never
invent citations. Start your exploration from some of these seed domains (or adjacent ones):
{', '.join(seeds)}. Roam the WHOLE of human knowledge, not just the sciences:
psychology, mythology, storytelling, ritual, philosophy, the arts, crafts,
and human skills (negotiation, sailing, cooking, chess) are as welcome as
physics. Mix a FIELD with a SKILL, or a myth with a mechanism, not only two
academic subjects.

Style reference - the two most recent cards:
{sample}

Write 3 new cards as a JSON array - a POLLINATION LADDER:
- Card 1 bridges exactly 2 fields.
- Card 2 braids exactly 3 fields into one mechanism.
- Card 3 fuses 4-6 fields around a single deep structural pattern.
Every card carries an extra key "fields": the ordered list of ALL fields it
braids (2, 3, and 4-6 entries respectively). fieldA and fieldB must be the two
most central fields and both must appear in "fields". For 3+ field cards the
title must name the chain (e.g. "X, Y and Z share one clock"), and the
connection and mechanism must genuinely use EVERY field - a field that only
appears as a name-drop is a failure. Include every field (lowercased) in tags. Schema per card (all 17 keys
required): id (new unique kebab-case slug), fieldA, fieldB (different, short
field names), title, hook (one arresting sentence), connection (200-400 chars:
why the fields are the same underneath), mechanism (200-400 chars: the actual
math/algorithm/causal machinery, rigorous), mentalModel, realWorld, historical,
business, personal (each a concrete non-empty paragraph), openQuestion
(genuinely open), reading (2-3 real "Title - Author" strings), tags (3-5
lowercase strings), difficulty (int 1-3, vary across the 3 cards),
readMinutes (int 2-8).

THE THINKING LENS (required on every card): the card must also declare the
cognitive move it performs, not just its subject.
- "lens": one of these snake_case values, and "lensFamily" its family:
  STRUCTURAL: isomorphism (same mathematical structure), homology (shared
  ancestry / common origin), structural_mapping (same relationships between
  different objects, e.g. predator:prey :: hacker:network), abstraction,
  transfer_learning.
  TRANSFORMATIVE: inversion, constraint_removal, scale_shift, time_shift,
  perspective_shift.
  DIALECTICAL: contrast, paradox, dialectic, irony.
  GENERATIVE: counterfactual, thought_experiment, first_principles.
  Do NOT default everything to isomorphism. Isomorphism means the SAME maths;
  if the claim is shared ancestry it is homology; if it maps relationships
  between different objects it is structural_mapping. Judge honestly.
- "relation": the relational skeleton like "predator : prey :: hacker :
  network" when the card has one, else an empty string "".
- "whereItFails": REQUIRED, over 60 chars. The specific boundary where the
  mapping genuinely breaks down. Not a hedge. A real divergence point.
- "whereElse": REQUIRED, over 60 chars. Two or three other domains the same
  pattern appears in.
- "opposite": REQUIRED, over 60 chars. The inversion of the core claim and
  what it would imply if true.
- "plainly": REQUIRED, over 60 chars. A plain-English explanation a curious
  non-expert would instantly get, with zero jargon. Use everyday images and
  a relatable comparison. This is the first thing the reader meets, so make
  it land. Do not restate the title; explain the idea like you would to a
  friend who knows nothing about either field.
- "example": REQUIRED, over 80 chars. A concrete everyday scene the reader
  can picture themselves in that makes the idea click. Start with something
  like "Picture..." or "Imagine..." or "You...". Not another abstract
  statement, an actual little story from ordinary life (a shop, a commute,
  a family, a team) that demonstrates the pattern in action.
- "personaExamples": REQUIRED object. For EACH of these keys, write the same
  idea's example rewritten for that person's world (each over 60 chars, a
  concrete scene from their life): student (a university student juggling lectures, deadlines and part-time work); founder (a startup founder worrying about runway, hiring and product); healthcare (a nurse or doctor working long clinical shifts on a busy ward); teacher (a schoolteacher managing a classroom, marking and lesson plans); parent (a busy parent running a household and raising young children); engineer (a software engineer shipping code, on-call rotas and reviews)
Prefer these under-used lenses this run if you can do so honestly: {rare}.
Avoid over-using these already-common lenses: {near_cap}.

HARD CONSTRAINTS:
- Do not reuse any of these ids: {json.dumps(ids)}
- Do not rehash any of these existing titles/topics: {json.dumps(titles)}
- These field pairs are FULL - do not use them again: {json.dumps(full_pairs)}
- Prefer field pairs never used before.

Reply with ONLY the JSON array in a ```json fenced block."""

    if brew:
        prompt = prompt + f"""

OVERRIDE FOR THIS RUN: a reader has requested ONE custom card. Write a JSON
array containing EXACTLY 1 card that braids EXACTLY these fields (its "fields"
key must contain exactly this set, any sensible order/casing):
{json.dumps(brew)}
Research the genuine structural mechanism connecting them. The pollination
ladder instruction above does not apply. All other schema rules apply."""

    last_err = "?"
    for attempt in range(3):
        text = call_claude(prompt if attempt == 0 else prompt +
                           "\n\nYour previous output failed validation: " +
                           last_err + "\nFix and resend the full array.")
        new_cards = extract_json_array(text)
        if new_cards is None:
            last_err = "output was not a parseable JSON array of cards"
            print("PARSE FAIL. response head:", text[:600].replace("\n", " "),
                  file=sys.stderr)
            continue
        errs = validate(cards + new_cards)
        errs += validate_lens(cards + new_cards)
        if brew:
            if len(new_cards) != 1:
                errs.append("brew run must return exactly 1 card")
            else:
                want = {f.casefold() for f in brew}
                got = {f.casefold() for f in
                       new_cards[0].get("fields", [new_cards[0].get("fieldA"),
                                                   new_cards[0].get("fieldB")])}
                if want != got:
                    errs.append(f"brew fields mismatch: wanted {sorted(want)} got {sorted(got)}")
        else:
            widths = sorted(len(c.get("fields", [c.get("fieldA"), c.get("fieldB")]))
                            for c in new_cards)
            if len(new_cards) == 3 and not (widths[0] == 2 and widths[1] == 3
                                            and widths[2] >= 4):
                errs.append(f"batch must be one 2-field, one 3-field, one 4+-field card (got widths {widths})")
            fams = {LENS_FAMILY.get(c.get("lens")) for c in new_cards}
            if len(new_cards) == 3 and not (
                    fams & {"dialectical", "generative"}):
                errs.append("batch must include at least one dialectical or "
                            "generative lens (irony/paradox/contrast/"
                            "counterfactual/thought_experiment/first_principles)")
        if not errs:
            pack["cards"] = cards + new_cards
            with open(CARDS_PATH, "w", encoding="utf-8") as f:
                json.dump(pack, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print("ADDED:", *[f"{c['title']} ({c['fieldA']} x {c['fieldB']})"
                              for c in new_cards], sep="\n  ")
            print("TOTAL:", len(pack["cards"]))
            return 0
        last_err = "; ".join(errs[:10])
        print("attempt", attempt + 1, "failed validation:", last_err,
              file=sys.stderr)
    print("Giving up without writing - pack left untouched.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
