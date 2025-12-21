import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN PROFESIONAL ---
st.set_page_config(
    page_title="Sistema de Gestión de Auditorías",
    page_icon="📊",
    layout="wide"
)

# --- CLASE DE BASE DE DATOS (EL CEREBRO) ---
class AuditDatabase:
    def __init__(self):
        # Conexión a la base de datos local
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Tabla de Usuarios
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT)''')
        
        # Tabla de Clientes (Encargos)
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            audit_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id))''')
        
        # Estructura de Carpetas
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
            "SELECT id, client_name as 'Cliente', audit_year as 'Año', created_at as 'Fecha Creación' FROM clients WHERE user_id = ?", 
            self.conn, params=(user_id,)
        )

# --- FUNCIONES DE EXPORTACIÓN (TUS REPORTES) ---
def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Lista_Encargos')
    return output.getvalue()

def generar_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE ENCARGOS DE AUDITORIA", ln=True, align='C')
    pdf.ln(10)
    
    # Encabezados de tabla
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Nombre del Cliente", 1)
    pdf.cell(30, 10, "Año", 1)
    pdf.cell(80, 10, "Fecha de Creación", 1)
    pdf.ln()
    
    # Datos
    pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        pdf.cell(80, 10, str(row['Cliente']), 1)
        pdf.cell(30, 10, str(row['Año']), 1)
        pdf.cell(80, 10, str(row['Fecha Creación']), 1)
        pdf.ln()
    
    return pdf.output()

# --- INTERFAZ DE USUARIO ---
def main_app():
    st.title("⚖️ Gestión Profesional de Auditorías")
    
    # Simulación de sesión (para que el código funcione de inmediato)
    if 'user_id' not in st.session_state:
        st.session_state.user_id = 1
        st.session_state.user_email = "contador@ejemplo.com"

    db = AuditDatabase()

    # 1. FORMULARIO DE CREACIÓN
    with st.expander("➕ Crear Nuevo Encargo de Auditoría", expanded=False):
        c1, c2 = st.columns(2)
        nuevo_cliente = c1.text_input("Nombre de la Empresa / Cliente")
        anio_auditoria = c2.number_input("Año Fiscal", value=2024)
        
        if st.button("💾 Guardar en Base de Datos"):
            if nuevo_cliente:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, nuevo_cliente, anio_auditoria))
                db.conn.commit()
                st.success(f"Encargo para {nuevo_cliente} creado correctamente.")
                st.rerun()
            else:
                st.error("Por favor, ingrese el nombre del cliente.")

    # 2. SECCIÓN DE REPORTE Y EXPORTACIÓN
    df_clientes = db.get_user_clients(st.session_state.user_id)
    
    if not df_clientes.empty:
        st.subheader("📋 Encargos Registrados")
        
        # Botones de Exportación
        col_ex1, col_ex2 = st.columns(2)
        
        with col_ex1:
            excel_data = generar_excel(df_clientes)
            st.download_button(
                label="📥 Descargar Reporte en Excel",
                data=excel_data,
                file_name=f"reporte_auditoria_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        with col_ex2:
            pdf_data = generar_pdf(df_clientes)
            st.download_button(
                label="📥 Descargar Reporte en PDF",
                data=pdf_data,
                file_name=f"reporte_auditoria_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        # 3. SECCIÓN DE ELIMINACIÓN (BORRADO SEGURO)
        st.markdown("---")
        st.subheader("🗑️ Zona de Eliminación")
        st.info("Seleccione los encargos que desea borrar definitivamente.")
        
        # Tabla interactiva para seleccionar
        df_con_seleccion = df_clientes.copy()
        df_con_seleccion.insert(0, "Seleccionar", False)
        
        tabla_editada = st.data_editor(
            df_con_seleccion,
            column_config={"Seleccionar": st.column_config.CheckboxColumn(required=True)},
            disabled=["id", "Cliente", "Año", "Fecha Creación"],
            hide_index=True,
            use_container_width=True
        )

        # Lógica de borrado
        ids_a_borrar = tabla_editada[tabla_editada["Seleccionar"] == True]["id"].tolist()

        if ids_a_borrar:
            st.warning(f"⚠️ Ha seleccionado {len(ids_a_borrar)} encargo(s) para eliminar.")
            confirmacion = st.text_input("Para confirmar la eliminación, escriba la palabra **ELIMINAR** en mayúsculas:")
            
            if st.button("❌ EJECUTAR ELIMINACIÓN", type="primary"):
                if confirmacion == "ELIMINAR":
                    cursor = db.conn.cursor()
                    # Borrar carpetas relacionadas y luego el cliente
                    placeholders = ','.join(['?'] * len(ids_a_borrar))
                    cursor.execute(f"DELETE FROM folder_structure WHERE client_id IN ({placeholders})", ids_a_borrar)
                    cursor.execute(f"DELETE FROM clients WHERE id IN ({placeholders})", ids_a_borrar)
                    db.conn.commit()
                    st.success("Los datos han sido eliminados.")
                    st.rerun()
                else:
                    st.error("Palabra de confirmación incorrecta.")
    else:
        st.write("No hay encargos registrados todavía.")

if __name__ == "__main__":
    main_app()
