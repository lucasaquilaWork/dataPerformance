import streamlit as st
import pandas as pd

st.title("Consolidador de Performance de Motoristas")

# Upload de múltiplos arquivos
carregamento_files = st.file_uploader("Arquivos de Carregamento (CSV)", type="csv", accept_multiple_files=True)
disponibilidade_files = st.file_uploader("Arquivos de Disponibilidade (Excel)", type=["xlsx"], accept_multiple_files=True)
performance_files = st.file_uploader("Arquivos de Performance (Excel)", type=["xlsx"], accept_multiple_files=True)

if st.button("Gerar Dados"):
    if carregamento_files and disponibilidade_files and performance_files:
        # Concatenar múltiplos arquivos
        df_carregou = pd.concat([pd.read_csv(f) for f in carregamento_files])
        df_disp = pd.concat([pd.read_excel(f) for f in disponibilidade_files])
        df_perf = pd.concat([pd.read_excel(f) for f in performance_files])

        # Remover duplicados no carregamento
        df_carregou = df_carregou.drop_duplicates(subset=["Task ID"])

        # Contar vezes que carregou
        carregou_count = df_carregou.groupby("Driver ID").size().reset_index(name="Vezes que Carregou")

        # Contar No Show Time
        disp_count = df_disp.groupby("Driver ID").agg({
            "No Show Time": "sum"
        }).reset_index()
        disp_count = disp_count.rename(columns={"No Show Time": "No-Show"})

        # 🔹 Identificar colunas de datas dinamicamente
        fixed_cols = ["Driver ID", "Driver Name", "No Show Time"]
        date_cols = [c for c in df_disp.columns if c not in fixed_cols]

        # Função para contar AM e SD
        def contar_disponibilidade(row):
            am_count = 0
            sd_count = 0
            for col in date_cols:
                val = str(row[col]).strip()
                if val in ["--", "Not Available", "nan"]:
                    continue
                if "05:45-09:30" in val:
                    am_count += 1
                if "12:30-15:00" in val:
                    sd_count += 1
            return pd.Series([am_count, sd_count])

        # Aplicar por motorista
        df_disp[["AM", "SD"]] = df_disp.apply(contar_disponibilidade, axis=1)

        # Agregar AM e SD por Driver ID
        disp_extra = df_disp.groupby("Driver ID")[["AM", "SD"]].sum().reset_index()
        disp_extra["Total Disponibilidade"] = disp_extra["AM"] + disp_extra["SD"]

        # Performance
        df_perf = df_perf[["Driver ID", "Driver Name", "DS"]]

        # Consolidar
        df_final = df_perf.merge(carregou_count, on="Driver ID", how="left")
        df_final = df_final.merge(disp_count, on="Driver ID", how="left")
        df_final = df_final.merge(disp_extra, on="Driver ID", how="left")

        # 🔹 Adicionar Vehicle Type
        df_final = df_final.merge(
            df_disp[["Driver ID", "Driver Name", "Vehicle Type"]].drop_duplicates(),
            on="Driver ID", how="left", suffixes=("", "_disp")
        )

        # Tratativa: se Driver Name estiver vazio, buscar pelo Driver ID na disponibilidade
        df_final["Driver Name"] = df_final["Driver Name"].fillna(df_final["Driver Name_disp"])
        df_final = df_final.drop(columns=["Driver Name_disp"])

        # Preencher valores ausentes
        for col in ["Vezes que Carregou", "No-Show", "AM", "SD", "Total Disponibilidade"]:
            df_final[col] = df_final[col].fillna(0).astype(int)

        # 🔹 Calcular Taxa de Aproveitamento
        df_final["Taxa de Aproveitamento (%)"] = df_final.apply(
            lambda row: (row["Vezes que Carregou"] / row["Total Disponibilidade"] * 100)
            if row["Total Disponibilidade"] > 0 else 0,
            axis=1
        )

        # Formatando DS
        df_final["Driver ID"] = pd.to_numeric(df_final["Driver ID"], errors="coerce").fillna(0).astype(int)
        df_final["DS (%)"] = df_final["DS"] * 100
        df_final["DS"] = df_final["DS"] * 100


        # 🔹 Função para colorir células
        def color_percent(val):
            try:
                if val >= 98:
                    return "color: green; font-weight: bold;"
                else:
                    return "color: red; font-weight: bold;"
            except:
                return ""

        # 🔹 Aplicar estilo e formatar com 2 casas decimais
        styled_df = (
            df_final.style
            .applymap(color_percent, subset=["Taxa de Aproveitamento (%)", "DS (%)"])
            .format({
                "Taxa de Aproveitamento (%)": "{:.2f}%",
                "DS (%)": "{:.2f}%"
            })
        )

        # Mostrar resultado com altura maior
        st.dataframe(styled_df, height=600, width=1600)

        # 🔹 Download do consolidado (agora dentro do botão)
        csv = df_final.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Baixar Dados", data=csv, file_name="resultado.csv", mime="text/csv")
