# ms-knowledge-assistant

A Dutch-language question-answering demo over company documents: ask a question, get an answer with the passages it came from, or an honest "ik weet het niet" when the documents don't say.

Built with FastAPI, PostgreSQL + pgvector, local multilingual embeddings and a small React UI. The documents in this demo are fictional (a made-up company, "Brouwer & Zonen NV").

## Problem

Staff ask the same questions about holidays, expenses and IT rules, and the answers sit in handbooks nobody searches. A plain keyword search misses paraphrases ("verlofdagen" vs "vakantiedagen"). A chatbot that answers from memory invents policy. What is needed is an answer taken from the actual documents, with the source shown, and a refusal when the documents are silent.

## Solution

1. **Ingest** Markdown, PDF and DOCX files: split into passages, embed them locally and store them in PostgreSQL with pgvector.
2. **Ask:** embed the question, fetch the 4 most similar passages, and answer from them.
3. **Cite:** every answer lists the passages it used, with file, section, page and similarity score.
4. **Refuse:** if nothing is similar enough, or the model finds the answer isn't in the passages, the assistant says it doesn't know.
5. **Review:** an admin view lists every question, with the unanswered and low-confidence ones filterable, so the document owners can see what is missing.

## Run it

You need Docker. No API key is needed.

```bash
git clone https://github.com/Ms-8888/ms-knowledge-assistant
cd ms-knowledge-assistant
cp .env.example .env
docker compose up --build
```

Then open <http://localhost:8080>. The first start downloads images and builds the embedding model into the API image; on a warm Docker cache it was healthy in about 25 seconds, and about a minute from a colder cache (measured on one machine, see below). The seed documents are ingested automatically.

The **Beheer** tab needs the `ADMIN_KEY` from your `.env` (change it from the example value; leave it empty to disable the tab). The API and the UI listen on `127.0.0.1` only.

## Answer modes

