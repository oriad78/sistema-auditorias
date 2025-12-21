import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import re
import io
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(
    page_title="AuditPro - Gestión Profesional",
    page_icon="⚖️",
    layout="wide"
)

# --- CLASE DE BASE DE DATOS ---
class AuditDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            audit_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id))''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_structure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            parent_id INTEGER,
            folder_name TEXT NOT NULL,
            folder_type TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id))''')
        self.conn.commit()

    def get_user_clients(self, user_id):
        return pd.read_sql_query(
            "SELECT id, client_name, audit_year, created_at FROM clients WHERE user_id = ?", 
            self.conn, params=(user_id,)
        )

    def delete_clients(self, client_ids):
        cursor = self.conn.cursor()
        ids_tuple = tuple(client_ids)
        placeholders = ','.join(['?'] * len(client_ids))
        # Eliminar en cascada manual (puedes mejorar esto con ON DELETE CASCADE en SQL)
        cursor.execute(f"DELETE FROM folder_structure WHERE client_id IN ({placeholders})", client_ids)
        cursor.execute(f"DELETE FROM clients WHERE id IN ({placeholders})", client_ids)
        self.conn.commit()

# --- FUNCIONES DE EXPORTACIÓN ---
def export_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Encargos')
    return output.getvalue()

def export_to_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "Reporte de Encargos de Auditoría", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(80, 10, "Cliente", 1)
    pdf.cell(40, 10, "Año", 1)
    pdf.cell(70, 10, "Fecha Creación", 1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 10)
    for index, row in df.iterrows():
        pdf.cell(80, 10, str(row['client_name']), 1)
        pdf.cell(40, 10, str(row['audit_year']), 1)
        pdf.cell(70, 10, str(row['created_at']), 1)
        pdf.ln()
    
    return pdf.output(dest='S').encode('latin-1')

# --- INTERFAZ DE USUARIO ---
def client_management_pro():
    st.header("👥 Gestión de Encargos")
    db = AuditDatabase()
    
    # --- SECCIÓN 1: CREACIÓN ---
    with st.expander("➕ Crear Nuevo Encargo", expanded=False):
        col1, col2, col3 = st.columns([2, 1, 1])
        name = col1.text_input("Nombre del Cliente")
        year = col2.number_input("Año", value=datetime.now().year)
        if col3.button("Guardar Encargo", use_container_width=True):
            if name:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, name, year))
                db.conn.commit()
                st.success("Cliente creado")
                st.rerun()

    # --- SECCIÓN 2: LISTADO Y EXPORTACIÓN ---
    df_clients = db.get_user_clients(st.session_state.user_id)
    
    if not df_clients.empty:
        st.subheader("📋 Mis Encargos")
        
        # Barra de herramientas de exportación
        exp_col1, exp_col2, exp_col3 = st.columns([2, 1, 1])
        with exp_col2:
            excel_data = export_to_excel(df_clients)
            st.download_button("📥 Descargar Excel", excel_data, "auditoria.xlsx", 
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with exp_col3:
            pdf_data = export_to_pdf(df_clients)
            st.download_button("📥 Descargar PDF", pdf_data, "auditoria.pdf", "application/pdf")

        # --- SECCIÓN 3: BORRADO MÚLTIPLE PROFESIONAL ---
        st.markdown("---")
        st.subheader("🗑️ Eliminación Masiva")
        
        # Usamos un dataframe con selección (Data Editor de Streamlit)
        df_with_selections = df_clients.copy()
        df_with_selections.insert(0, "Seleccionar", False)
        
        edited_df = st.data_editor(
            df_with_selections,
            column_config={"Seleccionar": st.column_config.CheckboxColumn(required=True)},
            disabled=["id", "client_name", "audit_year", "created_at"],
            hide_index=True,
            use_container_width=True
        )

        selected_ids = edited_df[edited_df["Seleccionar"] == True]["id"].tolist()

        if selected_ids:
            st.warning(f"Se han seleccionado {len(selected_ids)} registros para eliminar.")
            col_del1, col_del2 = st.columns(2)
            
            confirm = col_del1.text_input("Escribe 'ELIMINAR' para confirmar")
            if col_del2.button("Ejecutar Eliminación", type="primary", disabled=(confirm != "ELIMINAR")):
                db.delete_clients(selected_ids)
                st.success("Registros eliminados correctamente")
                st.rerun()
    else:
        st.info("No hay encargos registrados.")

# --- LÓGICA DE INICIO (SIMPLIFICADA PARA EL EJEMPLO) ---
def main():
    if 'user_id' not in st.session_state:
        st.session_state.user_id = 1  # Simulación de login para pruebas
        st.session_state.user_email = "admin@audit.com"

    menu = st.sidebar.selectbox("Navegación", ["Gestión de Clientes", "Dashboard"])
    
    if menu == "Gestión de Clientes":
        client_management_pro()

if __name__ == "__main__":
    main()
