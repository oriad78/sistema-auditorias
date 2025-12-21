import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
from fpdf import FPDF

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Gestión Auditoría", layout="wide")

# --- CONEXIÓN SEGURA A BASE DE DATOS ---
def get_db_connection():
    conn = sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        full_name TEXT,
        password_hash TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        client_name TEXT,
        audit_year INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES DE APOYO ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validar_password(p):
    # Reglas: 8 caracteres, 1 Mayúscula, 1 Número, 1 Especial
    if len(p) < 8 or not re.search("[A-Z]", p) or not re.search("[0-9]", p) or not re.search("[!@#$%^&*]", p):
        return False
    return True

# --- EXPORTACIÓN ---
def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def generar_pdf(df, auditor):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE AUDITORIA", ln=True, align='C')
    pdf.set_font("Helvetica", '', 12)
    pdf.cell(190, 10, f"Auditor: {auditor}", ln=True, align='C')
    pdf.ln(10)
    for _, row in df.iterrows():
        pdf.cell(190, 10, f"Cliente: {row['Cliente']} - Año: {row['Año']}", 1, ln=True)
    return bytes(pdf.output())

# --- INTERFAZ: LOGIN / REGISTRO ---
def vista_login():
    st.title("🔐 Acceso AuditPro")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Entrar")
        email = st.text_input("Correo", key="login_email")
        password = st.text_input("Clave", type="password", key="login_pass")
        if st.button("Iniciar Sesión"):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", 
                         (email, hash_pass(password)))
            user = cursor.fetchone()
            conn.close()
            if user:
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

    with col2:
        st.subheader("Registrarse")
        n_name = st.text_input("Nombre Completo")
        n_email = st.text_input("Nuevo Correo")
        n_pass = st.text_input("Nueva Clave (8+ carac, Mayús, Núm, Especial)", type="password")
        # --- CAMBIO AQUÍ: SEGUNDO CAMPO DE CONTRASEÑA ---
        n_pass_conf = st.text_input("Confirmar Nueva Clave", type="password")
        
        if st.button("Crear Cuenta"):
            if n_pass != n_pass_conf:
                st.error("❌ Las contraseñas no coinciden. Por favor, verifícalas.")
            elif not validar_password(n_pass):
                st.error("❌ La clave no cumple los requisitos (8 caracteres, una Mayúscula, un Número y un Carácter especial).")
            elif n_name and n_email:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?, ?, ?)", 
                                 (n_email, n_name, hash_pass(n_pass)))
                    conn.commit()
                    conn.close()
                    st.success("✅ ¡Registrado con éxito! Ya puedes iniciar sesión a la izquierda.")
                except:
                    st.error("❌ Este correo ya está registrado.")
            else:
                st.warning("⚠️ Por favor, completa todos los campos.")

# --- INTERFAZ: APP PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id
            st.rerun()
        
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        c_name = st.text_input("Nombre Cliente")
        c_year = st.number_input("Año", value=2025)
        if st.button("Guardar"):
            if c_name:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, c_name, c_year))
                conn.commit()
                conn.close()
                st.rerun()

    st.title("📋 Panel de Auditoría")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, client_name as 'Cliente', audit_year as 'Año' FROM clients WHERE user_id = ?", 
                           conn, params=(st.session_state.user_id,))
    conn.close()

    if not df.empty:
        c1, c2 = st.columns(2)
        c1.download_button("📊 Excel", generar_excel(df), "reporte.xlsx")
        c2.download_button("📄 PDF", generar_pdf(df, st.session_state.user_name), "reporte.pdf")
        
        st.divider()
        st.subheader("🗑️ Borrado de Encargos")
        sel_todos = st.toggle("Seleccionar todos")
        df_edit = df.copy()
        df_edit.insert(0, "Borrar", sel_todos)
        
        res = st.data_editor(df_edit, column_config={"id": None}, hide_index=True, use_container_width=True)
        ids_borrar = res[res["Borrar"] == True]["id"].tolist()
        
        if ids_borrar:
            confirm = st.text_input("Escribe ELIMINAR para confirmar:")
            if st.button("Borrar Seleccionados", type="primary") and confirm == "ELIMINAR":
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(ids_borrar))})", ids_borrar)
                conn.commit()
                conn.close()
                st.rerun()
    else:
        st.info("No hay encargos. Agrega uno en la barra lateral.")

# --- CONTROLADOR PRINCIPAL ---
if 'user_id' not in st.session_state:
    vista_login()
else:
    vista_principal()
