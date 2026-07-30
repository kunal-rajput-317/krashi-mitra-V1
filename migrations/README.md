# Schema migrations

Until now the schema was created by `Base.metadata.create_all()` at startup
([backend/main.py](../backend/main.py)). That creates *missing* tables but
never **alters** existing ones — so every column change on the 23 live tables
was a hand-written `ALTER` typed straight into production, with no record of
what ran or any way to roll it back.

Alembic replaces that. `create_all()` is still in place and still harmless
(it's a no-op once the tables exist), so nothing breaks during the switch.

## One-time setup on the existing production database

The tables already exist there, so **do not** run `upgrade` first — it would
try to create them again and fail. Mark the database as already being at the
baseline:

```bash
export DATABASE_URL='postgresql://...'   # same value Render uses
alembic stamp head
```

That writes a single `alembic_version` row and touches nothing else. Verify:

```bash
alembic current    # should print the baseline revision
```

## A fresh database (local dev, a new environment)

```bash
alembic upgrade head
```

## Making a schema change

1. Edit the model in [backend/database/db.py](../backend/database/db.py)
   (or `routes/cart.py` for `CartItem`).
2. Generate the migration:
   ```bash
   alembic revision --autogenerate -m "add msp_verified to mandi_prices"
   ```
3. **Read the generated file before running it.** Autogenerate is a good
   first draft, not an authority — it does not detect table or column
   *renames* (it emits a DROP plus an ADD, which silently discards the data)
   and it can miss server-default and constraint changes. Rewrite those by
   hand as `op.alter_column(..., new_column_name=...)`.
4. Apply and verify:
   ```bash
   alembic upgrade head
   alembic current
   ```
5. Commit the migration file alongside the model change — they are one unit.

## Useful commands

| Command | What it does |
|---|---|
| `alembic current` | Which revision this database is on |
| `alembic history --verbose` | Full revision graph |
| `alembic upgrade head` | Apply everything outstanding |
| `alembic downgrade -1` | Roll back one revision |
| `alembic upgrade head --sql` | Print the SQL instead of running it (review before prod) |

`DATABASE_URL` is read from the environment (or `.env`) by
[env.py](env.py) — the same variable the app uses, so there is no second
connection string to keep in sync.
