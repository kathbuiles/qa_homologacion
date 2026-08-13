"""Aplicación Principal Streamlit."""

from pathlib import Path
import sys

# Agregar la subcarpeta intermedia 'qa_liquidaciones_app' al sys.path
DIRECTORIO_ACTUAL = Path(__file__).resolve().parent
SUBDIRECTORIO_INTERMEDIO = DIRECTORIO_ACTUAL / "qa_liquidaciones_app"

if str(SUBDIRECTORIO_INTERMEDIO) not in sys.path:
    sys.path.append(str(SUBDIRECTORIO_INTERMEDIO))

import io
import pandas as pd
import streamlit as st

# Importaciones directas usando la ruta corregida
from python.file_loader import (
    cargar_dataframe_local,
    filtrar_por_placas,
    verificar_estado_archivos,
)
from python.qa_processor import procesar_qa_liquidaciones
from python.simulation_cross import cruzar_simulaciones_dinamico

st.set_page_config(
    page_title="QA Liquidaciones & Simulaciones",
    page_icon="🚗",
    layout="wide",
)

st.title("Sistema Auditor de QA Liquidaciones y Simulaciones")

# ==============================================================================
# PANEL LATERAL: ESTADO DE INSUMOS
# ==============================================================================
st.sidebar.header("📁 Estado de Bases Locales")

estado_archivos = verificar_estado_archivos()

nombres_visibles = {
    "recaudo_actual": "Recaudo Actual",
    "recaudo_anterior": "Recaudo Anterior",
    "Objeto_contrato": "Objeto Contrato (OC)",
    "runt": "Base RUNT",
    "novedades_sap": "Novedades SAP",
    "simulacion_base": "Simulación Base",
    "simulacion_comparar": "Simulación Comparar",
}

archivos_listos = 0
total_archivos = len(nombres_visibles)

for clave, nombre in nombres_visibles.items():
    if estado_archivos.get(clave, False):
        st.sidebar.success(f"✅ {nombre}")
        archivos_listos += 1
    else:
        st.sidebar.error(f"❌ {nombre} (Falta)")

st.sidebar.progress(archivos_listos / total_archivos)
st.sidebar.caption(f"Cargados: {archivos_listos} de {total_archivos} insumos")

if st.sidebar.button("🔄 Recargar Estado de Archivos"):
    st.rerun()

# ==============================================================================
# PESTAÑAS PRINCIPALES
# ==============================================================================
pestana_qa, pestana_cruce = st.tabs(
    ["QA Consolidado (Pesados/Local)", "Cruce Independiente"]
)

with pestana_qa:
    st.header("1. Parametrización")

    col1, col2 = st.columns(2)
    with col1:
        vigencia_evaluar = st.number_input(
            "Vigencia a Auditar:", value=2026, step=1
        )
    with col2:
        incluir_simulacion = st.checkbox(
            "Incluir Cruce de Simulaciones en el reporte final", value=True
        )

    st.subheader("2. Filtrado de Placas (Opcional)")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        texto_placas = st.text_input("Ingresar placas (separadas por coma):")
    with col_f2:
        excel_placas = st.file_uploader(
            "Cargar lista pequeña de Placas a auditar (Excel):", type=["xlsx"]
        )

    recaudos_listos = estado_archivos.get("recaudo_actual", False) and estado_archivos.get(
        "recaudo_anterior", False
    )

    if not recaudos_listos:
        st.warning(
            "⚠️ Revisa el panel izquierdo: los archivos de Recaudo Actual o Recaudo Anterior aún no han sido encontrados en la carpeta local."
        )

    if st.button("🚀 Ejecutar Auditoría desde Archivos Locales", type="primary", disabled=not recaudos_listos):
        with st.spinner("Cargando bases pesadas desde disco y procesando..."):
            rec_actual = cargar_dataframe_local("recaudo_actual")
            rec_anterior = cargar_dataframe_local("recaudo_anterior")
            oc_data = cargar_dataframe_local("Objeto_contrato")
            runt_data = cargar_dataframe_local("runt")
            nov_data = cargar_dataframe_local("novedades_sap")

            sim_base_df, sim_comp_df = None, None
            if incluir_simulacion:
                sim_base_df = cargar_dataframe_local("simulacion_base")
                sim_comp_df = cargar_dataframe_local("simulacion_comparar")

            rec_actual_filtrado = filtrar_por_placas(
                dataframe=rec_actual,
                columna_placa="Placa",
                texto_placas=texto_placas,
                archivo_excel=excel_placas,
            )

            resultado_qa = procesar_qa_liquidaciones(
                recaudo_actual=rec_actual_filtrado,
                recaudo_anterior=rec_anterior,
                Objeto_contrato=oc_data,
                runt=runt_data,
                novedades_sap=nov_data,
                sim_base=sim_base_df,
                sim_comp=sim_comp_df,
                anio_sim_base=vigencia_evaluar - 1,
                anio_sim_comp=vigencia_evaluar,
                vigencia_actual=vigencia_evaluar,
            )

            st.session_state["resultado_qa"] = resultado_qa

    if "resultado_qa" in st.session_state:
        df_res = st.session_state["resultado_qa"]

        st.markdown("---")
        st.header("📊 Vista Previa de los")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Placas Auditadas", len(df_res))
        m2.metric(
            "Cumplen Criterio",
            len(df_res[df_res["ESTADO_QA"] == "CUMPLE CRITERIOS DE VARIACION"]),
        )
        m3.metric(
            "No Cumplen Criterio",
            len(df_res[df_res["ESTADO_QA"] == "NO CUMPLE CRITERIOS DE VARIACION"]),
        )

        if "ESTADO_GRUPO" in df_res.columns:
            m4.metric(
                "Misma Tabla Simulación",
                len(df_res[df_res["ESTADO_GRUPO"] == "Misma Tabla"]),
            )

        st.dataframe(df_res, use_container_width=True)

        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
            df_res.to_excel(writer, index=False, sheet_name="Consolidado_QA")

        st.download_button(
            label="📥 Descargar Resultado Completo en Excel",
            data=output_excel.getvalue(),
            file_name=f"Consolidado_QA_Liquidaciones_{vigencia_evaluar}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with pestana_cruce:
    st.header("Cruce Independiente desde Disco")

    col_y1, col_y2 = st.columns(2)
    with col_y1:
        a_base = st.number_input("Año Base:", value=2025, step=1)
    with col_y2:
        a_comp = st.number_input("Año Comparar:", value=2026, step=1)

    if st.button("Ejecutar Solo Cruce de Simulaciones", type="primary"):
        s_base = cargar_dataframe_local("simulacion_base")
        s_comp = cargar_dataframe_local("simulacion_comparar")

        cruce_indep = cruzar_simulaciones_dinamico(
            simulacion_base=s_base,
            simulacion_comparar=s_comp,
            anio_base=a_base,
            anio_comparar=a_comp,
        )

        st.success(f"Cruce ejecutado exitosamente. Total registros: {len(cruce_indep)}")
        st.dataframe(cruce_indep, use_container_width=True)