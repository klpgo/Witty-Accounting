#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# squash_migrations.sh – fasst alle Alembic-Migrationen zu einer
# Basis-Migration zusammen und beweist, dass sie dasselbe Schema erzeugt.
#
# Ablauf (alles in Wegwerf-Containern, die laufende Instanz bleibt unberührt):
#   1. leere MariaDB starten (gleiches Image wie in docker-compose.yml)
#   2. Datenbank A: alle bisherigen Migrationen einspielen
#   3. Schema und Grunddaten von A auslesen und daraus die Basis-Migration
#      erzeugen – mit derselben Revisionsnummer wie der aktuelle Stand
#   4. Datenbank B: nur die Basis-Migration einspielen
#   5. Schema und Daten von A und B vergleichen
#
# Aufruf im Repository-Verzeichnis (dort, wo docker-compose.yml liegt):
#   docker compose build backend
#   ./backend/scripts/squash_migrations.sh
#
# Ergebnis in ./squash-work/: die Basis-Migration unter versions_new/ sowie
# die Auszüge beider Datenbanken. Die Migrationen im Repository werden nicht
# verändert – das Ersetzen erfolgt danach von Hand (siehe Ausgabe).
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/../.."
[ -f docker-compose.yml ] || { echo "docker-compose.yml nicht gefunden." >&2; exit 1; }

WORK="${WORK:-$PWD/squash-work}"
NET=witty-squash
DB=witty-squash-db
DB_IMAGE="${DB_IMAGE:-$(grep -m1 -E '^\s+image:\s*mariadb' docker-compose.yml | awk '{print $2}')}"
IMAGE="${IMAGE:-$(docker compose images -q backend 2>/dev/null | head -n1)}"
PW="$(openssl rand -hex 16)"

[ -n "$IMAGE" ] || { echo "Backend-Image nicht gefunden – zuerst 'docker compose build backend' ausführen." >&2; exit 1; }
[ -n "$DB_IMAGE" ] || DB_IMAGE=mariadb:11

cleanup() {
  docker rm -f "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

rm -rf "$WORK"
mkdir -p "$WORK/versions_new"

echo "1) Wegwerf-Datenbank starten ($DB_IMAGE) …"
docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" \
  -e MARIADB_ROOT_PASSWORD="$PW" "$DB_IMAGE" >/dev/null
# Das Image startet beim ersten Mal einen vorläufigen Server (ohne Netzwerk,
# Logzeile "... port: 0") zum Einrichten und danach den eigentlichen, der
# "... port: 3306" meldet. Erst wenn dieser bereit ist und eine Anmeldung
# gelingt, geht es weiter.
READY=0
for _ in $(seq 90); do
  if docker logs "$DB" 2>&1 | grep -q "socket: .*port: 3306" \
     && docker exec "$DB" mariadb -uroot -p"$PW" -e "SELECT 1" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
if [ "$READY" -ne 1 ]; then
  echo "Die Wegwerf-Datenbank ist nicht bereit geworden:" >&2
  docker logs --tail 20 "$DB" >&2
  exit 1
fi
docker exec "$DB" mariadb -uroot -p"$PW" \
  -e "CREATE DATABASE squash_old; CREATE DATABASE squash_new;"

# Nur die für Migrationen nötigen Werte setzen – die .env wird bewusst nicht
# mit "docker run --env-file" gelesen: anders als docker compose entfernt das
# keine Anführungszeichen (TZ="Europe/Berlin" käme mit Anführungszeichen an).
APP_TZ="$(grep -E '^TZ=' .env 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d "\"' " || true)"
APP_TZ="${APP_TZ:-Europe/Berlin}"
JWT="$(openssl rand -hex 32)"

backend() {
  docker run --rm --network "$NET" \
    -e TENANCY_ENABLED=false \
    -e TZ="$APP_TZ" \
    -e JWT_SECRET_KEY="$JWT" \
    -e DB_HOST="$DB" -e DB_PORT=3306 -e DB_USER=root -e DB_PASSWORD="$PW" \
    "$@"
}

