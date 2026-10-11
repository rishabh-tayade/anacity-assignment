# Move-in / Move-out Agentic Workflow: Explanation

## 1. How I read the problem

A move is one of the few times a resident and the community office *have* to work together, and it is usually
done badly: a WhatsApp message to the facility manager, a PDF form, a few calls about which documents are needed,
and a lot of checking by hand on the admin side.

**What a move involves**

| | Move-in | Move-out |
|---|---|---|
| Resident needs to know | allowed days and slots, notice period, documents (differ for owners and tenants), lift/deposit rules | dues to clear, NOC (tenants), what to hand back, deposit refund |
| Admin needs to verify | unit exists and is actually free, the person is who they claim, documents, slot capacity | the person is the registered occupant, dues are cleared, slot capacity |
| Shared constraint | lifts, loading bay and security staff are limited, so moves are slotted | same |

**Pain points I designed for**

- *Residents* don't know the rules until they break them, find out about missing documents late, and have no
  visibility after submitting.
- *Admins* receive incomplete requests, then manually cross-check the unit registry, billing and the move calendar.
  Most requests are routine; a few need judgement. Both kinds take the same effort today.
- *Communities* differ: one blocks Sundays and needs police verification, another allows weekend moves and
  is happy to auto-approve owners. A hard-coded flow doesn't survive the second community.

So the goal is: **get a complete, rule-compliant request on the first try, and make the admin's decision a
one-look decision**, with the rules of each community kept out of the code.

## 2. The experiences

### Resident (both request types)

| Stage | What happens | Why |
|---|---|---|
| Begin | Open *Plan a move*. Name and phone come from the logged-in profile and are never asked. The agent invites a free-form description. | People describe a move in one sentence ("moving into B-1204 next Saturday morning as a tenant"). A form makes them translate that into 8 fields. |
| Complete | The agent extracts what it can, asks only for what is missing, one question at a time, in the order the community configured. Rules are checked **as soon as the relevant answer is given**. If the date is blocked or the slot is full, it says why and offers numbered free alternatives. Vague answers ("this weekend", "flat 1204") get a clarifying question rather than a guess. Questions ("is there a lift charge?") are answered from the community's own info, then the conversation continues where it was. | Fixing a date problem at question 3 is better than at submission. Clarifying instead of guessing avoids wrong bookings. |
| Documents | Once the agent knows the request type and owner/tenant, it lists exactly the documents needed and the side panel takes uploads. Where the community treats documents as a warning, the resident can say "later". | The document list depends on type × occupancy × community. |
| Submit | A summary with any warnings ("Rs. 4,500 dues outstanding, the desk will look at this") and the community's guidelines, then explicit confirmation. "No" lets them change anything in plain words. | Nothing is submitted without a clear yes. Warnings set expectations. |
| Follow | *My requests* shows status, timeline, messages from the desk and, once approved, the move-day checklist. If the desk asks for more info, the resident replies and attaches documents there, which puts the request back in the queue. The chat also answers "what's the status of my request". | Closes the loop that usually happens over phone calls. |

Move-out differs only through configuration: different fields (forwarding address, access cards to return, refund
UPI), different documents (owner NOC for tenants) and extra rules (dues clearance, registered occupant check).

The side panel always shows the request as the agent currently understands it, plus an expander
("How the agent read your last message") that shows the extracted values, the chosen next step and the rule checks.
That makes the agent's behaviour inspectable, both for the resident and for anyone evaluating it.

### Admin

| Stage | What happens |
|---|---|
| Receive | A queue ordered by what needs action first (waiting for review), then by how soon the move is. Counters show waiting, waiting-on-resident, upcoming and auto-approved. |
| Understand | A short brief ("Priya Nair (tenant) wants to move out of C-305 on Sat 17 Oct... Needs attention: maintenance dues") plus all answers, documents, messages and timeline. |
| Assess | Every rule check re-run **at review time** (a slot may have filled since submission), shown as pass / warning / blocker with a reason. A recommendation (approve, ask for info, reject, or wait for the resident) with a confidence and the reasons behind it. If the date no longer works, free alternatives are listed. |
| Act | The recommended action is pre-selected and the message to the resident is pre-drafted with the specific asks (amount of dues, missing document names, alternative slots). The admin can change the action, edit the text, and send. Approved requests can be marked completed after the move, or cancelled. |

## 3. Architecture

```
            Streamlit UI (app/)                      thin: renders state, forwards input
   Resident page        Admin page       Rules page
        |                    |
  IntakeAgent           AdminCopilot                 agents/  (orchestrators, no business rules)
  extractor/planner/    recommender/summarizer/
  replies/knowledge     drafter/triage
        \                    /
   ComplianceService  SlotFinder  AutonomyPolicy  RequestService     services/
        |                                              |
   PolicyEngine -> rules (registry)                state machine      policies/, domain/
        |                                              |
   UnitDirectory / DuesProvider (mock)         RequestRepository (SQLite)   integrations/, repositories/
        \______________ CommunityConfig (YAML) ______________/             config/
   LLMClient (Claude, optional) used only inside agents/ via fallbacks      llm/
```

