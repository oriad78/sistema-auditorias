import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="Sistema de Gestión de Auditorías",
    page_icon="📊",
    layout="wide"
)

# --- BASE DE DATOS ---
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
        # Seleccionamos también el ID para poder borrar, pero lo ocultaremos visualmente
        return pd.read_sql_query(
            "SELECT id, client_name as 'Cliente', audit_year as 'Año', created_at as 'Fecha Creación' FROM clients WHERE user_id = ?", 
            self.conn, params=(user_id,)
        )

# --- FUNCIONES DE EXPORTACIÓN CORREGIDAS ---
def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Lista_Encargos')
    return output.getvalue()

def generar_pdf(df):
    # Usamos la configuración estándar para evitar errores de compatibilidad
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE ENCARGOS DE AUDITORIA", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Nombre del Cliente", 1)
    pdf.cell(30, 10, "Ano", 1) # Evitamos la ñ por ahora para máxima compatibilidad
    pdf.cell(80, 10, "Fecha de Creacion", 1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        pdf.cell(80, 10, str(row['Cliente']), 1)
        pdf.cell(30, 10, str(row['Año']), 1)
        pdf.cell(80, 10, str(row['Fecha Creación']), 1)
        pdf.ln()
    
    # IMPORTANTE: Aquí estaba el error. Usamos 'dest="S"' y encode para enviar bytes puros.
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- INTERFAZ PRINCIPAL ---
def main_app():
    st.title("⚖️ Gestión Profesional de Auditorías")
    
    if 'user_id' not in st.session_state:
        st.session_state.user_id = 1

    db = AuditDatabase()

    # 1. CREACIÓN
    with st.expander("➕ Crear Nuevo Encargo", expanded=False):
        c1, c2 = st.columns(2)
        nuevo_cliente = c1.text_input("Nombre de la Empresa")
        anio_auditoria = c2.number_input("Año", value=2024)
        
        if st.button("💾 Guardar Encargo"):
            if nuevo_cliente:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, nuevo_cliente, anio_auditoria))
                db.conn.commit()
                st.success("Guardado exitosamente.")
                st.rerun()

    # 2. LISTADO Y EXPORTACIÓN
    df_clientes = db.get_user_clients(st.session_state.user_id)
    
    if not df_clientes.empty:
        st.subheader("📋 Encargos Actuales")
        
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            st.download_button(
                label="📥 Descargar Excel",
                data=generar_excel(df_clientes),
                file_name="reporte_auditoria.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col_ex2:
            st.download_button(
                label="📥 Descargar PDF",
                data=generar_pdf(df_clientes),
                file_name="reporte_auditoria.pdf",
                mime="application/pdf"
            )

        # 3. BORRADO SEGURO
        st.markdown("---")
        st.subheader("🗑️ Eliminar Encargos")
        
        # Preparamos la tabla de selección
        df_sel = df_clientes.copy()
        df_sel.insert(0, "Seleccionar", False)
        
        # Mostramos la tabla (ocultamos la columna 'id' que es técnica)
        tabla_editada = st.data_editor(
            df_sel,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn("¿Borrar?"),
                "id": None # Esto oculta la columna ID para que no confunda al usuario
            },
            disabled=["Cliente", "Año", "Fecha Creación"],
            hide_index=True,
            use_container_width=True
        )

        seleccionados = tabla_editada[tabla_editada["Seleccionar"] == True]["id"].tolist()

        if seleccionados:
            st.error(f"⚠️ Atención: Va a eliminar {len(seleccionados)} registros.")
            confirmacion = st.text_input("Escriba **ELIMINAR** para proceder:")
            
            if st.button("❌ CONFIRMAR ELIMINACIÓN"):
                if confirmacion == "ELIMINAR":
                    cursor = db.conn.cursor()
                    query = f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(seleccionados))})"
                    cursor.execute(query, seleccionados)
                    db.conn.commit()
                    st.success("Registros eliminados.")
                    st.rerun()
                else:
                    st.warning("Debe escribir ELIMINAR para continuar.")
    else:
        st.info("No hay datos para mostrar.")

if __name__ == "__main__":
    main_app()
