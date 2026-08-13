"""Módulo para el cruce dinámico entre Simulación Actual y Recaudo Anterior."""

import numpy as np
import pandas as pd


def _limpiar_columnas_duplicadas(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Conserva solo la primera aparición de columnas duplicadas."""
    if dataframe is None or dataframe.empty:
        return dataframe
    return dataframe.loc[:, ~dataframe.columns.duplicated()].copy()


def _obtener_nombre_columna(
    dataframe: pd.DataFrame, opciones: list[str]
) -> str | None:
    """Busca cuál encabezado coincide con las opciones dadas."""
    columnas_limpias = {col.strip().upper(): col for col in dataframe.columns}
    for opcion in opciones:
        opcion_upper = opcion.upper()
        if opcion_upper in columnas_limpias:
            return columnas_limpias[opcion_upper]
    return None


def _normalizar_placa(serie: pd.Series) -> pd.Series:
    """Normaliza la columna de placa: mayúsculas, quita espacios y guiones."""
    return (
        serie.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"[\s\-]", "", regex=True)
    )


def _limpiar_monto_texto(serie: pd.Series) -> pd.Series:
    """Convierte cadenas con formato '55.671.000,00' o numéricos a floats limpios."""
    if serie is None:
        return pd.Series(dtype=float)

    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    serie_clean = (
        serie.astype(str)
        .str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(serie_clean, errors="coerce")


def _normalizar_escala_simulacion(
    val_base: pd.Series, val_comp: pd.Series
) -> pd.Series:
    """Ajusta la escala de la simulación respecto al recaudo si vienen en escalas distintas."""
    val_base_clean = _limpiar_monto_texto(val_base).fillna(0)
    val_comp_clean = _limpiar_monto_texto(val_comp).fillna(0)

    proporcion = np.where(
        val_base_clean > 0, val_comp_clean / val_base_clean, 1.0
    )

    # Caso 1: La simulación viene dividida por 100
    val_comp_ajustado = np.where(
        (proporcion >= 0.008) & (proporcion <= 0.012),
        val_comp_clean * 100.0,
        val_comp_clean,
    )

    # Caso 2: La simulación viene multiplicada por 100
    proporcion_adj1 = np.where(
        val_base_clean > 0, val_comp_ajustado / val_base_clean, 1.0
    )
    val_comp_ajustado = np.where(
        (proporcion_adj1 >= 80) & (proporcion_adj1 <= 120),
        val_comp_ajustado / 100.0,
        val_comp_ajustado,
    )

    # Caso 3: Desfase por factor 10
    proporcion_adj2 = np.where(
        val_base_clean > 0, val_comp_ajustado / val_base_clean, 1.0
    )
    val_comp_ajustado = np.where(
        (proporcion_adj2 >= 8) & (proporcion_adj2 <= 12),
        val_comp_ajustado / 10.0,
        np.where(
            (proporcion_adj2 >= 0.08) & (proporcion_adj2 <= 0.12),
            val_comp_ajustado * 10.0,
            val_comp_ajustado,
        ),
    )

    return pd.Series(val_comp_ajustado, index=val_comp.index)


def cruzar_simulacion_vs_recaudo_dinamico(
    df_recaudo: pd.DataFrame,
    df_simulacion: pd.DataFrame,
    anio_recaudo: int = 2025,
    anio_simulacion: int = 2026,
    porcentaje_limite_inferior: float = -20.0,
) -> pd.DataFrame:
    """Cruza Recaudo Anterior vs. Simulación Actual evaluando grupos, avalúos y límite de caída."""
    if df_recaudo is None or df_recaudo.empty:
        return pd.DataFrame()
    if df_simulacion is None or df_simulacion.empty:
        return pd.DataFrame()

    rec = _limpiar_columnas_duplicadas(df_recaudo)
    sim = _limpiar_columnas_duplicadas(df_simulacion)

    # 1. Mapeo de Placa
    posibles_placas = ["PLACA", "PLACA_VEHICULO", "PLACA_SIM", "PLACA_VEH"]
    col_placa_rec = _obtener_nombre_columna(rec, posibles_placas)
    col_placa_sim = _obtener_nombre_columna(sim, posibles_placas)

    if not col_placa_rec or not col_placa_sim:
        return pd.DataFrame()

    # 2. Mapeo de Grupo / Tabla
    posibles_grupos = ["GRUPO", "GRUPO_LIQUIDACION", "TABLA", "GRUPO_TABLA", "CLASE"]
    col_grupo_rec = _obtener_nombre_columna(rec, posibles_grupos)
    col_grupo_sim = _obtener_nombre_columna(sim, posibles_grupos)

    # 3. Mapeo de Avalúo
    posibles_avaluos_rec = ["AVALUO", "VALOR_AVALUO", "AVALUO_RECAUDO", "VALOR_BASE"]
    posibles_avaluos_sim = ["AVALUO", "VALOR_AVALUO", "AVALUO_SIM", "AVALUO_LIQUIDADO"]
    col_avaluo_rec = _obtener_nombre_columna(rec, posibles_avaluos_rec)
    col_avaluo_sim = _obtener_nombre_columna(sim, posibles_avaluos_sim)

    # Preparar DataFrames
    rec = rec.rename(columns={col_placa_rec: "Placa"}).copy()
    sim = sim.rename(columns={col_placa_sim: "Placa"}).copy()

    rec["Placa"] = _normalizar_placa(rec["Placa"])
    sim["Placa"] = _normalizar_placa(sim["Placa"])

    rec_unicas = rec.drop_duplicates(["Placa"], keep="last")
    sim_unicas = sim.drop_duplicates(["Placa"], keep="last")

    # Mapeo de columnas a exportar
    cols_rec = ["Placa"]
    if col_grupo_rec and col_grupo_rec in rec_unicas.columns:
        rec_unicas = rec_unicas.rename(columns={col_grupo_rec: f"Grupo_Recaudo_{anio_recaudo}"})
        cols_rec.append(f"Grupo_Recaudo_{anio_recaudo}")
    if col_avaluo_rec and col_avaluo_rec in rec_unicas.columns:
        rec_unicas = rec_unicas.rename(columns={col_avaluo_rec: f"Avaluo_Recaudo_{anio_recaudo}"})
        cols_rec.append(f"Avaluo_Recaudo_{anio_recaudo}")

    cols_sim = ["Placa"]
    if col_grupo_sim and col_grupo_sim in sim_unicas.columns:
        sim_unicas = sim_unicas.rename(columns={col_grupo_sim: f"Grupo_Sim_{anio_simulacion}"})
        cols_sim.append(f"Grupo_Sim_{anio_simulacion}")
    if col_avaluo_sim and col_avaluo_sim in sim_unicas.columns:
        sim_unicas = sim_unicas.rename(columns={col_avaluo_sim: f"Avaluo_Sim_{anio_simulacion}"})
        cols_sim.append(f"Avaluo_Sim_{anio_simulacion}")

    cruce = rec_unicas[cols_rec].merge(sim_unicas[cols_sim], on="Placa", how="inner")

    # Evaluación de Grupo (Misma Tabla / Cambio de Tabla)
    col_gr = f"Grupo_Recaudo_{anio_recaudo}"
    col_gs = f"Grupo_Sim_{anio_simulacion}"

    if col_gr in cruce.columns and col_gs in cruce.columns:
        grupo_rec_limpio = cruce[col_gr].fillna("").astype(str).str.strip().str.upper().str[0]
        grupo_sim_limpio = cruce[col_gs].fillna("").astype(str).str.strip().str.upper().str[0]

        cruce["ESTADO_GRUPO_RECAUDO_VS_SIM"] = np.where(
            grupo_rec_limpio == grupo_sim_limpio,
            "Misma Tabla",
            "Cambio de Tabla",
        )

    # Evaluación de Avalúos y Límites
    col_ar = f"Avaluo_Recaudo_{anio_recaudo}"
    col_as = f"Avaluo_Sim_{anio_simulacion}"

    if col_ar in cruce.columns and col_as in cruce.columns:
        av_rec_num = _limpiar_monto_texto(cruce[col_ar]).fillna(0)
        av_sim_raw = _limpiar_monto_texto(cruce[col_as]).fillna(0)

        # Normalizar escala de la Simulación comparada contra el Recaudo
        av_sim_num = _normalizar_escala_simulacion(av_rec_num, av_sim_raw)
        cruce[col_as] = av_sim_num

        cruce["VAR_AVALUO_RECAUDO_VS_SIM"] = np.where(
            av_rec_num > 0,
            ((av_sim_num - av_rec_num) / av_rec_num) * 100,
            0,
        )

        cruce["LIMITE_INFERIOR_RECAUDO"] = av_rec_num * (1 + (porcentaje_limite_inferior / 100))

        cruce["ESTADO_AVALUO_RECAUDO_VS_SIM"] = np.where(
            av_sim_num >= cruce["LIMITE_INFERIOR_RECAUDO"],
            "CUMPLE LIMITE INFERIOR",
            "NO CUMPLE LIMITE INFERIOR",
        )

    return cruce