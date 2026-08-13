"""Módulo optimizado para la lectura local flexible de archivos pesados."""

from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
from python.metadata_loader import obtener_ruta_archivo


def verificar_estado_archivos() -> Dict[str, bool]:
    """Revisa en disco qué archivos configurados en metadata.json existen."""
    archivos = [
        "recaudo_actual",
        "recaudo_anterior",
        "Objeto_contrato",
        "runt",
        "novedades_sap",
        "simulacion_base",
        "simulacion_comparar",
    ]
    estado = {}
    for clave in archivos:
        try:
            ruta = obtener_ruta_archivo(clave)
            # Verifica la ruta exacta o con extensiones fallback
            if ruta.exists():
                estado[clave] = True
            else:
                directorio = ruta.parent
                nombre = ruta.stem
                encontrado = any(
                    (directorio / f"{nombre}{ext}").exists()
                    for ext in [".csv", ".parquet", ".pq", ".xlsx", ".txt"]
                )
                estado[clave] = encontrado
        except Exception:
            estado[clave] = False
    return estado


def _leer_archivo_por_extension(ruta: Path) -> pd.DataFrame:
    """Lee un archivo según su extensión real en el sistema de archivos."""
    ext = ruta.suffix.lower()

    if ext in [".parquet", ".pq"]:
        return pd.read_parquet(ruta)
    if ext in [".csv", ".txt"]:
        return pd.read_csv(ruta, sep=None, engine="python")
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(ruta)

    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def cargar_dataframe_local(clave_metadata: str) -> pd.DataFrame:
    """Carga archivos locales desde metadata.json con fallback de extensión."""
    try:
        ruta_configurada = obtener_ruta_archivo(clave_metadata)

        if ruta_configurada.exists():
            return _leer_archivo_por_extension(ruta_configurada)

        directorio = ruta_configurada.parent
        nombre_base = ruta_configurada.stem
        extensiones_fallback = [".csv", ".parquet", ".pq", ".xlsx", ".txt"]

        for ext in extensiones_fallback:
            ruta_candidata = directorio / f"{nombre_base}{ext}"
            if ruta_candidata.exists():
                return _leer_archivo_por_extension(ruta_candidata)

        return pd.DataFrame()

    except Exception as error:
        st.error(f"Error al cargar '{clave_metadata}': {error}")
        return pd.DataFrame()


def filtrar_por_placas(
    dataframe: pd.DataFrame,
    columna_placa: str = "Placa",
    texto_placas: str = "",
    archivo_excel: Optional[st.runtime.uploaded_file_manager.UploadedFile] = None,
) -> pd.DataFrame:
    """Filtra el DataFrame local por una o varias placas ingresadas por el usuario."""
    if dataframe.empty:
        return dataframe

    placas_objetivo: List[str] = []

    if texto_placas.strip():
        placas_objetivo.extend(
            [p.strip().upper() for p in texto_placas.split(",") if p.strip()]
        )

    if archivo_excel is not None:
        try:
            excel_cargado = pd.read_excel(archivo_excel)
            if columna_placa in excel_cargado.columns:
                placas_excel = (
                    excel_cargado[columna_placa]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .tolist()
                )
                placas_objetivo.extend(placas_excel)
        except Exception as error:
            st.error(f"Error al leer el archivo de placas: {error}")

    if placas_objetivo:
        placas_unicas = set(placas_objetivo)
        filtro = dataframe[columna_placa].astype(str).str.strip().str.upper()
        return dataframe[filtro.isin(placas_unicas)]

    return dataframe