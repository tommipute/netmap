"""Gestione utenti da riga di comando, utile se si perde l'accesso.

    docker compose exec api python -m app.users list
    docker compose exec api python -m app.users create mario --role admin
    docker compose exec api python -m app.users password mario

Con 'password' un utente di Active Directory diventa locale: serve se il dominio non risponde.
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.auth import hash_password
from app.database import SessionLocal
from app.models import User
from app.models.enums import UserRole, UserSource


def _ask_password() -> str:
    while True:
        password = getpass.getpass("Nuova password (almeno 8 caratteri): ")
        if len(password) < 8:
            print("Troppo corta.")
        elif password != getpass.getpass("Ripetila: "):
            print("Le due password non coincidono.")
        else:
            return password


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.users", description="Utenti di NetMap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="elenca gli utenti")
    create = sub.add_parser("create", help="crea un utente")
    create.add_argument("username")
    create.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ADMIN.value)
    create.add_argument("--first-name", help="nome")
    create.add_argument("--last-name", help="cognome")
    password = sub.add_parser("password", help="reimposta la password (e riattiva l'utente; uno di dominio diventa locale)")
    password.add_argument("username")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.command == "list":
            for user in db.scalars(select(User).order_by(User.username)):
                state = "attivo" if user.active else "disattivato"
                origin = "Active Directory" if user.source == UserSource.AD.value else "locale"
                print(f"{user.username:<24} {user.role:<8} {state:<12} {origin}")
            return 0
        username = args.username.strip().lower()
        user = db.scalars(select(User).where(User.username == username)).first()
        if args.command == "create":
            if user is not None:
                print(f"L'utente {username} esiste già: usa 'password' per cambiargli la password.")
                return 1
            db.add(User(username=username, first_name=args.first_name, last_name=args.last_name, role=args.role,
                        password_hash=hash_password(_ask_password()), active=True, token_version=0))
        else:
            if user is None:
                print(f"Utente {username} non trovato.")
                return 1
            if user.source == UserSource.AD.value:
                print(f"{username} è un utente di Active Directory: con la password diventa un utente locale.")
            user.password_hash = hash_password(_ask_password())
            user.active = True
            user.source = UserSource.LOCAL.value
            user.token_version += 1
        db.commit()
        print("Fatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
