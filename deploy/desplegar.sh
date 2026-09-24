#!/bin/bash
# Deploy en el servidor de producción.
#
# Lo ejecuta GitHub Actions por SSM (.github/workflows/deploy.yml) dentro de /opt/matrix, después de
# descomprimir ahí el paquete del deploy: docker-compose.prod.yml, las migraciones de Liquibase,
# .env.prod, liquibase.env y el token para descargar la imagen de GHCR.
#
# Uso: bash desplegar.sh <version> <bucket-respaldos> <usuario-github>
set -euo pipefail

VERSION="$1"
BUCKET="$2"
USUARIO_GHCR="$3"
export VERSION # docker-compose.prod.yml usa ${VERSION} para la imagen de la API

cd /opt/matrix
chmod 600 .env.prod liquibase.env ghcr-token
# El contenedor de Liquibase no corre como root: necesita poder leer las migraciones y su configuración
chmod 644 liquibase.properties docker-compose.prod.yml
chmod -R a+rX db

compose() {
  docker compose -p matrix --env-file .env.prod -f docker-compose.prod.yml "$@"
}

# ---------------------------------------------------------------- 1. base de datos
# La primera vez MySQL se inicializa (~1 minuto). Se espera a que acepte conexiones por red
# con el usuario de la app: durante la inicialización solo escucha por socket.
echo "==> 1. Base de datos"
compose up -d db
lista=""
for _ in $(seq 1 60); do
  # shellcheck disable=SC2016  # comillas simples a propósito: las variables se expanden dentro del contenedor
  if compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -h 127.0.0.1 -u"$MYSQL_USER" -e "SELECT 1" "$MYSQL_DATABASE"' >/dev/null 2>&1; then
    lista="si"
    break
  fi
  sleep 3
done
[ -n "$lista" ] || { echo "MySQL no respondió a tiempo"; compose logs --tail 30 db; exit 1; }

# ---------------------------------------------------------------- 2. respaldo
# Antes de migrar: si una migración sale mal, se restaura este archivo.
echo "==> 2. Respaldo"
mkdir -p respaldos
ARCHIVO="respaldos/antes-v$VERSION-$(date +%Y%m%d-%H%M%S).sql.gz"
# shellcheck disable=SC2016  # comillas simples a propósito: las variables se expanden dentro del contenedor
compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysqldump --single-transaction --no-tablespaces -u"$MYSQL_USER" "$MYSQL_DATABASE"' | gzip > "$ARCHIVO"
aws s3 cp "$ARCHIVO" "s3://$BUCKET/$ARCHIVO" --only-show-errors
find respaldos -name '*.sql.gz' -mtime +7 -delete # en el servidor solo la última semana; S3 guarda 30 días
echo "$ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"

# ---------------------------------------------------------------- 3. migraciones
echo "==> 3. Migraciones (Liquibase)"
docker run --rm --network matrix_default --env-file liquibase.env -e INSTALL_MYSQL=true \
  -v /opt/matrix/db/liquibase/changelog:/liquibase/changelog \
  -v /opt/matrix/liquibase.properties:/liquibase/liquibase.properties \
  liquibase/liquibase:5.0.4 --defaults-file=/liquibase/liquibase.properties update

# ---------------------------------------------------------------- 4. API
echo "==> 4. API v$VERSION"
docker login ghcr.io -u "$USUARIO_GHCR" --password-stdin < ghcr-token
compose pull web
compose up -d web
docker logout ghcr.io

# ---------------------------------------------------------------- 5. verificación
echo "==> 5. Verificación"
sana=""
for _ in $(seq 1 30); do
  if curl -fsS http://localhost/health; then
    sana="si"
    echo
    break
  fi
  sleep 2
done
rm -f ghcr-token liquibase.env
[ -n "$sana" ] || { echo "La API no responde en /health"; compose logs --tail 50 web; exit 1; }

docker image prune -f >/dev/null
echo "==> Deploy de v$VERSION terminado"
