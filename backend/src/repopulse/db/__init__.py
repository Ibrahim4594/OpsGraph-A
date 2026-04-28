"""Storage layer (M2.0).

Public surface:
- :mod:`repopulse.db.base` — declarative ``Base`` and shared ``MetaData``.
- :mod:`repopulse.db.engine` — engine + sessionmaker factories (lazy, pure).

ORM models and repository classes land in M2.0 tasks 3 + 4 respectively.
Nothing in this package is imported at app startup unless code explicitly
asks for it; the FastAPI app boots without a database (preserves v1.1's
test-friendly defaults).
"""
