"""Comandos de consola de la API: flask --app wsgi <comando>.

crear-admin: primer arranque de una base vacía (producción recién creada por Liquibase). Crea la primera
tienda y el primer super_admin, con el mismo formato de usuario y NIP que el alta desde el panel.
Se niega a correr si ya hay un super admin activo: los demás usuarios se crean desde Personal.
"""
import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .credenciales import nuevo_nip, prefijo_usuario, siguiente_usuario
from .db import db_cursor
from .permisos import Rol


def registrar(app):
    app.cli.add_command(crear_admin)


@click.command("crear-admin")
@click.option("--nombres", required=True, help='Nombre(s) del administrador, ej. "Miguel Ángel"')
@click.option("--paterno", required=True, help="Apellido paterno")
@click.option("--materno", default="", help="Apellido materno (opcional)")
@click.option("--tienda", required=True, help="Nombre de la tienda; se crea si no existe")
@click.option("--direccion", default=None, help="Dirección de la tienda (opcional)")
@with_appcontext
def crear_admin(nombres, paterno, materno, tienda, direccion):
    """Crea la primera tienda y el primer super administrador."""
    nombres = " ".join(nombres.split())
    paterno = " ".join(paterno.split())
    materno = " ".join(materno.split())
    tienda = " ".join(tienda.split())[:150]

    prefijo = prefijo_usuario(nombres, paterno)
    if len(prefijo) < 2:
        raise click.ClickException("El nombre y el apellido deben tener letras.")
    if not tienda:
        raise click.ClickException("Falta el nombre de la tienda.")

    nombre = " ".join(p for p in (nombres, paterno, materno) if p)[:150]
    nip = nuevo_nip()

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE rol = %s AND activo = 1 FOR UPDATE",
            (Rol.SUPER_ADMIN.value,),
        )
        if cursor.fetchone()["n"] > 0:
            raise click.ClickException(
                "Ya existe un super administrador activo. Los demás usuarios se crean desde el panel (Personal)."
            )

        cursor.execute("SELECT id FROM tiendas WHERE nombre = %s", (tienda,))
        fila = cursor.fetchone()
        if fila:
            tienda_id = fila["id"]
        else:
            cursor.execute("INSERT INTO tiendas (nombre, direccion) VALUES (%s, %s)", (tienda, direccion))
            tienda_id = cursor.lastrowid

        usuario_login = siguiente_usuario(cursor, prefijo)
        cursor.execute(
            """
            INSERT INTO usuarios (tienda_id, nombre, usuario_login, password_hash, rol)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (tienda_id, nombre, usuario_login, generate_password_hash(nip), Rol.SUPER_ADMIN.value),
        )

    click.echo(f"Tienda:   {tienda}")
    click.echo(f"Nombre:   {nombre}")
    click.echo(f"Usuario:  {usuario_login}")
    click.echo(f"NIP:      {nip}")
    click.echo("Anota el NIP: no se vuelve a mostrar. Si se pierde, otro super admin lo resetea desde Personal.")