dump_schema() {
  docker exec "$DB" mariadb-dump -uroot -p"$PW" --no-data --compact \
    --skip-dump-date --ignore-table="$1.alembic_version" "$1" 2>/dev/null
}

dump_data() {
  docker exec "$DB" mariadb-dump -uroot -p"$PW" --no-create-info --compact \
    --complete-insert --skip-extended-insert \
    --ignore-table="$1.alembic_version" "$1" 2>/dev/null
}

echo "2) Alle bisherigen Migrationen einspielen …"
backend -e DB_NAME=squash_old "$IMAGE" alembic upgrade head
HEAD="$(backend -e DB_NAME=squash_old "$IMAGE" alembic heads 2>/dev/null | awk 'NR==1{print $1}')"
COUNT="$(backend "$IMAGE" sh -c 'ls alembic/versions/*.py | wc -l')"
echo "   Stand: $HEAD ($COUNT Migrationen)"

dump_schema squash_old > "$WORK/old_schema.sql"
dump_data squash_old > "$WORK/old_data.sql"

echo "3) Basis-Migration erzeugen …"
cat > "$WORK/generate.py" <<'PYEOF'
import re
import sys
from pathlib import Path

head, count = sys.argv[1], sys.argv[2]
work = Path("/work")


def statements(sql: str) -> list[str]:
    """Anweisungen aus einem mariadb-dump, ohne versionsbedingte SET-Zeilen."""
    # alle Kommentarzeilen entfernen: /*!40101 SET … */; ebenso die ab
    # MariaDB 11 vorangestellte Zeile /*M!999999\- enable the sandbox mode */
    lines = [
        line for line in sql.splitlines()
        if line.strip()
        and not (
            line.lstrip().startswith("/*")
            and line.rstrip().rstrip(";").endswith("*/")
        )
    ]
    result, current = [], []
    for line in lines:
        current.append(line)
        if line.rstrip().endswith(";"):
            result.append("\n".join(current).rstrip().rstrip(";"))
            current = []
    return result


def normalize_table(statement: str) -> str:
    # Zeichensatz und Sortierung erbt die Tabelle von der Datenbank – wie
    # bei den bisherigen Migrationen; Zählerstände gehören nicht ins Schema
    statement = re.sub(r" AUTO_INCREMENT=\d+", "", statement)
    statement = re.sub(r" DEFAULT CHARSET=\w+", "", statement)
    statement = re.sub(r" COLLATE=\w+", "", statement)
    return statement


schema_sql = (work / "old_schema.sql").read_text()
data_sql = (work / "old_data.sql").read_text()

schema = [
    normalize_table(s)
    for s in statements(schema_sql)
    if s.lstrip().upper().startswith("CREATE TABLE")
]
data = [
    s for s in statements(data_sql)
    if s.lstrip().upper().startswith("INSERT")
]

# Gegenprobe: nichts darf beim Zerlegen verloren gehen
expected_tables = len(re.findall(r"^CREATE TABLE", schema_sql, re.M))
expected_rows = len(re.findall(r"^INSERT INTO", data_sql, re.M))
if len(schema) != expected_tables or len(data) != expected_rows:
    sys.exit(
        f"Zerlegung unvollständig: {len(schema)}/{expected_tables} Tabellen, "
        f"{len(data)}/{expected_rows} Datensätze"
    )

body = f'''"""baseline schema

Fasst die {count} bisherigen Migrationen (Stand v1.5.0) zu einer zusammen.
Erzeugt mit backend/scripts/squash_migrations.sh aus dem Schema, das die
bisherige Migrationskette auf MariaDB erzeugt hat.

Die Revisionsnummer entspricht dem letzten Stand der alten Kette: Bestehende
Datenbanken stehen bereits darauf und bleiben unverändert; eine leere
Datenbank erhält das vollständige Schema in einem Schritt.

Revision ID: {head}
Revises:
"""
from typing import Sequence, Union

from alembic import op


revision: str = "{head}"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = {schema!r}

# Grunddaten, die die bisherigen Migrationen angelegt haben
DATA = {data!r}


def upgrade() -> None:
    # exec_driver_sql: SQL unverändert an MariaDB übergeben (kein Auswerten
    # von Doppelpunkten als Parameter);
    # no_parameters: auch "%" wird nicht als Platzhalter gedeutet
    connection = op.get_bind().execution_options(no_parameters=True)
    connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")

    for statement in SCHEMA + DATA:
        connection.exec_driver_sql(statement)

    connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")


def downgrade() -> None:
    raise NotImplementedError(
        "The baseline migration cannot be downgraded."
    )
'''

