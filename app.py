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
from python.simulation_vs_recaudo import (
    cruzar_simulacion_vs_recaudo_dinamico,
)

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
pestana_qa, pestana_cruce,pestana_recaudo_sim = st.tabs(
    ["QA Consolidado (Pesados/Local)", "Cruce Independiente","SIM_ACTUAL_PAGOS"]
)

with pestana_qa:
    st.header("1. Parametrización")

    col1, col2, col3 = st.columns(3)
    with col1:
        vigencia_evaluar = st.number_input(
            "Vigencia a Auditar:", value=2026, step=1
        )
    with col2:
        mes_seleccionado = st.selectbox(
            "Filtrar Mes Recaudo Actual (Opcional):",
            options=["Todos"] + list(range(1, 13)),
            index=0,
        )
    with col3:
        incluir_simulacion = st.checkbox(
            "Incluir Cruce de Simulaciones en el reporte final", value=True
        )

    # Convertir 'Todos' a None para el procesador
    mes_evaluar = None if mes_seleccionado == "Todos" else int(mes_seleccionado)

    st.subheader("2. Filtrado de Placas (Opcional)")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        texto_placas = st.text_input("Ingresar placas (separadas por coma):")
    with col_f2:
        excel_placas = st.file_uploader(
            "Cargar lista pequeña de Placas a auditar (Excel):", type=["xlsx"]
        )

    recaudos_listos = estado_archivos.get(
        "recaudo_actual", False
    ) and estado_archivos.get("recaudo_anterior", False)

    if not recaudos_listos:
        st.warning(
            "⚠️ Revisa el panel izquierdo: los archivos de Recaudo Actual o Recaudo Anterior aún no han sido encontrados en la carpeta local."
        )

    if st.button(
        "🚀 Ejecutar Auditoría desde Archivos Locales",
        type="primary",
        disabled=not recaudos_listos,
    ):
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

            # Llamada corregida sin el argumento erróneo
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
                mes_evaluar=mes_evaluar,
            )

            st.session_state["resultado_qa"] = resultado_qa

    if "resultado_qa" in st.session_state:
        df_res = st.session_state["resultado_qa"]

        st.markdown("---")
        st.header("📊 Vista Previa de los Resultados")

        # ==============================================================================
        # DIAGNÓSTICO RÁPIDO DE COLUMNAS QA
        # ==============================================================================
        print(df_res.columns)
        col_diag1, col_diag2 = st.columns(2)
        with col_diag1:
            if "ESTADO_AVALUO_ACTUAL_VS_SIM" in df_res.columns:
                st.success(
                    "✅ Columna 'ESTADO_AVALUO_ACTUAL_VS_SIM' presente."
                )
            else:
                st.error(
                    "❌ La columna 'ESTADO_AVALUO_ACTUAL_VS_SIM' NO se generó en el procesador."
                )

        with col_diag2:
            if "ESTADO_AVALUO_ACTUAL_VS_SIM" in df_res.columns:
                conteo_nulos = df_res[
                    "ESTADO_AVALUO_ACTUAL_VS_SIM"
                ].isna().sum()
                st.caption(
                    f"Registros nulos en Avalúo vs SIM: {conteo_nulos} / {len(df_res)}"
                )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Placas Auditadas", len(df_res))

        if "ESTADO_QA" in df_res.columns:
            m2.metric(
                "Cumplen Criterio",
                len(
                    df_res[
                        df_res["ESTADO_QA"] == "CUMPLE CRITERIOS DE VARIACION"
                    ]
                ),
            )
            m3.metric(
                "No Cumplen Criterio",
                len(
                    df_res[
                        df_res["ESTADO_QA"]
                        == "NO CUMPLE CRITERIOS DE VARIACION"
                    ]
                ),
            )

        if "ESTADO_GRUPO_SIM" in df_res.columns:
            m4.metric(
                "Misma Tabla Simulación",
                len(df_res[df_res["ESTADO_GRUPO_SIM"] == "Misma Tabla"]),
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

        st.session_state["cruce_indep"] = cruzar_simulaciones_dinamico(
            simulacion_base=s_base,
            simulacion_comparar=s_comp,
            anio_base=a_base,
            anio_comparar=a_comp,
        )

    if "cruce_indep" in st.session_state and not st.session_state["cruce_indep"].empty:
        df_cruce = st.session_state["cruce_indep"]

        st.success(
            f"Cruce ejecutado exitosamente. Total registros: {len(df_cruce)}"
        )

        # ----------------------------------------------------------------------
        # FILTROS DINÁMICOS
        # ----------------------------------------------------------------------
        st.subheader("Filtros de Exploración")
        col_f1, col_f2 = st.columns(2)

        df_filtrado = df_cruce.copy()

        with col_f1:
            filtro_placa = st.text_input("Filtrar por Placa (contiene):", "").strip().upper()
            if filtro_placa:
                df_filtrado = df_filtrado[
                    df_filtrado["Placa"].str.contains(filtro_placa, na=False)
                ]

        with col_f2:
            if "ESTADO_AVALUO_SIM" in df_cruce.columns:
                opciones_estado = df_cruce["ESTADO_AVALUO_SIM"].dropna().unique().tolist()
                filtro_estado = st.multiselect(
                    "Filtrar por ESTADO_AVALUO_SIM:",
                    options=opciones_estado,
                    default=opciones_estado,
                )
                if filtro_estado:
                    df_filtrado = df_filtrado[
                        df_filtrado["ESTADO_AVALUO_SIM"].isin(filtro_estado)
                    ]

        st.dataframe(df_filtrado, use_container_width=True)

        # ----------------------------------------------------------------------
        # DESCARGA EN PARQUET
        # ----------------------------------------------------------------------
        parquet_bytes = df_filtrado.to_parquet(index=False)

        st.download_button(
            label="📦 Descargar Resultado en Parquet",
            data=parquet_bytes,
            file_name=f"cruce_simulaciones_{a_base}_{a_comp}.parquet",
            mime="application/octet-stream",
        )
    elif "cruce_indep" in st.session_state and st.session_state["cruce_indep"].empty:
        st.warning("El cruce no generó registros. Verifica los encabezados de 'Placa' y 'Avalúo' en los archivos cargados.")


with pestana_recaudo_sim:
    st.header("Cruce Recaudo Anterior vs. Simulación Actual")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        a_rec = st.number_input("Año Recaudo:", value=2025, step=1)
    with col_r2:
        a_sim = st.number_input("Año Simulación:", value=2026, step=1)

    if st.button("Ejecutar Cruce Recaudo vs Simulación", type="primary"):
        df_recaudo_disco = cargar_dataframe_local("recaudo_anterior")
        df_sim_disco = cargar_dataframe_local("simulacion_comparar")

        st.session_state["cruce_rec_sim"] = cruzar_simulacion_vs_recaudo_dinamico(
            df_recaudo=df_recaudo_disco,
            df_simulacion=df_sim_disco,
            anio_recaudo=a_rec,
            anio_simulacion=a_sim,
        )

    if "cruce_rec_sim" in st.session_state and not st.session_state["cruce_rec_sim"].empty:
        df_rs = st.session_state["cruce_rec_sim"]

        st.success(f"Cruce ejecutado exitosamente. Total registros: {len(df_rs)}")

        # ----------------------------------------------------------------------
        # FILTROS
        # ----------------------------------------------------------------------
        st.subheader("Filtros de Exploración")
        col_f1, col_f2 = st.columns(2)

        df_filtrado_rs = df_rs.copy()

        m1, m2 = st.columns(2)
        
        if "ESTADO_AVALUO_RECAUDO_VS_SIM" in df_filtrado_rs.columns:
            m1.metric(
                        "Cumplen Criterio",
                        len(
                            df_filtrado_rs[
                                df_filtrado_rs["ESTADO_AVALUO_RECAUDO_VS_SIM"] == "CUMPLE LIMITE INFERIOR"
                            ]
                        ),
                    )
            m2.metric(
                        "No Cumplen Criterio",
                        len(
                            df_filtrado_rs[
                                df_filtrado_rs["ESTADO_AVALUO_RECAUDO_VS_SIM"]
                                == "NO CUMPLE LIMITE INFERIOR"
                            ]
                        ),
                    )

        with col_f1:
            filtro_placa_rs = st.text_input("Filtrar por Placa (contiene):", "", key="placa_rs").strip().upper()
            if filtro_placa_rs:
                df_filtrado_rs = df_filtrado_rs[
                    df_filtrado_rs["Placa"].str.contains(filtro_placa_rs, na=False)
                ]

        with col_f2:
            col_estado = "ESTADO_AVALUO_RECAUDO_VS_SIM"
            if col_estado in df_rs.columns:
                opciones_estado_rs = df_rs[col_estado].dropna().unique().tolist()
                filtro_estado_rs = st.multiselect(
                    f"Filtrar por {col_estado}:",
                    options=opciones_estado_rs,
                    default=opciones_estado_rs,
                    key="estado_rs"
                )
                if filtro_estado_rs:
                    df_filtrado_rs = df_filtrado_rs[
                        df_filtrado_rs[col_estado].isin(filtro_estado_rs)
                    ]

        st.dataframe(df_filtrado_rs, use_container_width=True)

        # ----------------------------------------------------------------------
        # DESCARGA EN PARQUET
        # ----------------------------------------------------------------------
        parquet_bytes_rs = df_filtrado_rs.to_parquet(index=False)

        st.download_button(
            label="📦 Descargar Resultado en Parquet",
            data=parquet_bytes_rs,
            file_name=f"cruce_recaudo_{a_rec}_vs_simulacion_{a_sim}.parquet",
            mime="application/octet-stream",
            key="btn_dl_rs"
        )
    elif "cruce_rec_sim" in st.session_state and st.session_state["cruce_rec_sim"].empty:
        st.warning("El cruce no generó registros. Verifica que los archivos tengan columnas válidas para Placa y Avalúo.")