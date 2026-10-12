"""Findet die Fehlermeldungen im Quelltext des Backends.

Ausgewertet werden ``raise Xyz("…")``, ``HTTPException(detail="…")`` und
``delivery_error_message="…"`` mit literalen Texten oder f-Strings. Platzhalter aus f-Strings werden
als ``{}`` zurückgegeben. Meldungen aus Variablen (``str(exc)``) sind
bereits an ihrer Quelle erfasst.
"""

import ast
from pathlib import Path

APP_DIRECTORY = Path(__file__).resolve().parents[1] / "app"

# eigene Anwendung mit eigener Fehlerbehandlung
EXCLUDED_DIRECTORIES = ("control",)

# Schlüsselwortargumente, die eine spätere Fehlermeldung enthalten
MESSAGE_KEYWORDS = ("delivery_error_message",)


def _template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("{", "{{").replace("}", "}}")

    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []

        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(
                    str(value.value).replace("{", "{{").replace("}", "}}")
                )
            else:
                parts.append("{}")

        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _template(node.left)
        right = _template(node.right)

        if left is not None and right is not None:
            return left + right

    return None


def _message_argument(call: ast.Call) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == "detail":
            return keyword.value

    if call.args:
        return call.args[0]

    return None


def _call_name(call: ast.Call) -> str:
    function = call.func

    if isinstance(function, ast.Name):
        return function.id

    if isinstance(function, ast.Attribute):
        return function.attr

    return ""


def scan_error_messages() -> dict[str, str]:
    """Liefert Vorlage -> Datei (relativ zu app/) der ersten Fundstelle."""

    found: dict[str, str] = {}

    for path in sorted(APP_DIRECTORY.rglob("*.py")):
        relative = path.relative_to(APP_DIRECTORY)

        if relative.parts[0] in EXCLUDED_DIRECTORIES:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))

        calls: list[ast.Call] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                calls.append(node.exc)
            elif (
                isinstance(node, ast.Call)
                and _call_name(node) == "HTTPException"
            ):
                calls.append(node)

        arguments: list[ast.AST] = []

        for call in calls:
            argument = _message_argument(call)

            if argument is not None:
                arguments.append(argument)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                arguments.extend(
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg in MESSAGE_KEYWORDS
                )

        for argument in arguments:
            template = _template(argument)

            if template is None or not template.strip():
                continue

            found.setdefault(template, str(relative))

    return found
