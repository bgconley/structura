from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import EmailStr, TypeAdapter

from lib.auth import AuthError, AuthService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap or rotate the first Structura admin.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", default="Structura Admin")
    parser.add_argument("--household-name", default="Structura Household")
    parser.add_argument(
        "--password",
        help="Use only for local automation; otherwise prompt securely.",
    )
    parser.add_argument("--no-must-rotate", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = args.password or getpass.getpass("Bootstrap password: ")
    email = TypeAdapter(EmailStr).validate_python(args.email)
    try:
        result = AuthService().bootstrap_admin(
            email=email,
            password=password,
            display_name=args.display_name,
            household_name=args.household_name,
            must_rotate=not args.no_must_rotate,
        )
    except AuthError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "Bootstrapped Structura admin: "
        f"user_id={result.user_id} household_id={result.household_id} email={result.email}"
    )


if __name__ == "__main__":
    main()
