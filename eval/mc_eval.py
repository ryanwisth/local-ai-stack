#!/usr/bin/env python3
"""Multiple-choice eval harness: score a model / persona / parameter change against a keyed item bank.

Pulls verified, non-retired items (stem + lettered choices + gold answer) from a SQLite bank,
runs them through an OpenAI-compatible endpoint (mtplx directly by default, no tool overhead),
extracts the chosen letter, and reports accuracy per question type, next to a human baseline
when the bank also holds an `attempts` table. Writes a JSONL so two runs can be diffed
item-by-item (--compare).

Expected schema (see eval/README.md):
  items(id, qtype, stem, choices JSON array, answer letter, verified 0/1, retired 0/1)
  attempts(item_id, is_correct 0/1)            -- optional

Examples:
  python mc_eval.py --db bank.db --n 100                          # stratified 100-item dev set
  python mc_eval.py --db bank.db --n 100 --system-file persona.md --tag persona
  python mc_eval.py --db bank.db --n 100 --model my-lora --base-url http://127.0.0.1:8001/v1 --tag lora
  python mc_eval.py --compare runs/base.jsonl runs/lora.jsonl
"""
import argparse, json, os, random, re, sqlite3, sys, time, urllib.request

DB = os.path.expanduser(os.environ.get("EVAL_DB", "bank.db"))
RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
LETTERS = "ABCDE"


def connect():
    """Open the bank read-only; the harness never writes to it."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def load_items(n, qtypes, seed):
    c = connect()
    q = "select id, qtype, stem, choices, answer from items where verified=1 and coalesce(retired,0)=0 and choices is not null and answer is not null"
    rows = [r for r in c.execute(q) if r[4] and r[4].strip().upper()[:1] in LETTERS]
    if qtypes:
        rows = [r for r in rows if r[1] in qtypes]
    random.Random(seed).shuffle(rows)
    if n and n < len(rows):                       # stratified by qtype
        by = {}
        for r in rows: by.setdefault(r[1], []).append(r)
        share = max(1, n // len(by)); picked = []
        for k in sorted(by): picked += by[k][:share]
        rows = picked[:n] if len(picked) >= n else (picked + [r for r in rows if r not in picked])[:n]
    return rows


def build_prompt(stem, choices_json):
    try: choices = json.loads(choices_json)
    except Exception: choices = [str(choices_json)]
    lines = [f"{LETTERS[i]}. {c}" for i, c in enumerate(choices[:5])]
    return (f"{stem.strip()}\n\n" + "\n".join(lines) +
            "\n\nSolve it, then end your reply with exactly one line of the form `Answer: X` where X is the letter.")


def ask(base_url, model, system, user, max_tokens, temperature, timeout):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    body = json.dumps({"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": temperature}).encode()
    req = urllib.request.Request(f"{base_url}/chat/completions", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    msg = d["choices"][0]["message"]
    return (msg.get("content") or ""), (msg.get("reasoning_content") or msg.get("reasoning") or ""), time.time() - t0, d.get("usage", {})


def extract_letter(text):
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.findall(r"Answer\s*[:\-]\s*\(?([A-E])\)?", t, flags=re.I)
    if m: return m[-1].upper()
    m = re.findall(r"\b([A-E])\b", t.strip().splitlines()[-1] if t.strip() else "")
    return m[-1].upper() if m else None


def human_baseline():
    """Accuracy from the optional attempts table; empty if the bank has none."""
    c = connect()
    try:
        out = {"overall": c.execute("select round(100.0*sum(is_correct)/count(*),1), count(*) from attempts").fetchone()}
    except sqlite3.OperationalError:
        return {"overall": (None, 0)}
    for qt, n, pct in c.execute("select i.qtype, count(*), round(100.0*sum(t.is_correct)/count(*),1) from attempts t join items i on i.id=t.item_id group by i.qtype"):
        out[qt] = (pct, n)
    return out


def run(a):
    items = load_items(a.n, a.qtype, a.seed)
    system = open(os.path.expanduser(a.system_file)).read() if a.system_file else None
    os.makedirs(RUNS, exist_ok=True)
    out = os.path.join(RUNS, f"{a.tag}.jsonl")
    res, t_all = [], time.time()
    with open(out, "w") as f:
        for i, (iid, qt, stem, ch, gold) in enumerate(items, 1):
            gold = gold.strip().upper()[0]
            try:
                content, reasoning, dt, usage = ask(a.base_url, a.model, system, build_prompt(stem, ch), a.max_tokens, a.temperature, a.timeout)
                pred = extract_letter(content) or extract_letter(reasoning); err = None
            except Exception as e:
                content = reasoning = ""; pred = None; dt = 0; usage = {}; err = str(e)[:120]
            rec = {"id": iid, "qtype": qt, "gold": gold, "pred": pred, "correct": pred == gold, "secs": round(dt, 1),
                   "tokens": usage.get("completion_tokens"), "err": err, "answer_tail": content[-160:]}
            res.append(rec); f.write(json.dumps(rec) + "\n"); f.flush()
            print(f"[{i}/{len(items)}] {qt:4} gold={gold} pred={pred or '-'} {'✓' if rec['correct'] else '✗'} {dt:5.1f}s", flush=True)
    report(res, a.tag, time.time() - t_all)


def report(res, tag, elapsed=None):
    base = human_baseline()
    tot = len(res); ok = sum(r["correct"] for r in res); noans = sum(r["pred"] is None for r in res)
    print(f"\n=== {tag}: {ok}/{tot} = {100*ok/max(tot,1):.1f}%  (no-answer: {noans}, human overall: {base['overall'][0]}% n={base['overall'][1]})"
          + (f"  [{elapsed/60:.1f} min]" if elapsed else ""))
    by = {}
    for r in res: by.setdefault(r["qtype"], []).append(r["correct"])
    for qt in sorted(by):
        m = by[qt]; b = base.get(qt)
        print(f"  {qt:4} model {100*sum(m)/len(m):5.1f}% (n={len(m):3})   human {b[0] if b else '  -'}% (n={b[1] if b else 0})")


def compare(p1, p2):
    r1 = {json.loads(l)["id"]: json.loads(l) for l in open(p1)}
    r2 = {json.loads(l)["id"]: json.loads(l) for l in open(p2)}
    ids = sorted(set(r1) & set(r2))
    gained = [i for i in ids if not r1[i]["correct"] and r2[i]["correct"]]
    lost = [i for i in ids if r1[i]["correct"] and not r2[i]["correct"]]
    a1 = sum(r1[i]["correct"] for i in ids); a2 = sum(r2[i]["correct"] for i in ids)
    print(f"{os.path.basename(p1)}: {a1}/{len(ids)}   {os.path.basename(p2)}: {a2}/{len(ids)}   Δ = {a2-a1:+d}")
    print(f"  gained {len(gained)}: {gained[:20]}\n  lost   {len(lost)}: {lost[:20]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", help="SQLite item bank (default: $EVAL_DB or ./bank.db)")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--qtype", nargs="*")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", default="mtplx-qwen38-27b-optimized-speed")
    p.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--system-file")
    p.add_argument("--tag", default="base")
    p.add_argument("--max-tokens", type=int, default=3000)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--compare", nargs=2, metavar=("RUN1", "RUN2"))
    a = p.parse_args()
    if a.db:
        DB = os.path.expanduser(a.db)
    compare(*a.compare) if a.compare else run(a)
