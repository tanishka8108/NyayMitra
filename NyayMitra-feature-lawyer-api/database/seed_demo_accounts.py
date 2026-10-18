"""Seed the DEMO / TEST accounts — development and integration testing only.

Run from the API folder::

    python -m database.seed_demo_accounts

What it does
------------
* Creates (or restores) three clearly-marked demo accounts:

    DEMO / TEST ACCOUNTS — not real user data
    ------------------------------------------
    USER    asha@example.com    / user123     (citizen, is_demo = 1)
    LAWYER  rohan@example.com   / lawyer123   (Adv. Rohan Deshmukh,
                                               lawyer_id LAWYER_0003,
                                               verification APPROVED)
    ADMIN   admin@nyaymitra.in  / admin123    (for Admin Dashboard
                                               integration testing —
                                               ADMIN cannot be
                                               self-registered)

  These same credentials are documented in README.md.

* Stores passwords as PBKDF2 hashes exactly like self-registered
  accounts (plaintext appears only in this file's documentation and
  in the console summary — never in the database).

* Is idempotent: running it twice leaves the same three users and one
  lawyer row — no duplicates. Existing demo users get their password
  reset to the documented value (so the README credentials always
  work) and their role restored; an existing lawyer row keeps whatever
  ``verification_status`` it currently has, so re-seeding never
  silently undoes an admin's APPROVE/REJECT decision — the current
  status is printed instead.

* Never touches non-demo accounts, sessions, conversations or any
  existing PostgreSQL data.

There is deliberately no ADMIN self-registration path anywhere in the
app; this script is the sanctioned way an ADMIN comes to exist.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from auth.security import hash_password
from database.sqlite_db import connect

# ---------------------------------------------------------
# The demo accounts. is_demo = 1 is written for every one of them.
# ---------------------------------------------------------

DEMO_ACCOUNTS = [
    {
        "email": "asha@example.com",
        "password": "user123",
        "name": "Asha Verma",
        "role": "USER",
    },
    {
        "email": "rohan@example.com",
        "password": "lawyer123",
        "name": "Adv. Rohan Deshmukh",
        "role": "LAWYER",
    },
    {
        "email": "admin@nyaymitra.in",
        "password": "admin123",
        "name": "Site Administrator",
        "role": "ADMIN",
    },
]

DEMO_LAWYER = {
    "lawyer_id": "LAWYER_0003",
    "lawyer_email": "rohan@example.com",
    "admin_email": "admin@nyaymitra.in",
    "license_id": "DEMO/ENROLL/0003",
    "practice_areas": "Criminal Law; Family Law; Consumer Law",
    # The demo lawyer starts APPROVED so Find-a-Lawyer and chat can be
    # demonstrated end to end; later admin decisions are preserved on
    # re-runs (see module docstring).
    "verification_status": "APPROVED",
}


def _upsert_user(connection, account: dict) -> tuple[int, bool]:
    """Insert or restore one demo user. Returns ``(user_id, created)``."""
    password_hash = hash_password(account["password"])

    row = connection.execute(
        "SELECT id FROM users WHERE email = ?",
        (account["email"],),
    ).fetchone()

    if row is None:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                account["name"],
                account["email"],
                password_hash,
                account["role"],
            ),
        )
        return int(cursor.lastrowid), True

    user_id = int(row["id"])

    # Restore the documented identity/password/role so the README
    # credentials always work after a re-seed.
    connection.execute(
        """
        UPDATE users
        SET name = ?, password_hash = ?, role = ?, is_demo = 1,
            updated_at = ?
        WHERE id = ?
        """,
        (
            account["name"],
            password_hash,
            account["role"],
            datetime.now(timezone.utc).isoformat(),
            user_id,
        ),
    )

    return user_id, False


def seed() -> dict:
    """Run the seeder. Returns a summary (used by tests and console).

    Safe to call repeatedly: same accounts, no duplicates.
    """
    summary: dict = {
        "created": [],
        "restored": [],
        "lawyer_created": False,
        "lawyer_status": None,
    }

    connection = connect()
    try:
        lawyer_user_id = None
        admin_user_id = None

        for account in DEMO_ACCOUNTS:
            user_id, created = _upsert_user(connection, account)

            if created:
                summary["created"].append(account["email"])
            else:
                summary["restored"].append(account["email"])

            if account["role"] == "LAWYER":
                lawyer_user_id = user_id
            elif account["role"] == "ADMIN":
                admin_user_id = user_id

        existing_lawyer = connection.execute(
            "SELECT user_id, verification_status FROM lawyers"
            " WHERE lawyer_id = ?",
            (DEMO_LAWYER["lawyer_id"],),
        ).fetchone()

        if existing_lawyer is None:
            verified_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO lawyers
                    (lawyer_id, user_id, license_id, practice_areas,
                     verification_status, verified_by, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEMO_LAWYER["lawyer_id"],
                    lawyer_user_id,
                    DEMO_LAWYER["license_id"],
                    DEMO_LAWYER["practice_areas"],
                    DEMO_LAWYER["verification_status"],
                    admin_user_id,
                    verified_at,
                ),
            )
            summary["lawyer_created"] = True
            summary["lawyer_status"] = DEMO_LAWYER["verification_status"]
        else:
            # Keep the current status — never undo an admin's decision.
            connection.execute(
                """
                UPDATE lawyers
                SET user_id = ?, license_id = ?, practice_areas = ?,
                    updated_at = ?
                WHERE lawyer_id = ?
                """,
                (
                    lawyer_user_id,
                    DEMO_LAWYER["license_id"],
                    DEMO_LAWYER["practice_areas"],
                    datetime.now(timezone.utc).isoformat(),
                    DEMO_LAWYER["lawyer_id"],
                ),
            )
            summary["lawyer_status"] = existing_lawyer["verification_status"]

        connection.commit()
    finally:
        connection.close()

    return summary


def main() -> int:
    """Console entry point: seed, then print the credentials summary."""
    from database.sqlite_db import get_db_path

    print("NyayMitra demo-account seed")
    print(f"  database: {get_db_path()}")

    summary = seed()

    if summary["created"]:
        print(f"  created:  {', '.join(summary['created'])}")
    if summary["restored"]:
        print(f"  restored: {', '.join(summary['restored'])}")
    print(
        "  lawyer:   "
        f"{'created' if summary['lawyer_created'] else 'kept'}, "
        f"status {summary['lawyer_status']}"
    )

    print()
    print("DEMO / TEST ACCOUNTS — development and integration testing only.")
    print("These are NOT real user data. Passwords are stored as PBKDF2")
    print("hashes; the plaintext below is the documented demo credential")
    print("set (see README.md) and is never shipped in production frontend")
    print("builds.")
    print()
    print(f"  {'ROLE':<8}{'EMAIL':<24}{'PASSWORD':<12}NAME")
    for account in DEMO_ACCOUNTS:
        print(
            f"  {account['role']:<8}"
            f"{account['email']:<24}"
            f"{account['password']:<12}"
            f"{account['name']}"
        )
    print()
    print("Idempotent: safe to re-run; running it twice never duplicates.")
    print(
        "Re-seeding restores documented passwords but preserves an "
        "existing lawyer verification status."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
