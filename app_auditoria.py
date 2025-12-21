import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="AuditPro - Sistema Seguro", page_icon="🔐", layout="wide")

# --- CLASE DE BASE DE DATOS ACTUALIZADA ---
class AuditDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Tabla de Auditores (Usuarios)
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Tabla de Clientes ligada al usuario
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            audit_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id))''')
        self.conn.commit()

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

# --- VALIDACIÓN DE CONTRASEÑA ---
def validar_password(password):
    # Al menos 8 caracteres, una mayúscula, un número y un carácter especial
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return False, "Debe contener al menos una letra MAYÚSCULA."
    if not re.search(r"[0-9]", password):
        return False, "Debe contener al menos un número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Debe contener al menos un carácter especial (ej: @, #, $)."
    return True, ""

# --- FUNCIONES DE EXPORTACIÓN ---
def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Encargos')
    return output.getvalue()

def generar_pdf(df, auditor_nombre):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE ENCARGOS DE AUDITORIA", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(190, 10, f"Auditor Responsable: {auditor_nombre}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(80, 10, "Nombre del Cliente", 1)
    pdf.cell(30, 10, "Ano", 1)
    pdf.cell(80, 10, "Fecha de Registro", 1)
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 9)
    for _, row in df.iterrows():
        pdf.cell(80, 10, str(row['Cliente'])[:40], 1)
        pdf.cell(30, 10, str(row['Año']), 1)
        pdf.cell(80, 10, str(row['Fecha Creación']), 1)
        pdf.ln()
    return bytes(pdf.output())

# --- LÓGICA DE AUTENTICACIÓN ---
def login_screen():
    db = AuditDatabase()
    st.title("🔐 Acceso al Sistema de Auditoría")
    
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse como Auditor"])
    
    with tab1:
        email = st.text_input("Correo Electrónico")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", use_container_width=True):
            cursor = db.conn.cursor()
            h_pass = db.hash_password(password)
            cursor.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (email, h_pass))
            user = cursor.fetchone()
            if user:
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos.")

    with tab2:
        st.subheader("Crear Cuenta de Auditor")
        new_name = st.text_input("Nombres y Apellidos")
        new_email = st.text_input("Correo Electrónico (Usuario)")
        new_pass = st.text_input("Nueva Contraseña", type="password", help="Mínimo 8 caracteres, 1 Mayúscula, 1 Número y 1 Carácter especial")
        conf_pass = st.text_input("Confirmar Contraseña", type="password")
        
        if st.button("Registrarme", use_container_width=True):
            if new_pass != conf_pass:
                st.warning("Las contraseñas no coinciden.")
            else:
                es_valida, mensaje = validar_password(new_pass)
                if not es_valida:
                    st.error(mensaje)
                elif new_name and new_email:
                    try:
                        cursor = db.conn.cursor()
                        cursor.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?, ?, ?)", 
                                     (new_email, new_name, db.hash_password(new_pass)))
                        db.conn.commit()
                        st.success("¡Registro exitoso! Ahora puedes iniciar sesión.")
                    except sqlite3.IntegrityError:
                        st.error("Este correo ya está registrado.")
                else:
                    st.warning("Por favor completa todos los campos.")

# --- INTERFAZ PRINCIPAL (DESPUÉS DEL LOGIN) ---
def main_app():
    db = AuditDatabase()
    
    # Barra lateral
    with st.sidebar:
        st.title(f"👨‍🏫 Auditor: {st.session_state.user_name}")
        st.markdown("---")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id
            del st.session_state.user_name
            st.rerun()
        
        st.header("➕ Nuevo Encargo")
        nuevo_cliente = st.text_input("Empresa")
        anio = st.number_input("Año", value=datetime.now().year)
        if st.button("Guardar"):
            if nuevo_cliente:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, nuevo_cliente, anio))
                db.conn.commit()
                st.success("Guardado.")
                st.rerun()

    # Dashboard
    st.title("⚖️ Panel de Gestión de Auditorías")
    df_clientes = pd.read_sql_query(
        "SELECT id, client_name as 'Cliente', audit_year as 'Año', created_at as 'Fecha Creación' FROM clients WHERE user_id = ?", 
        db.conn, params=(st.session_state.user_id,)
    )
    
    if not df_clientes.empty:
        col1, col2 = st.columns([3, 1])
        with col1: st.subheader("Mis Clientes Registrados")
        with col2:
            st.download_button("📥 Excel", generar_excel(df_clientes), "auditoria.xlsx", "application/vnd.ms-excel")
            st.download_button("📥 PDF", generar_pdf(df_clientes, st.session_state.user_name), "auditoria.pdf", "application/pdf")

        # Eliminación
        st.markdown("---")
        seleccionar_todos = st.toggle("Seleccionar todos para borrar")
        df_sel = df_clientes.copy()
        df_sel.insert(0, "Seleccionar", seleccionar_todos)
        
        tabla = st.data_editor(df_sel, column_config={"Seleccionar": st.column_config.CheckboxColumn("Borrar"), "id": None},
                              disabled=["Cliente", "Año", "Fecha Creación"], hide_index=True, use_container_width=True)
        
        seleccionados = tabla[tabla["Seleccionar"] == True]["id"].tolist()
        if seleccionados:
            confirmar = st.text_input("Escribe ELIMINAR para confirmar:")
            if st.button("Eliminar permanentemente", type="primary") and confirmar == "ELIMINAR":
                cursor = db.conn.cursor()
                cursor.execute(f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(seleccionados))})", seleccionados)
                db.conn.commit()
                st.rerun()
    else:
        st.info("Aún no tienes clientes asignados.")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    if 'user_id' not in st.session_state:
        login_screen()
    else:
        main_app()
