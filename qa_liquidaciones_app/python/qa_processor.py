"""Módulo de procesamiento y auditoría de QA para liquidaciones y simulaciones."""

from typing import Optional
import numpy as np
import pandas as pd

from .simulation_cross import cruzar_simulaciones_dinamico


def _limpiar_monto_texto(serie: pd.Series) -> pd.Series:
    """Convierte cadenas con formato '55.671.000,00' o numéricos a floats limpios."""
    if serie is None:
        return pd.Series(dtype=float)

    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    # Limpia formato latino/colombiano: quita puntos de miles y cambia coma decimal por punto
    serie_clean = (
        serie.astype(str)
        .str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(serie_clean, errors="coerce")


def _estandarizar_columna_placa(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Asegura la existencia de la columna 'Placa' y elimina encabezados repetidos."""
    if dataframe is None or dataframe.empty:
        return dataframe

    dataframe = dataframe.loc[:, ~dataframe.columns.duplicated()].copy()
    dataframe.columns = dataframe.columns.str.strip()

    renombres = {}
    for col in dataframe.columns:
        col_clean = col.upper()
        if col_clean in ["PLACA", "PLACA_VEHICULO", "PLACA_OC", "PLACA_VEH"]:
            if col != "Placa":
                renombres[col] = "Placa"

    if renombres:
        dataframe = dataframe.rename(columns=renombres)
        dataframe = dataframe.loc[:, ~dataframe.columns.duplicated()].copy()

    return dataframe


def _normalizar_escala_simulacion(
    val_real: pd.Series, val_sim: pd.Series
) -> pd.Series:
    """Ajusta valores simulados según su desfase respecto al avalúo real."""
    val_real_clean = _limpiar_monto_texto(val_real).fillna(0)
    val_sim_clean = _limpiar_monto_texto(val_sim).fillna(0)

    # Calcular la proporción entre lo simulado y lo real
    proporcion = np.where(
        val_real_clean > 0, val_sim_clean / val_real_clean, 1.0
    )

    # Caso 1: La simulación viene dividida por 100 o desplazada 2 ceros hacia abajo
    # Ej: Real = 58.566.000, Sim = 585.660 -> proporcion ~= 0.01 (entre 0.008 y 0.012)
    val_sim_ajustado = np.where(
        (proporcion >= 0.008) & (proporcion <= 0.012),
        val_sim_clean * 100.0,
        val_sim_clean,
    )

    # Recalcular proporción tras el primer ajuste
    proporcion_adj1 = np.where(
        val_real_clean > 0, val_sim_ajustado / val_real_clean, 1.0
    )

    # Caso 2: La simulación viene multiplicada por 100 (2 decimales implícitos sin coma)
    # Ej: Real = 585.660, Sim = 58.566.000 -> proporcion ~= 100
    val_sim_ajustado = np.where(
        (proporcion_adj1 >= 80) & (proporcion_adj1 <= 120),
        val_sim_ajustado / 100.0,
        val_sim_ajustado,
    )

    # Recalcular proporción tras el segundo ajuste
    proporcion_adj2 = np.where(
        val_real_clean > 0, val_sim_ajustado / val_real_clean, 1.0
    )

    # Caso 3: Ajuste secundario si viene desplazada por factor 10
    val_sim_ajustado = np.where(
        (proporcion_adj2 >= 8) & (proporcion_adj2 <= 12),
        val_sim_ajustado / 10.0,
        np.where(
            (proporcion_adj2 >= 0.08) & (proporcion_adj2 <= 0.12),
            val_sim_ajustado * 10.0,
            val_sim_ajustado,
        ),
    )

    return pd.Series(val_sim_ajustado, index=val_sim.index)


def calcular_variacion_avaluo_dinamico(
    recaudo_actual: pd.DataFrame,
    recaudo_anterior: pd.DataFrame,
    orden_compra: pd.DataFrame,
    runt: pd.DataFrame,
    vigencia_actual: int,
    mes_evaluar: Optional[int] = None,
    fecha_inicio: Optional[pd.Timestamp] = None,
    fecha_fin: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Calcula la variación de avalúo entre vigencias integrando OC y RUNT.

    Permite filtrar el recaudo actual por mes (comportamiento original) y/o
    por un rango de días [fecha_inicio, fecha_fin] (ambos inclusive), usando
    la misma columna de fecha detectada automáticamente.
    """
    if recaudo_actual is None or recaudo_actual.empty:
        return pd.DataFrame()

    recaudo_actual = _estandarizar_columna_placa(recaudo_actual)
    recaudo_anterior = _estandarizar_columna_placa(recaudo_anterior)
    orden_compra = _estandarizar_columna_placa(orden_compra)
    runt = _estandarizar_columna_placa(runt)

    # --------------------------------------------------------------------------
    # FILTRADO DE RECAUDO ACTUAL POR MES Y/O RANGO DE DÍAS
    # --------------------------------------------------------------------------
    hay_filtro_fecha = (
        mes_evaluar is not None
        or fecha_inicio is not None
        or fecha_fin is not None
    )

    if hay_filtro_fecha and not recaudo_actual.empty:
        col_fecha = None
        for col in recaudo_actual.columns:
            col_norm = col.strip().lower()
            if col_norm in [
                "fecha_de_pago",
                "fecha_pago",
                "fechapago",
                "mes",
                "mes_pago",
                "mes_recaudo",
            ]:
                col_fecha = col
                break

        if col_fecha:
            fechas_convertidas = pd.to_datetime(
                recaudo_actual[col_fecha], format="%d/%m/%Y", errors="coerce"
            )

            if fechas_convertidas.isna().all():
                fechas_convertidas = pd.to_datetime(
                    recaudo_actual[col_fecha], dayfirst=True, errors="coerce"
                )

            if not fechas_convertidas.isna().all():
                # La columna sí se pudo interpretar como fecha real:
                # aquí se puede aplicar mes y/o rango de días.
                mascara = pd.Series(True, index=recaudo_actual.index)

                if mes_evaluar is not None:
                    mascara &= fechas_convertidas.dt.month == int(mes_evaluar)

                if fecha_inicio is not None:
                    mascara &= fechas_convertidas.dt.normalize() >= pd.Timestamp(
                        fecha_inicio
                    )

                if fecha_fin is not None:
                    mascara &= fechas_convertidas.dt.normalize() <= pd.Timestamp(
                        fecha_fin
                    )

                recaudo_actual = recaudo_actual[mascara].copy()
            elif mes_evaluar is not None:
                # Fallback original: la columna no es una fecha real (p. ej.
                # viene como número/texto de mes). El rango de días no aplica
                # en este caso porque no hay información de día disponible.
                serie_mes = (
                    recaudo_actual[col_fecha]
                    .astype(str)
                    .str.extract(r"(\d+)")[0]
                )
                serie_mes_num = pd.to_numeric(serie_mes, errors="coerce")
                recaudo_actual = recaudo_actual[
                    serie_mes_num == int(mes_evaluar)
                ].copy()

    if recaudo_actual.empty:
        return pd.DataFrame()

    oc_limpio = (
        orden_compra.drop_duplicates(["Placa"], keep="last")
        if orden_compra is not None
        and not orden_compra.empty
        and "Placa" in orden_compra.columns
        else pd.DataFrame(columns=["Placa"])
    )

    runt_limpio = (
        runt.drop_duplicates(["Placa"], keep="last")
        if runt is not None
        and not runt.empty
        and "Placa" in runt.columns
        else pd.DataFrame(columns=["Placa"])
    )

    consolidado = recaudo_actual.copy()

    if (
        recaudo_anterior is not None
        and not recaudo_anterior.empty
        and "Placa" in recaudo_anterior.columns
    ):
        rec_ant_unicas = recaudo_anterior.drop_duplicates(
            ["Placa"], keep="last"
        )
        consolidado = consolidado.merge(
            rec_ant_unicas,
            on="Placa",
            how="left",
            suffixes=("", "_ANT"),
        )

    if not oc_limpio.empty:
        consolidado = consolidado.merge(
            oc_limpio, on="Placa", how="left", suffixes=("", "_OC")
        )

    if not runt_limpio.empty:
        consolidado = consolidado.merge(
            runt_limpio, on="Placa", how="left", suffixes=("", "_RUNT")
        )

    col_act = None
    col_ant = None

    for col in consolidado.columns:
        col_clean = col.strip().upper()
        if col_clean in [
            "AVALUO",
            "AVALUO_ACTUAL",
            f"AVALUO_{vigencia_actual}",
        ]:
            col_act = col
        elif col_clean in [
            "AVALUO_ANT",
            "AVALUO_ANTERIOR",
            f"AVALUO_{vigencia_actual - 1}",
        ]:
            col_ant = col

    if col_act and col_ant:
        avaluo_act_num = _limpiar_monto_texto(consolidado[col_act]).fillna(0)
        avaluo_ant_num = _limpiar_monto_texto(consolidado[col_ant]).fillna(0)

        consolidado["VAR_AVALUO"] = np.where(
            avaluo_ant_num > 0,
            ((avaluo_act_num - avaluo_ant_num) / avaluo_ant_num) * 100,
            0,
        )

    return consolidado


def evaluar_criterios_qa(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Evalúa criterios de variación e identifica desviaciones por debajo o arriba del 20%."""
    if dataframe is None or dataframe.empty:
        return dataframe

    resultado = dataframe.copy()

    if "VAR_AVALUO" in resultado.columns:
        condicion_cumple = (resultado["VAR_AVALUO"] >= -50) & (
            resultado["VAR_AVALUO"] <= 50
        )
        resultado["ESTADO_QA"] = np.where(
            condicion_cumple,
            "CUMPLE CRITERIOS DE VARIACION",
            "NO CUMPLE CRITERIOS DE VARIACION",
        )

        condiciones_detalle = [
            resultado["VAR_AVALUO"] < -20,
            resultado["VAR_AVALUO"] > 20,
        ]
        opciones_detalle = [
            "Inferior a -20%",
            "Superior a +20%",
        ]

        resultado["DETALLE_VARIACION"] = np.select(
            condiciones_detalle,
            opciones_detalle,
            default="Dentro del rango +/-20%",
        )
    else:
        resultado["ESTADO_QA"] = "SIN EVALUAR"
        resultado["DETALLE_VARIACION"] = "SIN EVALUAR"

    return resultado


def procesar_qa_liquidaciones(
    recaudo_actual: pd.DataFrame,
    recaudo_anterior: pd.DataFrame,
    Objeto_contrato: Optional[pd.DataFrame] = None,
    orden_compra: Optional[pd.DataFrame] = None,
    runt: Optional[pd.DataFrame] = None,
    novedades_sap: Optional[pd.DataFrame] = None,
    sim_base: Optional[pd.DataFrame] = None,
    sim_comp: Optional[pd.DataFrame] = None,
    anio_sim_base: int = 2025,
    anio_sim_comp: int = 2026,
    vigencia_actual: int = 2026,
    mes_evaluar: Optional[int] = None,
    fecha_inicio: Optional[pd.Timestamp] = None,
    fecha_fin: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Función principal para el procesamiento consolidado de QA.

    fecha_inicio / fecha_fin: rango de días (ambos inclusive) para filtrar
    el recaudo actual, adicional/compatible con mes_evaluar.
    """
    oc_df = Objeto_contrato if Objeto_contrato is not None else orden_compra

    datos_consolidados = calcular_variacion_avaluo_dinamico(
        recaudo_actual=recaudo_actual,
        recaudo_anterior=recaudo_anterior,
        orden_compra=oc_df,
        runt=runt,
        vigencia_actual=vigencia_actual,
        mes_evaluar=mes_evaluar,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

    if datos_consolidados.empty:
        return pd.DataFrame()

    resultado_qa = evaluar_criterios_qa(datos_consolidados)

    # Cruce e integración de simulaciones
    if (
        sim_base is not None
        and sim_comp is not None
        and not sim_base.empty
        and not sim_comp.empty
    ):
        cruce_simulaciones = cruzar_simulaciones_dinamico(
            simulacion_base=sim_base,
            simulacion_comparar=sim_comp,
            anio_base=anio_sim_base,
            anio_comparar=anio_sim_comp,
        )

        if not cruce_simulaciones.empty and "Placa" in cruce_simulaciones.columns:
            cruce_sim_unicas = cruce_simulaciones.drop_duplicates(
                ["Placa"], keep="last"
            )
            resultado_qa = resultado_qa.merge(
                cruce_sim_unicas,
                on="Placa",
                how="left",
                suffixes=("", "_SIM"),
            )

            # ------------------------------------------------------------------
            # COMPARACIÓN GENERALIZADA DE AVALÚOS REALES VS SIMULACIÓN
            # ------------------------------------------------------------------
            col_act_real = (
                "Avaluo"
                if "Avaluo" in resultado_qa.columns
                else f"Avaluo_{vigencia_actual}"
            )
            col_act_sim = f"Avaluo_Sim_{anio_sim_comp}"

            col_ant_real = (
                "Avaluo_ANT"
                if "Avaluo_ANT" in resultado_qa.columns
                else f"Avaluo_{vigencia_actual - 1}"
            )
            col_ant_sim = f"Avaluo_Sim_{anio_sim_base}"

            # 1. Comparar Vigencia Actual (ej. 2026 vs Sim 2026)
            if (
                col_act_real in resultado_qa.columns
                and col_act_sim in resultado_qa.columns
            ):
                av_act_real = _limpiar_monto_texto(
                    resultado_qa[col_act_real]
                ).fillna(0)

                av_act_sim_norm = _normalizar_escala_simulacion(
                    av_act_real, resultado_qa[col_act_sim]
                )

                resultado_qa["AVALUO_SIM_ACTUAL_NORM"] = av_act_sim_norm
                resultado_qa["DIF_PCT_AVALUO_ACTUAL"] = np.where(
                    av_act_real > 0,
                    ((av_act_sim_norm - av_act_real) / av_act_real) * 100,
                    np.nan,
                )
                resultado_qa["ESTADO_AVALUO_ACTUAL_VS_SIM"] = np.where(
                    resultado_qa["DIF_PCT_AVALUO_ACTUAL"].abs() <= 1,
                    "COINCIDE",
                    "DIFERENTE",
                )

            # 2. Comparar Vigencia Anterior (ej. 2025 vs Sim 2025)
            if (
                col_ant_real in resultado_qa.columns
                and col_ant_sim in resultado_qa.columns
            ):
                av_ant_real = _limpiar_monto_texto(
                    resultado_qa[col_ant_real]
                ).fillna(0)

                av_ant_sim_norm = _normalizar_escala_simulacion(
                    av_ant_real, resultado_qa[col_ant_sim]
                )

                resultado_qa["AVALUO_SIM_ANT_NORM"] = av_ant_sim_norm
                resultado_qa["DIF_PCT_AVALUO_ANT"] = np.where(
                    av_ant_real > 0,
                    ((av_ant_sim_norm - av_ant_real) / av_ant_real) * 100,
                    np.nan,
                )
                resultado_qa["ESTADO_AVALUO_ANT_VS_SIM"] = np.where(
                    resultado_qa["DIF_PCT_AVALUO_ANT"].abs() <= 1,
                    "COINCIDE",
                    "DIFERENTE",
                )

    return resultado_qa