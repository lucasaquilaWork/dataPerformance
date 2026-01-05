import streamlit as st
import pandas as pd

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
    df_carregou = pd.concat(
        [pd.read_csv(f) for f in carregamento_files], ignore_index=True
    )
    df_disp = pd.concat(
        [pd.read_excel(f) for f in disponibilidade_files], ignore_index=True
    )
    df_perf = pd.concat(
        [pd.read_excel(f) for f in performance_files], ignore_index=True
    )

    # =====================================================
    # PADRONIZAÇÃO DE COLUNAS
    # =====================================================
    for df in [df_carregou, df_disp, df_perf]:
        df.columns = df.columns.str.strip()

    # Performance (vem em maiúsculo)
    df_perf = df_perf.rename(columns={
        "DRIVER ID": "Driver ID",
        "DRIVER NAME": "Driver Name"
    })

    required_perf = ["Driver ID", "Driver Name", "DS"]
    missing = [c for c in required_perf if c not in df_perf.columns]
    if missing:
        st.error(f"❌ Colunas ausentes no arquivo de Performance: {missing}")
        st.stop()

    df_perf = df_perf[required_perf]

    # =====================================================
    # CARREGAMENTO
    # =====================================================
    df_carregou = df_carregou.drop_duplicates(subset=["Task ID"])

    carregou_count = (
        df_carregou
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

    # Contagem AM e SD (otimizada)
    df_disp["AM"] = df_disp[date_cols].apply(
        lambda x: x.astype(str).str.contains("05:45-09:30", regex=False).sum(), axis=1
    )

    df_disp["SD"] = df_disp[date_cols].apply(
        lambda x: x.astype(str).str.contains("12:30-15:00", regex=False).sum(), axis=1
    )

    disp_extra = (
        df_disp
        .groupby("Driver ID", as_index=False)[["AM", "SD"]]
        .sum()
    )

    disp_extra["Total Disponibilidade"] = disp_extra["AM"] + disp_extra["SD"]

    # =====================================================
    # CONSOLIDAÇÃO FINAL
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

    # Ajustar nome do motorista
    df_final["Driver Name"] = df_final["Driver Name"].fillna(df_final["Driver Name_disp"])
    df_final = df_final.drop(columns=["Driver Name_disp"])

    # =====================================================
    # TRATATIVAS
    # =====================================================
    num_cols = ["Vezes que Carregou", "No-Show", "AM", "SD", "Total Disponibilidade"]
    for col in num_cols:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").fillna(0).astype(int)

    df_final["Driver ID"] = pd.to_numeric(
        df_final["Driver ID"], errors="coerce"
    ).fillna(0).astype(int)

    # Taxa de Aproveitamento
    df_final["Taxa de Aproveitamento (%)"] = (
        df_final["Vezes que Carregou"] / df_final["Total Disponibilidade"]
    ).where(df_final["Total Disponibilidade"] > 0, 0) * 100

    # DS
    df_final["DS (%)"] = pd.to_numeric(df_final["DS"], errors="coerce").fillna(0) * 100

    # =====================================================
    # ESTILO (SEM ERRO DE TYPE)
    # =====================================================
    def color_percent(val):
        try:
            val = float(val)
        except (TypeError, ValueError):
            return ""

        if val >= 98:
            return "color: green; font-weight: bold;"
        elif val >= 95:
            return "color: orange; font-weight: bold;"
        else:
            return "color: red; font-weight: bold;"

    styled_df = (
        df_final.style
        .applymap(
            color_percent,
            subset=["Taxa de Aproveitamento (%)", "DS (%)"]
        )
        .format({
            "Taxa de Aproveitamento (%)": "{:.2f}%",
            "DS (%)": "{:.2f}%"
        })
    )

    st.write(styled_df)

    # =====================================================
    # DOWNLOAD
    # =====================================================
    csv = df_final.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Baixar Resultado",
        data=csv,
        file_name="resultado_consolidado.csv",
        mime="text/csv"
    )