- `container.py` is the composition root: the only place that chooses implementations
  (SQLite vs in-memory, mock vs real integrations, Claude vs rules).
- Everything above the services depends on interfaces (`Protocol`s): `RequestRepository`, `UnitDirectory`,
  `DuesProvider`, `Notifier`, `LLMClient`, `FieldExtractor`, `QuestionAnswerer`, `Summarizer`, `MessageDrafter`.
- The UI never changes a request directly; every mutation goes through `RequestService`, which validates the
  status change against the state machine, records who did it on the timeline, saves and notifies.

**Request lifecycle**

```
DRAFT -> SUBMITTED -> UNDER_REVIEW <-> NEEDS_INFO
              |            |               |
              |            +-> APPROVED -> COMPLETED
              +-> APPROVED (agent, when allowed)
         UNDER_REVIEW / NEEDS_INFO -> REJECTED       any open state -> CANCELLED
```

## 4. Agent design

### Two agents, different jobs

**Intake agent** (resident side) runs a fixed loop per message:

1. **Understand**: if the agent offered numbered options and the reply picks one, take it (no model needed).
   Otherwise the *extractor* returns intent (info, question, confirm, change, skip, status, cancel), request type,
   field values and ambiguities.
2. **Update state**: merge values into the `IntakeSession`.
3. **Plan**: the *planner* (plain code) chooses the next step in a fixed priority order:
   clarify ambiguity → ask request type → fix blocking rule issues (with alternatives) → ask next missing field →
   ask for documents → confirm → submit.
4. **Respond**: the reply builder turns the step into text. A question gets answered first, then the step.

**Admin copilot** builds a `ReviewBrief`: re-runs the checks, recommends, summarises, finds alternative slots if
needed, and drafts the message for whichever action the admin picks. It never changes a request.

### Tools available to the agents

| Tool | Used by | Purpose |
|---|---|---|
| `ComplianceService.check` | intake planner, copilot, autonomy | run the community's rules on a draft or a request |
| `SlotFinder.alternatives` | intake planner, copilot | free date/slot combinations that pass the scheduling rules |
| `UnitDirectory`, `DuesProvider` | rules | registry occupant and outstanding dues (mocked) |
| `CommunityKnowledge` | question answering | rules, slots, documents, guidelines, FAQs from config |
| `RequestService.submit` | intake agent | the only "act" the intake agent performs, after explicit confirmation |
| resident request lookup | intake agent | answer status questions |

The tools are called by deterministic code, not chosen by the model. That's deliberate (see decisions).

### State and context

- `IntakeSession`: profile (from the platform), request type, answers, documents, chat turns, and what the agent
  last asked for (`pending_field`, `offered_choices`, `pending_ambiguities`, `awaiting_confirmation`,
  `awaiting_documents`). That "last asked" context is what lets a reply of "2", "skip" or "no" be understood.
- `MoveRequest`: all answers in a config-keyed `answers` dict, documents, a timeline of
  `(actor, action, note)` and a message thread. The timeline records whether a human, the agent or the system made
  each change, which gives an audit trail for every autonomous action.
- Context the agent did not have to ask for: the resident's profile, the unit registry, billing dues, other
  requests holding slots, and the community config.

### Inference approach: where the model helps, and where it doesn't

| Task | With Claude | Without (fallback) | Why this split |
|---|---|---|---|
| Understanding messages | structured-output extraction (JSON schema), then **every value re-validated** by the same deterministic parsers | regex/keyword extractor | Language understanding is where a model clearly beats rules; validation keeps it from inventing slots or dates. |
| Answering questions | grounded strictly in the config text, told to say "I don't know" otherwise | keyword match over FAQs and generated facts | Natural answers, no made-up policy. |
| Admin summary | 2–3 sentence brief from facts and check results | template | Useful but not critical. |
| Resident message | polishes a template draft that already contains every fact | the template itself | Facts (amounts, ids, slot options) can't be lost because they come from the template. |
| Next step, rule checks, recommendation, approvals | never | n/a | Must be predictable, testable and auditable. |
| Replies to residents | templates | n/a | They carry dates, rules and next steps that must be exactly right. |

### Handling ambiguity

