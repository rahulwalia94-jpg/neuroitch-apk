#!/usr/bin/env python3
"""Backfill personaExamples for every card that lacks them.

For each card, asks Claude to rewrite the example for each persona's world.
Cheap (no web search), resumable (skips cards already done), and never
corrupts the pack (validates before writing each card).
"""
import json
import os
import re
import sys
import urllib.request

CARDS_PATH = "cards.json"
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")
API_KEY = os.environ["ANTHROPIC_API_KEY"]

PERSONAS = {
    "student": "a university student juggling lectures, deadlines and part-time work",
    "founder": "a startup founder worrying about runway, hiring and product",
    "healthcare": "a nurse or doctor working long clinical shifts on a busy ward",
    "teacher": "a schoolteacher managing a classroom, marking and lesson plans",
    "parent": "a busy parent running a household and raising young children",
    "engineer": "a software engineer shipping code, on-call rotas and reviews",
}


def post(body):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def extract_obj(text):
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = fenced if fenced else []
    if not cands:
        i = text.find("{")
        if i != -1:
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        cands.append(text[i:j + 1])
                        break
    for c in reversed(cands):
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def personalise(card):
    briefs = "\n".join(f'- "{k}": {v}' for k, v in PERSONAS.items())
    prompt = f"""Rewrite this idea's everyday example for six different readers,
so each one sees it in their own world. Keep the underlying point identical.

Idea: {card['title']}
Plain English: {card['plainly']}
General example: {card['example']}

Write a JSON object with exactly these keys, each value a concrete scene from
that person's life (over 60 characters, no jargon, British spelling):
{briefs}

Reply with ONLY the JSON object in a ```json fenced block."""
    for _ in range(2):
        res = post({
            "model": MODEL,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        })
        text = "\n".join(b.get("text", "") for b in res.get("content", [])
                         if b.get("type") == "text")
        obj = extract_obj(text)
        if obj and all(
                isinstance(obj.get(k), str) and len(obj[k]) > 60
                for k in PERSONAS):
            return {k: obj[k] for k in PERSONAS}
    return None


def main():
    limit = int(os.environ.get("LIMIT", "0"))
    pack = json.load(open(CARDS_PATH, encoding="utf-8"))
    cards = pack["cards"]
    done = 0
    for c in cards:
        pe = c.get("personaExamples") or {}
        if all(isinstance(pe.get(k), str) and len(pe.get(k, "")) > 60
               for k in PERSONAS):
            continue
        result = personalise(c)
        if result is None:
            print(f"skip {c['id']}: generation failed", file=sys.stderr)
            continue
        c["personaExamples"] = result
        done += 1
        print(f"personalised {c['id']} ({done})")
        with open(CARDS_PATH, "w", encoding="utf-8") as f:
            json.dump(pack, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if limit and done >= limit:
            break
    print(f"DONE: personalised {done} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
