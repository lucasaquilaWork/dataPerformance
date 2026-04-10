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
        st.warning("⚠️ Envie todos os arquivos.")
        st.stop()

    # =====================================================
    # LEITURA
    # =====================================================
    df_carregou = pd.concat([pd.read_csv(f) for f in carregamento_files], ignore_index=True)
    df_disp = pd.concat([pd.read_excel(f) for f in disponibilidade_files], ignore_index=True)
    df_perf = pd.concat([pd.read_excel(f) for f in performance_files], ignore_index=True)

    # =====================================================
    # PADRONIZAÇÃO
    # =====================================================
    for df in [df_carregou, df_disp, df_perf]:
        df.columns = df.columns.str.strip()

    for df in [df_carregou, df_disp, df_perf]:
        df["Driver ID"] = df["Driver ID"].astype(str).str.strip()

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
        .reset_index(name="Vezes que Carregou")
    )

    # =====================================================
    # DISPONIBILIDADE (🔥 CORRIGIDO DE VERDADE)
    # =====================================================
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

        return "AM" if int(match.group(1)) < 12 else "SD"

    # 🔥 EXPLODIR dados (linha por dia/turno)
    registros = []

    for _, row in df_disp.iterrows():
        for col in date_cols:
            turno = classify_shift(row[col])
            if turno:
                registros.append({
                    "Driver ID": row["Driver ID"],
                    "Driver Name": row.get("Driver Name"),
                    "Vehicle Type": row.get("Vehicle Type"),
                    "Turno": turno
                })

    df_turnos = pd.DataFrame(registros)

    # 🔥 AGRUPAMENTO CORRETO
    disp_resumo = (
        df_turnos
        .groupby("Driver ID")
        .agg(
            AM=("Turno", lambda x: (x == "AM").sum()),
            SD=("Turno", lambda x: (x == "SD").sum())
        )
        .reset_index()
    )

    disp_resumo["Total Disponibilidade"] = disp_resumo["AM"] + disp_resumo["SD"]

    # 🔥 NO SHOW
    disp_noshow = (
        df_disp
        .groupby("Driver ID")["No Show Time"]
        .sum()
        .reset_index(name="No-Show")
    )

    # 🔥 VEÍCULO (agora confiável)
    veiculo = (
        df_turnos
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
        .merge(disp_resumo, on="Driver ID", how="left")
        .merge(disp_noshow, on="Driver ID", how="left")
        .merge(veiculo, on="Driver ID", how="left")
    )

    # =====================================================
    # TRATAMENTO
    # =====================================================
    num_cols = ["Vezes que Carregou", "AM", "SD", "Total Disponibilidade", "No-Show"]

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
        veiculo_filtro = st.selectbox(
            "Tipo de Veículo",
            ["Todos"] + sorted(df_final["Vehicle Type"].dropna().unique())
        )

    with col3:
        min_aprov = st.slider("Aproveitamento mínimo (%)", 0, 100, 0)

    df_filtrado = df_final.copy()

    if motorista != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Driver Name"] == motorista]

    if veiculo_filtro != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Vehicle Type"] == veiculo_filtro]

    df_filtrado = df_filtrado[df_filtrado["Taxa de Aproveitamento (%)"] >= min_aprov]

    # =====================================================
    # TABELA
    # =====================================================
    st.dataframe(df_filtrado, use_container_width=True, height=500)

    # =====================================================
    # GRÁFICO
    # =====================================================
    top_n = st.slider("Qtd. piores motoristas", 5, 30, 10)

    df_piores = df_filtrado.sort_values("Taxa de Aproveitamento (%)").head(top_n)

    fig = px.bar(
        df_piores,
        x="Driver Name",
        y="Taxa de Aproveitamento (%)",
        color="Vehicle Type"
    )

    st.plotly_chart(fig, use_container_width=True)

    # =====================================================
    # DOWNLOAD
    # =====================================================
    st.download_button(
        "📥 Baixar Resultado",
        data=df_filtrado.to_csv(index=False).encode("utf-8"),
        file_name="resultado.csv"
    )
