import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="AuditPro - Gestión de Auditorías",
    page_icon="⚖️",
    layout="wide"
)

# --- BASE DE DATOS ---
class AuditDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            audit_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()

    def get_user_clients(self, user_id):
        return pd.read_sql_query(
            "SELECT id, client_name as 'Cliente', audit_year as 'Año', created_at as 'Fecha Creación' FROM clients", 
            self.conn
        )

# --- FUNCIONES DE EXPORTACIÓN ---
def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Encargos')
    return output.getvalue()

def generar_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE ENCARGOS DE AUDITORIA", ln=True, align='C')
    pdf.ln(10)
    
    # Encabezados
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(80, 10, "Nombre del Cliente", 1)
    pdf.cell(30, 10, "Ano", 1)
    pdf.cell(80, 10, "Fecha de Registro", 1)
    pdf.ln()
    
    # Datos
    pdf.set_font("Helvetica", '', 9)
    for _, row in df.iterrows():
        pdf.cell(80, 10, str(row['Cliente'])[:40], 1) # Limitamos texto para que no se desborde
        pdf.cell(30, 10, str(row['Año']), 1)
        pdf.cell(80, 10, str(row['Fecha Creación']), 1)
        pdf.ln()
    
    # RETORNO CORREGIDO PARA FPDF2
    return bytes(pdf.output())

# --- INTERFAZ PRINCIPAL ---
def main_app():
    st.title("⚖️ Gestión Profesional de Auditorías")
    
    # Aseguramos que el ID de usuario exista
    if 'user_id' not in st.session_state:
        st.session_state.user_id = 1

    db = AuditDatabase()

    # 1. CREACIÓN DE ENCARGOS
    with st.sidebar:
        st.header("➕ Nuevo Encargo")
        nuevo_cliente = st.text_input("Nombre de la Empresa")
        anio_auditoria = st.number_input("Año Fiscal", value=datetime.now().year)
        if st.button("💾 Registrar Cliente"):
            if nuevo_cliente:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, nuevo_cliente, anio_auditoria))
                db.conn.commit()
                st.success("Registrado.")
                st.rerun()

    # 2. LISTADO Y EXPORTACIÓN
    df_clientes = db.get_user_clients(st.session_state.user_id)
    
    if not df_clientes.empty:
        col_t1, col_t2 = st.columns([3, 1])
        with col_t1:
            st.subheader("📋 Base de Datos de Clientes")
        with col_t2:
            # BOTONES DE DESCARGA
            excel_data = generar_excel(df_clientes)
            pdf_data = generar_pdf(df_clientes)
            
            st.download_button("📥 Excel", excel_data, "auditoria.xlsx", "application/vnd.ms-excel", use_container_width=True)
            st.download_button("📥 PDF", pdf_data, "auditoria.pdf", "application/pdf", use_container_width=True)

        # 3. BORRADO SEGURO CON SELECCIONADOR
        st.markdown("---")
        st.subheader("🗑️ Eliminación Masiva")
        
        df_sel = df_clientes.copy()
        df_sel.insert(0, "Seleccionar", False)
        
        tabla_editada = st.data_editor(
            df_sel,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn("Borrar"),
                "id": None 
            },
            disabled=["Cliente", "Año", "Fecha Creación"],
            hide_index=True,
            use_container_width=True
        )

        seleccionados = tabla_editada[tabla_editada["Seleccionar"] == True]["id"].tolist()

        if seleccionados:
            st.warning(f"Va a eliminar {len(seleccionados)} registros de la base de datos.")
            if st.button("❌ ELIMINAR SELECCIONADOS"):
                cursor = db.conn.cursor()
                query = f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(seleccionados))})"
                cursor.execute(query, seleccionados)
                db.conn.commit()
                st.success("Eliminado con éxito.")
                st.rerun()
    else:
        st.info("No hay encargos registrados. Use la barra lateral para agregar uno.")

if __name__ == "__main__":
    main_app()
