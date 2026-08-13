"""Módulo para el cruce dinámico de simulaciones entre vigencias."""

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

    # Limpia formato latino/colombiano: quita puntos de miles y cambia coma decimal por punto
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
    """Ajusta la escala del avalúo comparado respecto al avalúo base si vienen en escalas distintas."""
    val_base_clean = _limpiar_monto_texto(val_base).fillna(0)
    val_comp_clean = _limpiar_monto_texto(val_comp).fillna(0)

    # Calcular la proporción entre lo comparado y lo base
    proporcion = np.where(
        val_base_clean > 0, val_comp_clean / val_base_clean, 1.0
    )

    # Caso 1: La simulación a comparar viene dividida por 100 o le faltan 2 ceros
    # Ej: Base = 58.566.000, Comp = 585.660 -> proporcion ~= 0.01
    val_comp_ajustado = np.where(
        (proporcion >= 0.008) & (proporcion <= 0.012),
        val_comp_clean * 100.0,
        val_comp_clean,
    )

    # Recalcular proporción tras el primer ajuste
    proporcion_adj1 = np.where(
        val_base_clean > 0, val_comp_ajustado / val_base_clean, 1.0
    )

    # Caso 2: La simulación a comparar viene multiplicada por 100 (2 decimales implícitos)
    # Ej: Base = 585.660, Comp = 58.566.000 -> proporcion ~= 100
    val_comp_ajustado = np.where(
        (proporcion_adj1 >= 80) & (proporcion_adj1 <= 120),
        val_comp_ajustado / 100.0,
        val_comp_ajustado,
    )

    # Recalcular proporción tras el segundo ajuste
    proporcion_adj2 = np.where(
        val_base_clean > 0, val_comp_ajustado / val_base_clean, 1.0
    )

    # Caso 3: Ajuste secundario si viene desplazada por factor 10
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


