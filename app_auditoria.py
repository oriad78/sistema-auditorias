import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="AuditPro - Gestión de Auditoría", page_icon="⚖️", layout="wide")

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
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL)''')
        
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

# --- VALIDACIONES Y REPORTES ---
def validar_password(password):
    if len(password) < 8: return False, "Mínimo 8 caracteres"
    if not re.search(r"[A-Z]", password): return False, "Falta una Mayúscula"
    if not re.search(r"[0-9]", password): return False, "Falta un número"
    if not re.search(r"[!@#$%^&*()]", password): return False, "Falta carácter especial"
    return True, ""

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
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(190, 10, f"Auditor: {auditor}", ln=True, align='C')
    pdf.ln(10)
    for _, row in df.iterrows():
        pdf.cell(190, 10, f"Cliente: {row['Cliente']} - Año: {row['Año']}", 1, ln=True)
    return bytes(pdf.output())

# --- VISTA: LOGIN ---
def login_screen():
    db = AuditDatabase()
    st.title("🔐 Acceso AuditPro")
    
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.subheader("Iniciar Sesión")
        email = st.text_input("Correo", key="l_email")
        passw = st.text_input("Clave", type="password", key="l_pass")
        if st.button("Entrar", use_container_width=True):
            h_pass = db.hash_password(passw)
            cursor = db.conn.cursor()
            cursor.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (email, h_pass))
            user = cursor.fetchone()
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.rerun()
            else:
                st.error("Datos incorrectos")

    with col_r:
        st.subheader("Registro de Auditor")
        n_name = st.text_input("Nombre Completo")
        n_email = st.text_input("Nuevo Correo")
        n_pass = st.text_input("Nueva Clave", type="password")
        if st.button("Registrar", use_container_width=True):
            val, msj = validar_password(n_pass)
            if not val: st.error(msj)
            else:
                try:
                    cursor = db.conn.cursor()
                    cursor.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?, ?, ?)", 
                                 (n_email, n_name, db.hash_password(n_pass)))
                    db.conn.commit()
                    st.success("¡Registrado! Ya puedes entrar.")
                except: st.error("El correo ya existe")

# --- VISTA: APLICACIÓN PRINCIPAL ---
def main_app():
    db = AuditDatabase()
    
    with st.sidebar:
        st.write(f"Bienvenido, **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.rerun()
        
        st.divider()
        st.header("➕ Nuevo Encargo")
        c_name = st.text_input("Cliente")
        c_year = st.number_input("Año", value=2025)
        if st.button("Guardar"):
            if c_name:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", 
                             (st.session_state.user_id, c_name, c_year))
                db.conn.commit()
                st.rerun()

    st.title("📋 Gestión de Encargos")
    df = pd.read_sql_query("SELECT id, client_name as 'Cliente', audit_year as 'Año' FROM clients WHERE user_id = ?", 
                           db.conn, params=(st.session_state.user_id,))
    
    if not df.empty:
        col_d1, col_d2 = st.columns(2)
        col_d1.download_button("📥 Excel", generar_excel(df), "reporte.xlsx")
        col_d2.download_button("📥 PDF", generar_pdf(df, st.session_state.user_name), "reporte.pdf")

        st.divider()
        sel_all = st.toggle("Seleccionar todos")
        df_edit = df.copy()
        df_edit.insert(0, "Borrar", sel_all)
        
        res = st.data_editor(df_edit, column_config={"id": None}, hide_index=True, use_container_width=True)
        
        ids = res[res["Borrar"] == True]["id"].tolist()
        if ids:
            confirm = st.text_input("Escribe ELIMINAR para borrar:")
            if st.button("Borrar Seleccionados", type="primary") and confirm == "ELIMINAR":
                cursor = db.conn.cursor()
                cursor.execute(f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(ids))})", ids)
                db.conn.commit()
                st.rerun()
    else:
        st.info("No hay encargos registrados.")

# --- CONTROLADOR DE FLUJO ---
if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        login_screen()
    else:
        main_app()