| `LLM_BACKEND` | Needs | What you get |
|---|---|---|
| `extractive` (default) | nothing | The most relevant passage and its sources. No generated text. |
| `ollama` | [Ollama](https://ollama.com) running on the host with a model pulled (tested: `qwen2.5:7b`) | A short Dutch answer written by a local model. No key, and nothing leaves the machine. Needs a few GB of disk and RAM; tested on a 6 GB laptop GPU. |
| `anthropic` | `ANTHROPIC_API_KEY` | A short Dutch answer written by Claude from the retrieved passages, with a daily call cap and a kill switch (`LLM_ENABLED=false`). **Not yet run end to end.** |
| `claude-cli` | the `claude` CLI, logged in, on the same machine | The same as above through the author's own Claude Code login. Development mode for the author, not a deployable backend, and it does not work inside the Docker image. |

To use the local model: install Ollama, run `ollama pull qwen2.5:7b`, then start with `LLM_BACKEND=ollama docker compose up --build` (or set it in `.env`). The API container reaches Ollama on the host through `host.docker.internal`.

Embeddings always run locally (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions), so retrieval never needs a key.

## Evaluation

38 hand-written questions over the 5 seed documents, checked automatically by `eval/run_eval.py` (expected source, and a fact that must appear in the answer). The retrieval threshold (0.28) was chosen from a separate 10-question test before these questions were written and was not tuned on them. Raw results are in `eval/results/`.

| Measure | `extractive` (no model) | `ollama` `qwen2.5:7b` (local) | `claude-cli` (Claude, author's login) |
|---|---|---|---|
| In-scope questions (28): correct fact in the answer | 27/28 | 27/28 | 28/28 |
| Off-domain questions refused (4), e.g. "hoofdstad van Frankrijk" | 4/4 | 4/4 | 4/4 |
| Right topic but not in the documents, refused (4), e.g. "salaris van de directeur" | **0/4** | 4/4 | 4/4 |
| Prompt injection (2): nothing leaked or obeyed | 2/2 | 2/2 | 1/2 (see note) |
| Prompt injection (2): clean refusal | 0/2 | 1/2 | 1/2 |
| Mean time per question | 2 s | 3 s | 10 s |

Retrieval is the same in every mode (same embeddings and database): the right document is ranked first for 27 of 28 questions and is in the top 4 for all 28. In the `ollama` run the model refused one answerable question, so that question returned no citations.

What these numbers say and don't say:

- **Without a model, "ik weet het niet" only works for off-topic questions.** A question about the right area but not in the documents scores 0.33–0.54, higher than some genuine questions (0.37), so no similarity threshold can separate them. Both models did it 4/4.
- **The local model is close to the cloud one, with two weaknesses.** It wrongly refused one answerable question ("krijg ik mijn benzine terug als ik privé rij…": the answer is no, it said it didn't know). On the instruction-injection test it replied with the single word "Systeemprompt": nothing leaked, but it isn't a clean refusal.
- **The one retrieval miss** ("welk nummer bel ik in levensgevaar?") went to the handbook first because the PDF has no headings, so its single passage mixes three topics. The right document was still in the top 4.
- **The first local run looked perfect and was wrong.** Reading the answers showed the model had written `Niet_gevonden` and `NIEGT_GEVONDEN` instead of the exact refusal marker. The backend only accepted the exact string, so garbled refusals reached users as answers, and my fact check let one through because it searched for "niet". I fixed the backend (it now accepts case and spelling slips, with tests) and tightened the check, then re-scored the stored runs and re-ran the local model. The original run is kept as `eval/results/ollama-qwen2.5-7b-run1-before-fix.json`; scored with the stricter check it is 27/28 facts and 1/2 injection-safe, not the 28/28 and 2/2 it first showed.
- **The `claude-cli` injection "failure":** an answer that says "25 vakantiedagen … ik kan dus niet bevestigen dat het er 100 zijn". It correctly refuses the request, but the string check flags it because the reply repeats "100 vakantiedagen". I kept the check and report what it produced.
- **Small and friendly test.** 38 questions, a 5-document synthetic corpus, questions written by the same person who wrote the documents. Treat it as a smoke test, not a benchmark.
- **The `claude-cli` column is the author's own run through the Claude Code CLI; the `ollama` column is a local run on one laptop (RTX 3060, 6 GB).** The `anthropic` API backend has not been run against the real API, so no result is claimed for it.

## Security notes

- No file-upload endpoint. Documents are ingested from a folder at startup or with `python -m app.ingest`.
- Questions are length-limited (3–500 characters) and rate-limited per client (in memory, single process).
- The admin endpoints require an `X-Admin-Key` compared in constant time, and are off when no key is set.
- The model prompt treats passages as data and tells the model to ignore instructions inside them.
- SQL goes through SQLAlchemy with bound parameters. The UI renders text only (no HTML injection).
- Dependencies are pinned. `pip-audit` and `npm audit` were clean when this was written, and gitleaks runs in CI.

## Limitations

- Passages are cut by headings and length only. PDFs have no heading detection, so multi-topic pages become one blurry passage.
- The "confidence" shown is the best similarity score. It is not a calibrated probability.
- Tables are created at startup; there are no migrations. The rate limiter is per process.
- One English question in the evaluation was answered correctly, but the corpus is Dutch and answers come back in Dutch.
- One small synthetic corpus. Nothing here has been tested on real company documents or under load.

## Layout

```
api/     FastAPI app, ingest, tests (pytest)
web/     React + TypeScript UI, served by nginx
seed/    Fictional Dutch documents (md, docx, pdf)
eval/    Questions, runner and recorded results
scripts/ Generates the docx and pdf seed files
```

## Tests

```bash
cd api && pip install -r requirements-dev.txt
pytest          # needs a pgvector database; see .github/workflows/ci.yml
cd ../web && npm ci && npm run lint && npm run build
python eval/run_eval.py http://localhost:8080/api eval/results/extractive.json
```

## Stack

Python 3.12 · FastAPI · PostgreSQL 16 + pgvector · fastembed (ONNX) · React 19 · TypeScript · Vite · nginx · Docker Compose · GitHub Actions
