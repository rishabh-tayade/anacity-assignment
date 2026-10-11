# ANACITY Move Desk

A prototype of an agentic move-in / move-out workflow for ANACITY communities.

- **Residents** describe their move in plain language. An intake agent fills in the request, checks the
  community's rules as the conversation goes, suggests free slots, asks for the right documents and submits.
- **Admins** get a prioritised queue. A copilot re-checks every rule, recommends approve / ask for info /
  reject with reasons, and drafts the message to the resident. The admin decides.
- **Communities** are configured in YAML (fields, slots, documents, rules, how much the agent may do alone).

The design, decisions and trade-offs are explained in [docs/EXPLANATION.md](docs/EXPLANATION.md).

## Running it

Requires Python 3.11 or newer (developed on 3.14).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/Home.py
```

The app opens at http://localhost:8501. On first start it creates `data/moveflow.db` and loads a few demo
requests. To reset the demo data at any time:

```bash
python scripts/seed_demo_data.py
```

### Using Claude (optional)

The app works without any API key: understanding messages, answering questions and drafting messages fall back
to rule-based implementations. To use Claude, copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
The sidebar shows which mode is active. `LLM_PROVIDER=none` forces rule-based mode.

### Tests

```bash
pytest
```

The tests run offline. The LLM paths are covered with a fake model client.

### Deploying on Streamlit Community Cloud

Point the app at `app/Home.py`. Add `ANTHROPIC_API_KEY` under the app's secrets if you want the Claude mode.
The SQLite file lives on the container's disk, so demo data resets when the app restarts.

## Demo script

Pick the community in the sidebar, then:

1. **Green Meadows, Plan a move, signed in as Ananya Rao**
   `I'm moving into flat 1204 this weekend as a tenant` → the agent asks for the tower, then which weekend day.
   Pick Sunday and it explains Sundays are blocked and offers free slots; reply `1`. It then asks the remaining
   questions and for the three tenant documents (upload any file). Confirm with `yes`.
   Try a question at any point, e.g. `Is there a lift charge?`.
2. **Green Meadows, Admin desk** → open Priya Nair's move-out: the copilot flags Rs. 4,500 in dues and drafts a
   request-for-info. Karan Malhotra's move-in is flagged because D-404 is still occupied. Your request from step 1
   is in the queue with an approve recommendation.
3. **Skyline Towers, Plan a move, signed in as Kavita Joshi**
   `Moving out of T1-1203 on the 20th, first half, I'm the owner` → answer the UPI question → `yes`.
   Skyline lets the agent auto-approve owners when every rule passes, so it is approved immediately.
4. **Green Meadows, My requests, signed in as Farhan Qureshi** → reply to the desk's question; the request goes
   back to the admin queue.
5. **Community rules** → compare the two communities' configurations side by side.

## Project layout

```
app/                     Streamlit UI (Home, Resident, Admin, Community rules)
communities/             one YAML file per community
data/                    mock unit registry / billing data, SQLite database
moveflow/
  domain/                request model, statuses, lifecycle (state machine)
  config/                community config schema and loader
  policies/              rule interface, the rules, registry, engine
  agents/intake/         resident intake agent (extract -> plan -> reply)
  agents/review/         admin copilot (recommend, summarise, draft)
  agents/knowledge.py    answers questions from community config
  llm/                   model client interface + Claude implementation
  services/              compliance checks, slot finder, autonomy policy, request lifecycle
  repositories/          storage interface + SQLite and in-memory versions
  integrations/          unit registry / billing / notifications (mocked)
  container.py           wires everything together
tests/                   unit and conversation tests
```
