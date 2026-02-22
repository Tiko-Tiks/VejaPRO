#!/usr/bin/env python3
"""
Išvalo testinius įrašus, kurie rodomi Admin Ops inbox („Nauja skambucio uzklausa“).

Šalina:
  - call_requests su status='NEW' (visos „naujos skambucio uzklausos“ dingo iš inbox).

Naudojimas (serveryje arba lokaliai su prod DB):
  cd backend
  export DATABASE_URL="postgresql://..."   # arba .env
  PYTHONPATH=. python scripts/cleanup_test_inbox_data.py

  Dry-run (tik parodyti kiek būtų ištrinta):
  PYTHONPATH=. python scripts/cleanup_test_inbox_data.py --dry-run

Testiniams DRAFT projektams išvalyti rankiniu būdu (atidžiai, geriau su backup):
  -- per SQL arba per admin UI ištrinti atitinkamus projektus
"""

from __future__ import annotations

import argparse
import os
import sys

# Run from repo root or backend; ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func, select

from app.core.dependencies import SessionLocal
from app.models.project import CallRequest


def main() -> None:
    parser = argparse.ArgumentParser(description="Išvalyti testinius inbox įrašus (call_requests NEW).")
    parser.add_argument("--dry-run", action="store_true", help="Tik parodyti kiek eilučių būtų ištrinta.")
    args = parser.parse_args()

    if SessionLocal is None:
        print("Klaida: DATABASE_URL nenustatytas.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(CallRequest).where(CallRequest.status == "NEW")) or 0
        if count == 0:
            print("Call requests su status NEW: 0. Nieko trinti.")
            return
        if args.dry_run:
            print(f"Dry-run: būtų ištrinta {count} call_request(s) su status NEW.")
            return
        result = db.execute(delete(CallRequest).where(CallRequest.status == "NEW"))
        db.commit()
        print(f"Ištrinta {result.rowcount} testinių skambučių užklausų (call_requests NEW).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
