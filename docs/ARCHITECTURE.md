# How the code is organised

TheOne has two parts: a FastAPI backend (`backend/`) and a Next.js console (`frontend/`). Both follow Clean Architecture: business rules sit at the centre with no knowledge of frameworks, and every outer layer depends inwards.

## Backend (`backend/app/`)

The backend follows Clean Architecture. Each business module (`identity`, `network`, `assistant`) has the same four layers:

```
<module>/
  domain/          entities and business rules, in plain Python
  application/     use cases, and ports.py: the interfaces they need from the outside world
  infrastructure/  implementations of those ports: database tables and repositories, the bank,
                   NIBSS, speaker and iris engines, file formats, Gemini
  api/             FastAPI routers and request/response schemas
```

```
core/            the shared kernel: settings, errors, time
infrastructure/  shared technical pieces: database engine and mapper registry, the unit of work, encryption
api/             shared web pieces: API-key roles, error mapping, request dependencies
identity/        customers and biometrics (voice, iris, device step-up)
network/         mule-network detection, the core product
  domain/          entities, the detection engine (typologies, scoring, rings), the transfer decision
                   policy, sender-side rules, explanations, the shadow risk model
  dev/             demo data, and the mock bank and NIBSS used locally (outside the layers)
assistant/       the analyst assistant: read-only tools (application), Gemini (infrastructure)
main.py          the composition root: builds the app and wires each layer together
```

### The dependency rule

Dependencies point inwards only:

```
api  ─────────►  application  ─────────►  domain
infrastructure ─────┘  (implements the ports)
```

- **Domain** imports nothing outside the domain: no SQLAlchemy, FastAPI, HTTP clients or settings. Entities are plain dataclasses (`network/domain/entities.py`, `identity/domain/entities.py`) with their own behaviour, for example `Account.watch()` and `SafeLimit.change()`.
- **Application** use cases depend only on the domain and on ports (`application/ports.py`): a unit of work with repositories, the bank connector, NIBSS, and the biometric engines. They raise the errors in `core/errors.py`, never HTTP errors.
- **Infrastructure** implements the ports. `infrastructure/tables.py` maps the domain entities onto tables (SQLAlchemy imperative mapping), so the domain never sees the ORM. `UtcDateTime` columns give every layer timezone-aware UTC times.
- **API** routers translate HTTP to a use case call and back. `api/deps.py` supplies the unit of work and the connectors for each request; `api/errors.py` turns application errors into `{"detail": ...}` responses.

`tests/test_architecture.py` checks the rule on every domain and application file, so a violation fails the build.

### Patterns used

| Pattern | Where |
|---|---|
| Repository and Unit of Work | `application/ports.py` (interfaces), `infrastructure/repositories.py`, `app/infrastructure/unit_of_work.py` |
| Ports and adapters | bank (`network/infrastructure/bank.py`), NIBSS, speaker embedder, anti-spoof, iris engine, Gemini |
| Dependency injection | FastAPI dependencies in `api/deps.py`; use cases receive their collaborators as arguments |
| Transactional outbox | bank holds and blocks (`network/application/bank_actions.py`) |
| Rich domain model | entity methods such as `Account.effective_status()`, `SafeLimit.current()`, `EnrolmentSession.accepted()` |
| Strategy | swappable connectors and engines chosen from settings |

Tests mirror this layout: `tests/identity`, `tests/network`, `tests/assistant`. Shared builders (synthetic voices, eyes and a classic mule ring) are in `tests/helpers`.

Database changes are Alembic migrations in `backend/migrations/versions/`, numbered in order.

## Frontend (`frontend/src/`)

The console follows the same rule, with four layers and a composition root:

```
domain/           what the console works with: types for rings, accounts, decisions, customers,
                  and business rules such as riskBand() (flag at 0.60, hold at 0.85)
application/      ports.ts: the gateways the console needs (network, identity, assistant, documents),
                  and use cases such as importRoute() (inline or background import)
infrastructure/
  http/           the gateways implemented over HTTP and WebSocket (the only code that calls fetch)
  media/          browser devices: the voice recorder and the iris tracker
presentation/
  components/ui/  the design system (Button, Badge, DataTable, Dialog, Tabs, ...)
  components/shell/ the app frame (sidebar, top bar) and the assistant panel
  features/       one folder per area: home, overview, rings, accounts, alerts, decisions, ops,
                  customers, settings, biometrics, simulation
  hooks/          useAsync, useActor, and gateways.tsx (useNetwork, useIdentity, ...)
  format.ts, status.tsx, three/   formatting, status labels and the shared 3D models
app/              Next.js routes; each page.tsx re-exports a page from presentation/features
  providers.tsx   the composition root: gives the HTTP gateways to the whole console
  (console)/      console pages, with the sidebar layout; the first page (/) sits outside it
```

- Pages never import the HTTP code. They ask for a gateway (`const net = useNetwork()`) and call the interface from `application/ports.ts`. Swapping the backend for a mock is a change in `app/providers.tsx` only.
- `domain/` imports nothing but itself, and `application/` only the domain: no React, no Next.js, no infrastructure.
- `eslint.config.mjs` enforces these rules, so a page that imports `@/infrastructure/http` or a domain file that imports React fails the lint.

## Running checks

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npx tsc --noEmit && npm run lint && npx next build
```
