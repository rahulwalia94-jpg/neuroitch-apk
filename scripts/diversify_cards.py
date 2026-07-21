#!/usr/bin/env python3
"""One-off diversifier: inject cards on the lenses and domains the pack is
missing (irony, paradox, dialectic, counterfactual, thought experiment, first
principles) drawn from psychology, mythology, storytelling, probability,
philosophy and human skills - not just science analogies.

Generates one card per target, validates it against the pack rules, and
appends. Resumable and safe: never writes a card that fails validation.
"""
import importlib.util
import json
import os
import re
import sys
import urllib.request

CARDS_PATH = "cards.json"
MODEL = os.environ.get("MODEL", "claude-sonnet-5")
API_KEY = os.environ["ANTHROPIC_API_KEY"]

g = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("g", "scripts/generate_cards.py"))
importlib.util.spec_from_file_location("g", "scripts/generate_cards.py").loader\
    .exec_module(g)

# (lens, a nudge toward domains/pairings the pack lacks)
TARGETS = [
    ("irony", "psychology or self-improvement"),
    ("paradox", "mythology or religion"),
    ("dialectic", "politics or philosophy"),
    ("contrast", "art versus craft"),
    ("counterfactual", "history or 'what if' of a famous decision"),
    ("thought_experiment", "physics or ethics"),
    ("first_principles", "probability or decision-making"),
    ("irony", "storytelling or narrative"),
    ("paradox", "economics or markets"),
    ("perspective_shift", "a human skill like negotiation or sailing"),
    ("inversion", "cooking or gardening as a way of thinking"),
    ("scale_shift", "psychology of habits or memory"),
    ("homology", "mythology across cultures (shared origin)"),
    ("structural_mapping", "a craft skill mapped to leadership"),
    ("counterfactual", "evolution or biology"),
    ("dialectic", "storytelling: hero and shadow"),
]


def post(body):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def call(prompt):
    messages = [{"role": "user", "content": prompt}]
    body = {"model": MODEL, "max_tokens": 16000,
            "tools": [{"type": "web_search_20250305", "name": "web_search",
                       "max_uses": 5}],
            "messages": messages}
    res = post(body)
    rounds = 0
    while res.get("stop_reason") == "pause_turn" and rounds < 6:
        messages.append({"role": "assistant", "content": res["content"]})
        body["messages"] = messages
        res = post(body)
        rounds += 1
    return "\n".join(b.get("text", "") for b in res.get("content", [])
                     if b.get("type") == "text")


def main():
    pack = json.load(open(CARDS_PATH, encoding="utf-8"))
    cards = pack["cards"]
    added = 0
    for lens, hint in TARGETS:
        ids = [c["id"] for c in cards]
        titles = [c["title"] for c in cards]
        fam = g.LENS_FAMILY[lens]
        prompt = f"""You write idea cards for Neuroitch. Write ONE card whose
thinking lens is EXACTLY "{lens}" (family: {fam}). Draw it from: {hint}.
Genuinely use that lens - if it is irony, the card must turn on a real irony;
if paradox, a real paradox; if counterfactual, a real 'what if'. Do not fall
back on a plain 'these share a mechanism' analogy.

Use web search to ground it in something real. Reply with a JSON array of ONE
card. Schema (all keys required): id (new unique kebab-case, avoid {json.dumps(ids[:40])}...),
fieldA, fieldB (different; one may be a human SKILL, myth, or story, not only
an academic subject), fields (list, 2-4), title, hook, connection (>60 chars),
mechanism (>60 chars), mentalModel, realWorld, historical, business, personal,
openQuestion, reading (2-3 real "Title - Author"), tags (3-5), difficulty
(1-3), readMinutes (2-8), lens "{lens}", lensFamily "{fam}", relation (or ""),
whereItFails (>60), whereElse (>60), opposite (>60), plainly (>60, no jargon),
example (>80, an everyday scene). Do not reuse these titles: {json.dumps(titles[-30:])}.
Reply with ONLY the JSON array in a ```json fenced block."""
        text = call(prompt)
        arr = g.extract_json_array(text)
        if not arr or len(arr) != 1:
            print(f"skip {lens}/{hint}: no card", file=sys.stderr)
            continue
        card = arr[0]
        if card.get("lens") != lens:
            card["lens"] = lens
        card["lensFamily"] = fam
        errs = g.validate(cards + [card]) + g.validate_lens(cards + [card])
        if errs:
            print(f"skip {lens}: {errs[:3]}", file=sys.stderr)
            continue
        cards.append(card)
        added += 1
        print(f"added {card['id']} ({lens})")
        with open(CARDS_PATH, "w", encoding="utf-8") as f:
            json.dump(pack, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"DONE: added {added} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
