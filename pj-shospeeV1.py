import streamlit as st
import pandas as pd
import re
import plotly.express as px

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
    # LEITURA
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
        st.error("❌ Instale: pip install openpyxl")
        st.stop()

    # =====================================================
    # PADRONIZAÇÃO
    # =====================================================
    for df in [df_carregou, df_disp, df_perf]:
        df.columns = df.columns.str.strip()

    df_carregou["Driver ID"] = df_carregou["Driver ID"].astype(str).str.strip()
    df_disp["Driver ID"] = df_disp["Driver ID"].astype(str).str.strip()
    df_perf["Driver ID"] = df_perf["Driver ID"].astype(str).str.strip()

    df_perf = df_perf.rename(columns={
        "DRIVER ID": "Driver ID",
        "DRIVER NAME": "Driver Name"
    })

    df_perf = df_perf[["Driver ID", "Driver Name", "DS"]]

    # =====================================================
    # CARREGAMENTO
    # =====================================================
    carregou_count = (
        df_carregou
        .dropna(subset=["Driver ID"])
        .groupby("Driver ID")["Task ID"]
        .nunique()
        .reset_index()
        .rename(columns={"Task ID": "Vezes que Carregou"})
    )

    # DEBUG
    st.write("🔍 Motoristas carregamento:", df_carregou["Driver ID"].nunique())
    st.write("🔍 Tasks únicas:", df_carregou["Task ID"].nunique())

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
    # 🚗 VEÍCULO (🔥 CORREÇÃO AQUI)
    # =====================================================
    veiculo_por_motorista = (
        df_disp
        .dropna(subset=["Vehicle Type"])
        .groupby("Driver ID")["Vehicle Type"]
        .agg(lambda x: x.mode()[0] if not x.mode().empty else x.iloc[0])
        .reset_index()
    )

    # =====================================================
    # CONSOLIDAÇÃO
    # =====================================================
    df_final = (
        df_perf
        .merge(carregou_count, on="Driver ID", how="left")
        .merge(disp_count, on="Driver ID", how="left")
        .merge(disp_extra, on="Driver ID", how="left")
        .merge(veiculo_por_motorista, on="Driver ID", how="left")
        .merge(
            df_disp[["Driver ID", "Driver Name"]].drop_duplicates(),
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
    # TRATATIVA
    # =====================================================
    num_cols = ["Vezes que Carregou", "No-Show", "AM", "SD", "Total Disponibilidade"]

    for col in num_cols:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").fillna(0)

    df_final["Taxa de Aproveitamento (%)"] = (
        df_final["Vezes que Carregou"] / df_final["Total Disponibilidade"]
    ).where(df_final["Total Disponibilidade"] > 0, 0) * 100

    # =====================================================
    # FILTROS
    # =====================================================
    st.subheader("🎯 Filtros")

    col1, col2, col3 = st.columns(3)

    with col1:
        motorista = st.selectbox(
            "Motorista",
            ["Todos"] + sorted(df_final["Driver Name"].dropna().unique())
        )

    with col2:
        veiculo = st.selectbox(
            "Tipo de Veículo",
            ["Todos"] + sorted(df_final["Vehicle Type"].dropna().unique())
        )

    with col3:
        min_aprov = st.slider("Aproveitamento mínimo (%)", 0, 100, 0)

    df_filtrado = df_final.copy()

    if motorista != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Driver Name"] == motorista]

    if veiculo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Vehicle Type"] == veiculo]

    df_filtrado = df_filtrado[
        df_filtrado["Taxa de Aproveitamento (%)"] >= min_aprov
    ]

    # =====================================================
    # TABELA
    # =====================================================
    st.dataframe(
        df_filtrado,
        use_container_width=True,
        height=500,
        column_config={
            "Taxa de Aproveitamento (%)": st.column_config.NumberColumn(
                format="%.2f%%"
            )
        }
    )

    # =====================================================
    # GRÁFICO
    # =====================================================
    top_n = st.slider("Qtd. piores motoristas", 5, 30, 10)

    df_piores = df_filtrado.sort_values(
        by="Taxa de Aproveitamento (%)"
    ).head(top_n)

    fig = px.bar(
        df_piores,
        x="Driver Name",
        y="Taxa de Aproveitamento (%)",
        color="Vehicle Type",
        title="📉 Piores Motoristas"
    )

    st.plotly_chart(fig, use_container_width=True)

    # =====================================================
    # DOWNLOAD
    # =====================================================
    st.download_button(
        "📥 Baixar Resultado",
        data=df_filtrado.to_csv(index=False).encode("utf-8"),
        file_name="resultado_consolidado.csv",
        mime="text/csv"
    )
