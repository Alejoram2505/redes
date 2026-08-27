"""Command-line entry point for the MCP-enabled chatbot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chatbot import ChatSession
from .config import create_clients
from .llm import provider_from_env
from .logging import McpAuditLogger


def main() -> int:
    parser = argparse.ArgumentParser(description="Plant Energy MCP terminal chatbot")
    parser.add_argument(
        "--servers", default="plant-local", help="Comma-separated: plant-local,filesystem,git,plant-remote"
    )
    args = parser.parse_args()
    try:
        provider = provider_from_env()
    except RuntimeError as exc:
        parser.error(str(exc))
    clients, notes = create_clients([item.strip() for item in args.servers.split(",") if item.strip()])
    for note in notes:
        print(f"Aviso: {note}")
    started = []
    for client in clients:
        try:
            started.append(client.start())
            print(f"MCP conectado: {client.name}")
        except Exception as exc:
            print(f"MCP no disponible ({client.name}): {exc}")
    logger = McpAuditLogger(project_root=Path.cwd())
    session = ChatSession(provider, started, logger=logger)
    print("Chatbot listo. Comandos: /help, /tools, /log, /exit")
    try:
        while True:
            text = input("Tú> ").strip()
            if not text:
                continue
            if text in {"/exit", "/quit"}:
                break
            if text == "/help":
                print("/tools lista herramientas; /log muestra 20 eventos MCP; /exit termina la sesión.")
            elif text == "/tools":
                print("\n".join(sorted(session.tools)) or "No hay herramientas disponibles.")
            elif text == "/log":
                print(json.dumps(logger.tail(), ensure_ascii=False, indent=2))
            else:
                try:
                    print(f"Bot> {session.ask(text)}")
                except Exception as exc:
                    print(f"Error del anfitrión: {exc}")
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
