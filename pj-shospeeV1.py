import streamlit as st
import pandas as pd
import re

st.set_page_config(layout="wide")
st.title("📊 Consolidador de Performance de Motoristas")

# =====================================================
# UPLOADS
# =====================================================
carregamento_files = st.file_uploader(
    "Arquivos de Carregamento (CSV)", type="csv", accept_multiple_files=True
)
disponibilidade_files = st.file_uploader(
    "Arquivos de Disponibilidade (Excel)", type=["xlsx"], accept_multiple_files=True
)
performance_files = st.file_uploader(
    "Arquivos de Performance (Excel)", type=["xlsx"], accept_multiple_files=True
)

if st.button("🚀 Gerar Dados"):
    if not (carregamento_files and disponibilidade_files and performance_files):
        st.warning("⚠️ Envie todos os arquivos antes de gerar os dados.")
        st.stop()

    # =====================================================
    # LEITURA DOS ARQUIVOS
    # =====================================================
    try:
        df_carregou = pd.concat(
            [pd.read_csv(f) for f in carregamento_files],
            ignore_index=True
        )

        df_disp = pd.concat(
            [pd.read_excel(f) for f in disponibilidade_files],
            ignore_index=True
        )

        df_perf = pd.concat(
            [pd.read_excel(f) for f in performance_files],
            ignore_index=True
        )
    except ImportError:
        st.error(
            "❌ Dependência ausente: openpyxl\n\n"
            "Instale com:\n"
            "`pip install openpyxl`"
        )
        st.stop()

    # =====================================================
    # PADRONIZAÇÃO
    # =====================================================
    for df in [df_carregou, df_disp, df_perf]:
        df.columns = df.columns.str.strip()

    df_perf = df_perf.rename(columns={
        "DRIVER ID": "Driver ID",
        "DRIVER NAME": "Driver Name"
    })

    required = ["Driver ID", "Driver Name", "DS"]
    missing = [c for c in required if c not in df_perf.columns]
    if missing:
        st.error(f"❌ Colunas ausentes no Performance: {missing}")
        st.stop()

    df_perf = df_perf[required]

    # =====================================================
    # CARREGAMENTO
    # =====================================================
    carregou_count = (
        df_carregou
        .drop_duplicates(subset=["Task ID"])
        .groupby("Driver ID", as_index=False)
        .size()
        .rename(columns={"size": "Vezes que Carregou"})
    )

    # =====================================================
    # DISPONIBILIDADE
    # =====================================================
    disp_count = (
        df_disp
        .groupby("Driver ID", as_index=False)["No Show Time"]
        .sum()
        .rename(columns={"No Show Time": "No-Show"})
    )

    fixed_cols = ["Driver ID", "Driver Name", "No Show Time", "Vehicle Type"]
    date_cols = [c for c in df_disp.columns if c not in fixed_cols]

    # -------- FUNÇÃO AUTOMÁTICA DE TURNO --------
    def classify_shift(val):
        if pd.isna(val):
            return None

        val = str(val).strip()
        if val in ["", "--", "Not Available"]:
            return None

        match = re.search(r"(\d{1,2}):(\d{2})", val)
        if not match:
            return None

        hour = int(match.group(1))
        return "AM" if hour < 12 else "SD"

    # -------- CONTAGEM AUTOMÁTICA --------
    df_disp["AM"] = df_disp[date_cols].apply(
        lambda row: sum(classify_shift(v) == "AM" for v in row),
        axis=1
    )

    df_disp["SD"] = df_disp[date_cols].apply(
        lambda row: sum(classify_shift(v) == "SD" for v in row),
        axis=1
    )

    df_disp["Total Disponibilidade"] = df_disp["AM"] + df_disp["SD"]

    disp_extra = (
        df_disp
        .groupby("Driver ID", as_index=False)[["AM", "SD", "Total Disponibilidade"]]
        .sum()
    )

    # =====================================================
    # CONSOLIDAÇÃO
    # =====================================================
    df_final = (
        df_perf
        .merge(carregou_count, on="Driver ID", how="left")
        .merge(disp_count, on="Driver ID", how="left")
        .merge(disp_extra, on="Driver ID", how="left")
        .merge(
            df_disp[["Driver ID", "Driver Name", "Vehicle Type"]].drop_duplicates(),
            on="Driver ID",
            how="left",
            suffixes=("", "_disp")
        )
    )

    df_final["Driver Name"] = df_final["Driver Name"].fillna(
        df_final["Driver Name_disp"]
    )
    df_final = df_final.drop(columns=["Driver Name_disp"])

    # =====================================================
    # TRATATIVAS
    # =====================================================
    num_cols = ["Vezes que Carregou", "No-Show", "AM", "SD", "Total Disponibilidade"]
    for col in num_cols:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").fillna(0).astype(int)


    df_final["Taxa de Aproveitamento (%)"] = (
        df_final["Vezes que Carregou"] / df_final["Total Disponibilidade"]
    ).where(df_final["Total Disponibilidade"] > 0, 0) * 100

    # =====================================================
    # TABELA
    # =====================================================
    st.dataframe(
        df_final,
        use_container_width=True,
        height=600,
        column_config={
            "Taxa de Aproveitamento (%)": st.column_config.NumberColumn(
                "Taxa de Aproveitamento (%)", format="%.2f%%"
            )
        }
    )
    df_final = df_final.drop(columns=["DS", "DS (%)"], errors="ignore")

    # =====================================================
    # DOWNLOAD
    # =====================================================
    st.download_button(
        "📥 Baixar Resultado",
        data=df_final.to_csv(index=False).encode("utf-8"),
        file_name="resultado_consolidado.csv",
        mime="text/csv"
    )
