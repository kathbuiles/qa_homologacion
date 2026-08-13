"""Configuraciones globales del proyecto cargadas dinámicamente."""

from qa_liquidaciones_app.python.metadata_loader import cargar_metadatos, obtener_ruta_archivo


METADATA = cargar_metadatos()

COL_PLACA = METADATA["parametros_sistema"]["columna_clave"]
DEFAULT_VIGENCIA = METADATA["parametros_sistema"]["vigencia_por_defecto"]

DIR_OC = METADATA["rutas"]["carpeta_oc"]
DIR_RESULTADOS = METADATA["rutas"]["carpeta_resultados"]

RUTA_RECAUDO_ACTUAL = obtener_ruta_archivo("recaudo_actual")
RUTA_RECAUDO_ANTERIOR = obtener_ruta_archivo("recaudo_anterior")
RUTA_OC = obtener_ruta_archivo("Objeto_contrato")
RUTA_RUNT = obtener_ruta_archivo("runt")
RUTA_NOVEDADES = obtener_ruta_archivo("novedades_sap")