- Vague dates ("this weekend") → a question with both concrete dates as numbered options.
- Unit without a tower ("flat 1204") → ask for the full unit number.
- Several ambiguities in one message are queued and asked one at a time.
- A question is answered without recording values from it ("Can I move on Sunday?" doesn't book Sunday).
- Unknown values from the model are dropped, so the field is simply asked again.
- Required fields can't be skipped; optional ones are asked once.

### Autonomy and boundaries

| Level | What the agent does | Where |
|---|---|---|
| **Guide** | Collects details, explains rules and documents, answers questions, suggests alternatives | always |
| **Recommend** | Recommends approve / ask for info / reject with reasons and confidence; drafts messages | admin copilot, always |
| **Decide** | Blocks submission on hard rule failures (notice period, blocked day, full slot, unknown unit, documents where configured as blockers) | deterministic rules |
| **Act** | Submits after the resident says yes. Auto-approves **only** if the community enabled it for that request type and occupancy **and every check passes, warnings included**. Logged as an agent action with its reason. | `AutonomyPolicy`, per community |

Boundaries: the agent never rejects, never asks for information on the admin's behalf, never edits a submitted
request, never waives a rule, and never approves anything with a warning on it.

## 5. Scalability

### What is configuration and what is core

| Configurable per community (YAML) | Core logic (code) |
|---|---|
| Intake fields: key, question, kind, required, request types, order | Request model, lifecycle and state machine |
| Move slots, capacity, aliases ("forenoon" → first half) | Conversation loop and planner priorities |
| Documents by request type × owner/tenant | Rule implementations and the rule interface |
| Which rules apply, with parameters and severity (blocker/warning) | Autonomy safety bar (all checks must pass) |
| Blocked weekdays and dates | Validation of model output |
| Autonomy: auto-approve on/off, for which types and occupancies | Audit trail, notifications interface |
| Guidelines, move-day checklist, FAQs | |

The two sample communities show the range: Green Meadows (strict, blocks Sundays, documents are blockers, every
request reviewed) and Skyline Towers (relaxed, documents are warnings, an extra parking question, owners
auto-approved).

### How it evolves

- **New community**: add a YAML file. The schema validates it at startup (and rejects configs missing core fields
  or naming unknown rules).
- **New rule** (e.g. "max two moves per tower per day"): write one `PolicyRule` subclass, add it to the registry,
  opt in from YAML. The planner, copilot, slot finder and admin UI pick it up with no changes, because they all work
  on `CheckResult`s and the rule's declared `fields`.
- **New question** (e.g. "pets?"): YAML only.
- **New request type** (e.g. interior work or a vendor visit): add the enum value and the phrases that signal it
  in `detect_request_type`; fields, documents, rules and autonomy are already keyed by request type in config.
- **Different model or provider**: implement `LLMClient`. **Real ANACITY systems**: implement `UnitDirectory`,
  `DuesProvider`, `Notifier`, `RequestRepository`; only `container.py` changes.

## 6. Assumptions

| Assumption | Why it was needed | How production may differ |
|---|---|---|
| The resident is already logged in to ANACITY; name and phone come from the profile | No auth in a prototype | Use the ANACITY session and the resident's linked units; could pre-select the unit too |
| A unit registry and billing system exist and can be queried | Needed for occupant and dues checks | Real APIs, with caching and timeouts; dues might be checked again on the move date |
| Moves are booked in fixed slots with a capacity | Common in gated communities (lifts, security) | Some communities may book lifts separately or by hour; a rule can model that |
| One open request of each type per unit | Prevents accidental duplicates | Large families or staggered moves may need exceptions |
| Uploaded files are recorded by name, contents not stored or checked | Storage and OCR are out of scope | Object storage, virus scan, and OCR/vision checks (e.g. agreement dates cover the move date) |
| Notifications are in-app only (logged) | No messaging provider | Push/SMS/WhatsApp via ANACITY's notification service |
| A single admin role per community | Simpler queue | Roles (facility manager, security, committee), assignment and SLAs |
| Community config is edited as files | Fast to build and review | An admin UI with validation and versioning, stored in a DB |
| Indian context (rupees, +91 phone numbers, festival dates) | Matches ANACITY's market | Locale-specific parsing and formats |

## 7. Key decisions and trade-offs

- **Deterministic orchestration instead of a free-roaming tool-calling agent.** The model understands and writes;
  code decides the flow, checks rules and changes state. Trade-off: less flexible conversation, but predictable,
  cheap, testable and safe for actions that affect a real building. A fully model-driven loop would be easier to
  extend to unforeseen conversations, and would be my next experiment once evals exist.
- **The prototype must work without a model.** Every model-backed component has a rule-based fallback behind
  the same interface. This gives graceful degradation in production and a demo that runs anywhere.
- **Templates for resident replies.** Less "chatty" than generated text, but every date, rule and amount shown
  is guaranteed correct.
- **Warnings vs blockers per community.** The same rule (documents) can stop submission in one community and only
  flag the admin in another. This captures real policy differences with one implementation.
- **Re-checking at review time.** Submission-time results can go stale (slots fill, dues get paid); the copilot
  always shows the current state.
- **Answers stored as a config-keyed dictionary.** Adding a question needs no schema migration; the handful of
  fields the core needs are exposed as typed properties.
- **Streamlit for the UI.** Pure Python and quick to host. The core package has no Streamlit dependency, so a
  FastAPI backend or the ANACITY mobile app could reuse it as is.
- **Model choice.** Claude Opus 5.5 at low effort by default, configurable via env. Refusals, truncation, invalid
  JSON and API errors all raise `LLMError` and fall back to rules, so no separate server-side fallback is enabled.

## 8. Testing and results

`pytest` runs 75 tests offline in a few seconds. All pass.

| Area | What is covered |
|---|---|
| Lifecycle | allowed and forbidden transitions, final states |
| Config | both YAML files load, core fields required, unknown rule rejected, documents by type × occupancy |
| Rules | notice period, past dates, blocked weekday and festival, the same date passing in another community, slot capacity counting only active requests, unknown unit, occupied unit with/without a move-out on file, occupant mismatch, dues only for move-out, duplicates, missing documents, rules skipping when info is missing, alternative slots |
| Parsing | ISO / numeric / ordinal / month-name / weekday dates, year roll-over, weekend ambiguity, month look-alikes, unit formats, phone formats, slots from clock times, yes/no/skip |
| Conversations | full tenant move-in to the admin queue, everything in one message, profile fields not asked, blocked date → pick an alternative by number, two ambiguities in one message, question mid-flow, required field can't be skipped, change after summary, Skyline owner auto-approval, tenant with dues warned then sent to review, cancel |
| Model path | model values validated and unknown fields/slots dropped, fallback to rules when the model fails, Q&A fallback, Claude client: structured-output request, invalid JSON / refusal / max_tokens / API errors become `LLMError`, offline mode without a key |
| Admin | approve / ask-for-info / reject recommendations, specific draft content (dues amount, alternative slots), slot filled after submission, full needs-info round trip, no approving finished requests, queue ordering, SQLite round trip |

I also ran every page headlessly with Streamlit's `AppTest` (admin approving, resident replying to a needs-info
request) and walked through the demo script manually in rule-based mode. Tests found two real bugs during
development: `b1204` was read as `B1-204`, and `+91 98765 43210` wasn't recognised. Both are fixed and covered.

