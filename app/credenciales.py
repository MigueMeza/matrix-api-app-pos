"""Usuario y NIP de los empleados.

Usuario: 2 primeras letras del primer nombre + 2 del primer apellido + un número consecutivo por si se repite
(Antonio Pérez Velázquez → ANPE1; Antonia Pedraza Medina → ANPE2). Sin acentos ni Ñ.
Si las 4 letras forman una palabra inconveniente (PENE, PUTO...), se cambian 2 letras al azar (PUTO → LUYO).
NIP: 6 dígitos al azar. En la base solo se guarda su hash: se muestra una sola vez al darlo de alta o resetearlo.
"""
import re
import secrets
import string
import unicodedata

# Lista de palabras inconvenientes de la CURP (RENAPO): justo las que pueden salir de juntar iniciales
PALABRAS_INCONVENIENTES = {
    "BACA", "BAKA", "BUEI", "BUEY", "CACA", "CACO", "CAGA", "CAGO", "CAKA", "CAKO", "COGE", "COGI", "COJA",
    "COJE", "COJI", "COJO", "COLA", "CULO", "FALO", "FETO", "GETA", "GUEI", "GUEY", "JETA", "JOTO", "KACA",
    "KACO", "KAGA", "KAGO", "KAKA", "KAKO", "KOGE", "KOGI", "KOJA", "KOJE", "KOJI", "KOJO", "KOLA", "KULO",
    "LILO", "LOCA", "LOCO", "LOKA", "LOKO", "MAME", "MAMO", "MEAR", "MEAS", "MEON", "MIAR", "MION", "MOCO",
    "MOKO", "MULA", "MULO", "NACA", "NACO", "PEDA", "PEDO", "PENE", "PIPI", "PITO", "POPO", "PUTA", "PUTO",
    "QULO", "RATA", "ROBA", "ROBE", "ROBO", "RUIN", "SENO", "TETA", "VACA", "VAGA", "VAGO", "VAKA", "VUEI",
    "VUEY", "WUEI", "WUEY",
}


def solo_letras(texto):
    """"Pérez Núñez" → "PEREZNUNEZ": mayúsculas, sin acentos (la Ñ queda como N), solo A-Z."""
    sin_acentos = unicodedata.normalize("NFD", texto or "")
    sin_acentos = "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z]", "", sin_acentos.upper())


def prefijo_usuario(nombres, apellido):
    """Las 4 letras del usuario (sin el número), ya sin palabras inconvenientes."""
    primer_nombre = (nombres or "").split()[0] if (nombres or "").split() else ""
    prefijo = solo_letras(primer_nombre)[:2] + solo_letras(apellido)[:2]

    while prefijo in PALABRAS_INCONVENIENTES:
        letras = list(prefijo)
        for posicion in secrets.SystemRandom().sample(range(len(letras)), 2):
            letras[posicion] = secrets.choice([c for c in string.ascii_uppercase if c != letras[posicion]])
        prefijo = "".join(letras)
    return prefijo


def siguiente_usuario(cursor, prefijo):
    """ANPE → ANPE1, o ANPE3 si ya existen ANPE1 y ANPE2 (toma el número más alto + 1)."""
    cursor.execute(
        "SELECT usuario_login FROM usuarios WHERE usuario_login REGEXP %s",
        (f"^{prefijo}[0-9]+$",),
    )
    numeros = [int(fila["usuario_login"][len(prefijo):]) for fila in cursor.fetchall()]
    return f"{prefijo}{max(numeros, default=0) + 1}"


def nuevo_nip():
    return "".join(secrets.choice(string.digits) for _ in range(6))
