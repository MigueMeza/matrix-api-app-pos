from contextlib import contextmanager

import pymysql
from flask import current_app


def get_connection():
    cfg = current_app.config
    return pymysql.connect(
        host=cfg["DB_HOST"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,  # cada fila regresa como dict, no como tupla
        charset="utf8mb4",
    )


@contextmanager
def db_cursor(commit=False):
    """Abre una conexión y un cursor, y siempre cierra la conexión al salir.

    Uso:
        with db_cursor() as cursor:
            cursor.execute("SELECT ...")
            filas = cursor.fetchall()

        with db_cursor(commit=True) as cursor:
            cursor.execute("UPDATE ...")
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        if commit:
            conn.commit()
    finally:
        conn.close()