**Not verified**: live calls to Claude (no API key in the build environment). The client is tested against a
stubbed SDK, and every model output passes through the same validation as the rule-based path, but extraction
quality with the real model should be measured with an eval set (see next steps).

## 9. Limitations

- The rule-based extractor handles common phrasing well but not everything ("the Saturday after Diwali").
  Claude mode is meant to cover that.
- English only. Hindi/Hinglish messages would need the model path and testing.
- One conversation per resident session; chat history isn't persisted across server restarts (submitted requests are).
- No real authentication, file storage, notification delivery or concurrent booking locks (two residents could
  confirm the last slot at the same moment; production needs a transactional slot reservation).
- Config changes need a restart to load.

## 10. Failure recovery

| Failure | What happens |
|---|---|
| Model unavailable, slow, refuses, truncates, or returns invalid JSON | `LLMError` → the same request is handled by the rule-based component; logged |
| Model returns a value that isn't valid (unknown slot, bad date, unknown field) | dropped by validation; the agent asks for that field again |
| Resident gives an unusable answer | the planner asks the same question again; ambiguous ones get a clarifying question |
| Slot fills up or dues change after submission | the copilot re-checks at review time and drafts a request for new info with alternatives |
| Invalid status change (e.g. approving a rejected request) | `InvalidTransitionError`; nothing is saved |
| Bad community config | startup fails with a validation error naming the problem, instead of misbehaving later |
| Wrong auto-approval | only possible when every check passed; the timeline records it as an agent action with its reason, and the admin can still cancel |

## 11. Next steps for production

1. **Integrate**: ANACITY auth and resident profile, unit registry, billing, notifications; replace the mocks behind
   the existing interfaces. Postgres instead of SQLite; transactional slot reservation.
2. **Documents**: real storage plus model-based checks (is this a rental agreement, does it cover the move date,
   does the name match), shown to the admin as additional checks.
3. **Evals before scaling autonomy**: a labelled set of real resident messages to measure extraction accuracy
   per field; track how often admins override the copilot. Widen auto-approval per community only where override
   rates are low.
4. **Config UI** for community admins with validation, preview and versioning (who changed which rule, when).
5. **Operations**: move calendar for security and facility staff, gate passes, reminders the day before, SLA
   alerts for requests waiting too long, and an analytics view (approval times, common rejection reasons).
6. **Channels**: the core is UI-independent, so the same agent can sit behind the ANACITY app, WhatsApp, or a
   web widget.
