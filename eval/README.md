# Eval harness

`mc_eval.py` scores a model, persona or sampling change against a keyed multiple-choice item
bank, so a change can be shown to help instead of assumed to. Standard library only.

It was built to gate model and quant swaps on the local server. The item bank it was used with
is private and is not included; point `--db` at your own.

## Bank schema (SQLite)

```sql
create table items (
  id       integer primary key,
  qtype    text,      -- question type, used for stratified sampling and per-type scores
  stem     text,
  choices  text,      -- JSON array of choice strings, in letter order A..E
  answer   text,      -- gold letter
  verified integer,   -- only verified = 1 items are used
  retired  integer    -- retired = 1 items are skipped
);
-- optional: a human baseline shown next to the model's score
create table attempts (item_id integer, is_correct integer);
```

The bank is opened read-only.

## Run

```bash
python3 eval/mc_eval.py --db bank.db --n 100                           # stratified dev set
python3 eval/mc_eval.py --db bank.db --n 100 --system-file persona.md --tag persona
python3 eval/mc_eval.py --compare eval/runs/base.jsonl eval/runs/persona.jsonl
```

Each run writes `eval/runs/<tag>.jsonl` (one record per item) and prints accuracy overall and
per question type. `--compare` lists items gained and lost between two runs.

On the 27B model a 100-item run takes one to two hours and occupies the serial scheduler, so
run it when nobody is chatting. Only a one-item smoke run was recorded on the original setup.

## results/

Raw benchmark output behind `docs/performance.md`:

- `mtp_depth_ab.json`: plain decode against MTP depth 1, 2 and 3, 1,200 tokens each.
- `sustained_6000_tokens.json`: one 6,000-token run at depth 3.