def cruzar_simulaciones_dinamico(
    simulacion_base: pd.DataFrame,
    simulacion_comparar: pd.DataFrame,
    anio_base: int = 2025,
    anio_comparar: int = 2026,
    porcentaje_limite_inferior: float = -20.0,
) -> pd.DataFrame:
    """Cruza simulaciones evaluando cambio de grupo y límites de avalúo con escala normalizada."""
    if simulacion_base is None or simulacion_base.empty:
        return pd.DataFrame()
    if simulacion_comparar is None or simulacion_comparar.empty:
        return pd.DataFrame()

    sim_base = _limpiar_columnas_duplicadas(simulacion_base)
    sim_comp = _limpiar_columnas_duplicadas(simulacion_comparar)

    # Identificar columna Placa
    posibles_placas = ["PLACA", "PLACA_VEHICULO", "PLACA_SIM", "PLACA_VEH"]
    col_placa_base = _obtener_nombre_columna(sim_base, posibles_placas)
    col_placa_comp = _obtener_nombre_columna(sim_comp, posibles_placas)

    if not col_placa_base or not col_placa_comp:
        return pd.DataFrame()

    # Identificar columna Grupo / Tabla
    posibles_grupos = ["GRUPO", "GRUPO_LIQUIDACION", "TABLA", "GRUPO_TABLA", "CLASE"]
    col_grupo_base = _obtener_nombre_columna(sim_base, posibles_grupos)
    col_grupo_comp = _obtener_nombre_columna(sim_comp, posibles_grupos)

    # Identificar columna Avalúo
    posibles_avaluos = ["AVALUO", "VALOR_AVALUO", "AVALUO_SIM", "AVALUO_LIQUIDADO"]
    col_avaluo_base = _obtener_nombre_columna(sim_base, posibles_avaluos)
    col_avaluo_comp = _obtener_nombre_columna(sim_comp, posibles_avaluos)

    df_base = sim_base.rename(columns={col_placa_base: "Placa"}).copy()
    df_comp = sim_comp.rename(columns={col_placa_comp: "Placa"}).copy()

    df_base = _limpiar_columnas_duplicadas(df_base)
    df_comp = _limpiar_columnas_duplicadas(df_comp)

    # Normalización de Placa previa a la deduplicación y al cruce
    df_base["Placa"] = _normalizar_placa(df_base["Placa"])
    df_comp["Placa"] = _normalizar_placa(df_comp["Placa"])

    base_unicas = df_base.drop_duplicates(["Placa"], keep="last")
    comp_unicas = df_comp.drop_duplicates(["Placa"], keep="last")

    # Mapear columnas para el subconjunto de cruce
    cols_base = ["Placa"]
    if col_grupo_base and col_grupo_base in base_unicas.columns:
        base_unicas = base_unicas.rename(columns={col_grupo_base: f"Grupo_{anio_base}"})
        cols_base.append(f"Grupo_{anio_base}")
    if col_avaluo_base and col_avaluo_base in base_unicas.columns:
        base_unicas = base_unicas.rename(columns={col_avaluo_base: f"Avaluo_Sim_{anio_base}"})
        cols_base.append(f"Avaluo_Sim_{anio_base}")

    cols_comp = ["Placa"]
    if col_grupo_comp and col_grupo_comp in comp_unicas.columns:
        comp_unicas = comp_unicas.rename(columns={col_grupo_comp: f"Grupo_{anio_comparar}"})
        cols_comp.append(f"Grupo_{anio_comparar}")
    if col_avaluo_comp and col_avaluo_comp in comp_unicas.columns:
        comp_unicas = comp_unicas.rename(columns={col_avaluo_comp: f"Avaluo_Sim_{anio_comparar}"})
        cols_comp.append(f"Avaluo_Sim_{anio_comparar}")

    sub_base = base_unicas[cols_base]
    sub_comp = comp_unicas[cols_comp]

    cruce = sub_base.merge(sub_comp, on="Placa", how="inner")

    # 1. Evaluación de Tabla/Grupo
    col_gb = f"Grupo_{anio_base}"
    col_gc = f"Grupo_{anio_comparar}"

    if col_gb in cruce.columns and col_gc in cruce.columns:
        grupo_base_limpio = cruce[col_gb].fillna("").astype(str).str.strip().str.upper().str[0]
        grupo_comp_limpio = cruce[col_gc].fillna("").astype(str).str.strip().str.upper().str[0]

        cruce["ESTADO_GRUPO_SIM"] = np.where(
            grupo_base_limpio == grupo_comp_limpio,
            "Misma Tabla",
            "Cambio de Tabla",
        )
    else:
        cruce["ESTADO_GRUPO_SIM"] = "SIN GRUPO REGISTRADO"

    # 2. Evaluación de Avalúos y Límites de Simulación
    col_ab = f"Avaluo_Sim_{anio_base}"
    col_ac = f"Avaluo_Sim_{anio_comparar}"

    if col_ab in cruce.columns and col_ac in cruce.columns:
        # Limpieza de montos por formato texto
        av_base_num = _limpiar_monto_texto(cruce[col_ab]).fillna(0)
        av_comp_raw = _limpiar_monto_texto(cruce[col_ac]).fillna(0)

        # Normalizar la escala de la simulación a comparar contra la base
        av_comp_num = _normalizar_escala_simulacion(av_base_num, av_comp_raw)

        # Guardar valor normalizado en la columna del DataFrame
        cruce[col_ac] = av_comp_num

        cruce["VAR_AVALUO_SIM"] = np.where(
            av_base_num > 0,
            ((av_comp_num - av_base_num) / av_base_num) * 100,
            0,
        )

        cruce["LIMITE_INFERIOR_SIM"] = av_base_num * (1 + (porcentaje_limite_inferior / 100))

        cruce["ESTADO_AVALUO_SIM"] = np.where(
            av_comp_num >= cruce["LIMITE_INFERIOR_SIM"],
            "CUMPLE LIMITE INFERIOR",
            "NO CUMPLE LIMITE INFERIOR",
        )

    return cruce