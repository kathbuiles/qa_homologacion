"""Módulo para cargar la configuración y rutas desde el archivo de metadatos."""

import json
from pathlib import Path
from typing import Any, Dict


def cargar_metadatos(ruta_json: str = "metadata.json") -> Dict[str, Any]:
    """Carga y retorna el diccionario de metadatos desde un archivo JSON."""
    archivo_config = Path(ruta_json)

    if not archivo_config.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de metadatos en: {archivo_config.resolve()}"
        )

    with open(archivo_config, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def obtener_ruta_archivo(clave_archivo: str, ruta_json: str = "metadata.json") -> Path:
    """Construye la ruta absoluta de un archivo fuente según los metadatos."""
    metadata = cargar_metadatos(ruta_json)

    base = Path(metadata["rutas"]["directorio_base"])
    carpeta_req = metadata["rutas"]["carpeta_requerimientos"]
    nombre_archivo = metadata["archivos_fuente"].get(clave_archivo, "")

    if not nombre_archivo:
        raise KeyError(f"La clave de archivo '{clave_archivo}' no existe en los metadatos.")

    return base / carpeta_req / nombre_archivo