def render(items: list[str]) -> str:
    """Liste als lesbarer Python-Code: jede Anweisung zeilenweise."""
    if not items:
        return "[]"
    parts = []
    for item in items:
        lines = item.split("\n")
        rendered = "\n".join(
            "        " + repr(line + ("\n" if i < len(lines) - 1 else ""))
            for i, line in enumerate(lines)
        )
        parts.append("    (\n" + rendered + "\n    ),")
    return "[\n" + "\n".join(parts) + "\n]"


body = body.replace("SCHEMA = " + repr(schema), "SCHEMA = " + render(schema))
body = body.replace("DATA = " + repr(data), "DATA = " + render(data))

target = work / "versions_new" / f"{head}_baseline_schema.py"
target.write_text(body)
compile(body, str(target), "exec")
print(f"   {target.name}: {len(schema)} Tabellen, {len(data)} Datensätze")
PYEOF
# mit der eigenen Benutzer-/Gruppennummer, damit der Container in das
# Arbeitsverzeichnis schreiben darf (das Image läuft sonst nicht als root)
docker run --rm -i --user "$(id -u):$(id -g)" -v "$WORK:/work" \
  "$IMAGE" python - "$HEAD" "$COUNT" < "$WORK/generate.py"

echo "4) Nur die Basis-Migration einspielen …"
backend -e DB_NAME=squash_new -v "$WORK/versions_new:/app/alembic/versions:ro" \
  "$IMAGE" alembic upgrade head
NEW_HEAD="$(docker exec "$DB" mariadb -uroot -p"$PW" -N -e 'SELECT version_num FROM squash_new.alembic_version' 2>/dev/null)"

dump_schema squash_new > "$WORK/new_schema.sql"
dump_data squash_new > "$WORK/new_data.sql"

echo "5) Vergleichen …"
normalize() { sed -E 's/ AUTO_INCREMENT=[0-9]+//' "$1"; }
FAIL=0
if ! diff <(normalize "$WORK/old_schema.sql") <(normalize "$WORK/new_schema.sql") > "$WORK/schema.diff"; then
  echo "   ABWEICHUNG im Schema – siehe $WORK/schema.diff"; FAIL=1
else
  echo "   Schema identisch ($(grep -c '^CREATE TABLE' "$WORK/old_schema.sql") Tabellen)"
fi
if ! diff "$WORK/old_data.sql" "$WORK/new_data.sql" > "$WORK/data.diff"; then
  echo "   ABWEICHUNG in den Grunddaten – siehe $WORK/data.diff"; FAIL=1
else
  echo "   Grunddaten identisch ($(grep -c '^INSERT' "$WORK/old_data.sql") Datensätze)"
fi
if [ "$NEW_HEAD" != "$HEAD" ]; then
  echo "   ABWEICHUNG im Versionsstand: $NEW_HEAD statt $HEAD"; FAIL=1
else
  echo "   Versionsstand identisch ($HEAD)"
fi

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "Die Basis-Migration erzeugt NICHT dasselbe Ergebnis. Bitte nichts ersetzen."
  exit 1
fi

cat <<EOF

Erfolgreich: Die Basis-Migration erzeugt exakt dasselbe Schema wie die
$COUNT bisherigen Migrationen.

Zum Übernehmen:
  git rm -q backend/alembic/versions/*.py
  cp "$WORK"/versions_new/*.py backend/alembic/versions/
  git add backend/alembic/versions/
  rm -rf "$WORK"
EOF
