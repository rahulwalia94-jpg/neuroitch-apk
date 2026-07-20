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
    "mathematics", "biology", "economics", "linguistics", "materials science",
    "music theory", "ecology", "cryptography", "anthropology", "thermodynamics",
    "law", "epidemiology", "game theory", "neuroscience", "logistics",
    "mycology", "queueing theory", "origami mathematics", "auction theory",
    "immunology", "fluid dynamics", "archaeology", "control theory",
    "fermentation", "cartography", "information theory", "urban planning",
    "evolutionary biology", "signal processing", "sociology", "metallurgy",
    "chess theory", "supply chains", "astronomy", "typography", "seismology",
]

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
        key = "|".join(sorted([str(c.get("fieldA")), str(c.get("fieldB"))]))
        pairs[key] = pairs.get(key, 0) + 1
    for p, n in pairs.items():
        if n > 3:
            errs.append(f"pair overused: {p} x{n}")
    return errs


def call_claude(prompt):
    body = {
        "model": MODEL,
        "max_tokens": 8000,
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 6,
        }],
        "messages": [{"role": "user", "content": prompt}],
    }
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
        res = json.load(r)
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
            if isinstance(arr, list) and len(arr) == 3:
                return arr
        except json.JSONDecodeError:
            continue
    return None


def main():
    pack = json.load(open(CARDS_PATH, encoding="utf-8"))
    cards = pack["cards"]
    ids = [c["id"] for c in cards]
    titles = [c["title"] for c in cards]
    pair_counts = {}
    for c in cards:
        k = "|".join(sorted([c["fieldA"], c["fieldB"]]))
        pair_counts[k] = pair_counts.get(k, 0) + 1
    full_pairs = sorted(k for k, n in pair_counts.items() if n >= 3)
    sample = json.dumps(cards[-2:], indent=2, ensure_ascii=False)
    seeds = random.sample(DOMAINS, 4)

    prompt = f"""You write idea cards for Neuroitch, an app of structural
analogies between unrelated fields of human knowledge. Each card claims two
fields are the same thing underneath and backs it with the actual mechanism.

Use web search to research REAL published cross-disciplinary mechanisms,
isomorphisms or shared mathematics. Verify the mechanism is accurate and cite
2-3 real books or papers (format "Title - Author") in the reading list. Never
invent citations. Start your exploration from some of these seed domains (or
adjacent ones): {', '.join(seeds)}.

Style reference - the two most recent cards:
{sample}

Write EXACTLY 3 new cards as a JSON array. Schema per card (all 17 keys
required): id (new unique kebab-case slug), fieldA, fieldB (different, short
field names), title, hook (one arresting sentence), connection (200-400 chars:
why the fields are the same underneath), mechanism (200-400 chars: the actual
math/algorithm/causal machinery, rigorous), mentalModel, realWorld, historical,
business, personal (each a concrete non-empty paragraph), openQuestion
(genuinely open), reading (2-3 real "Title - Author" strings), tags (3-5
lowercase strings), difficulty (int 1-3, vary across the 3 cards),
readMinutes (int 2-8).

HARD CONSTRAINTS:
- Do not reuse any of these ids: {json.dumps(ids)}
- Do not rehash any of these existing titles/topics: {json.dumps(titles)}
- These field pairs are FULL - do not use them again: {json.dumps(full_pairs)}
- Prefer field pairs never used before.

Reply with ONLY the JSON array in a ```json fenced block."""

    for attempt in range(2):
        text = call_claude(prompt if attempt == 0 else prompt +
                           "\n\nYour previous output failed validation: " +
                           last_err + "\nFix and resend the full array.")
        new_cards = extract_json_array(text)
        if new_cards is None:
            last_err = "output was not a parseable JSON array of 3 cards"
            continue
        errs = validate(cards + new_cards)
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
