import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
from fpdf import FPDF

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="AuditPro - Gestión Integral", layout="wide")

# --- CONEXIÓN Y MIGRACIÓN DE BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Usuarios
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        full_name TEXT,
        password_hash TEXT)''')
    
    # Clientes (con nuevas columnas)
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        client_name TEXT,
        client_nit TEXT,
        audit_year INTEGER,
        tipo_encargo TEXT,
        estado TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Migración: Agregar columnas si no existen (evita errores al actualizar)
    columnas = [('client_nit', 'TEXT'), ('tipo_encargo', 'TEXT'), ('estado', 'TEXT')]
    for col_name, col_type in columnas:
        try:
            cursor.execute(f'ALTER TABLE clients ADD COLUMN {col_name} {col_type}')
        except:
            pass
            
    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES DE APOYO ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validar_password(p):
    return len(p) >= 8 and re.search("[A-Z]", p) and re.search("[0-9]", p) and re.search("[!@#$%^&*]", p)

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
    pdf.cell(190, 10, "REPORTE DE GESTION DE AUDITORIA", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(190, 10, f"Auditor: {auditor} | Generado: {pd.Timestamp.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", 'B', 8)
    cols = ["Cliente", "NIT", "Año", "Tipo", "Estado"]
    widths = [55, 35, 20, 45, 35]
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 10, col, 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 8)
    for _, row in df.iterrows():
        pdf.cell(widths[0], 10, str(row['Cliente'])[:30], 1)
        pdf.cell(widths[1], 10, str(row['NIT']), 1)
        pdf.cell(widths[2], 10, str(row['Año']), 1)
        pdf.cell(widths[3], 10, str(row['Tipo']), 1)
        pdf.cell(widths[4], 10, str(row['Estado']), 1)
        pdf.ln()
    return bytes(pdf.output())

# --- VISTA: LOGIN / REGISTRO ---
def vista_login():
    st.title("🔐 Sistema AuditPro")
    tab_login, tab_reg = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab_login:
        email = st.text_input("Correo electrónico", key="l_email")
        password = st.text_input("Contraseña", type="password", key="l_pass")
        if st.button("Ingresar"):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (email, hash_pass(password)))
            user = cursor.fetchone()
            conn.close()
            if user:
                st.session_state.user_id, st.session_state.user_name = user[0], user[1]
                st.rerun()
            else: st.error("Credenciales inválidas")

    with tab_reg:
        n_name = st.text_input("Nombre y Apellido")
        n_email = st.text_input("Correo")
        n_pass = st.text_input("Clave (8+ carac, Mayús, Núm, Especial)", type="password")
        n_conf = st.text_input("Confirmar Clave", type="password")
        if st.button("Crear Cuenta"):
            if n_pass != n_conf: st.error("Las claves no coinciden")
            elif not validar_password(n_pass): st.error("La clave no cumple los requisitos de seguridad")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?, ?, ?)", (n_email, n_name, hash_pass(n_pass)))
                    conn.commit()
                    conn.close()
                    st.success("¡Registro exitoso!")
                except: st.error("El correo ya existe")

# --- VISTA: APP PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.title(f"💼 Auditor: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id
            st.rerun()
        
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        c_name = st.text_input("Nombre de la Empresa")
        c_nit = st.text_input("NIT")
        c_year = st.number_input("Año", value=2025)
        c_tipo = st.selectbox("Tipo de Encargo", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Auditoría Interna", "Otro"])
        c_estado = st.selectbox("Estado Inicial", ["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"])
        
        if st.button("Guardar"):
            if c_name and c_nit:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, client_nit, audit_year, tipo_encargo, estado) VALUES (?, ?, ?, ?, ?, ?)", 
                             (st.session_state.user_id, c_name, c_nit, c_year, c_tipo, c_estado))
                conn.commit()
                conn.close()
                st.rerun()
            else: st.warning("Nombre y NIT son obligatorios")

    st.title("📋 Gestión de Auditorías")
    
    # 3. BUSCADOR
    busqueda = st.text_input("🔍 Buscar por Nombre de Empresa o NIT...", placeholder="Escriba aquí para filtrar...")

    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT id, client_name as 'Cliente', client_nit as 'NIT', 
        audit_year as 'Año', tipo_encargo as 'Tipo', estado as 'Estado'
        FROM clients WHERE user_id = ?""", conn, params=(st.session_state.user_id,))
    conn.close()

    # Filtrado lógico del buscador
    if busqueda:
        df = df[df['Cliente'].str.contains(busqueda, case=False, na=False) | 
                df['NIT'].str.contains(busqueda, case=False, na=False)]

    if not df.empty:
        col1, col2 = st.columns(2)
        col1.download_button("📊 Excel", generar_excel(df), "auditoria.xlsx")
        col2.download_button("📄 PDF", generar_pdf(df, st.session_state.user_name), "auditoria.pdf")
        
        st.divider()
        st.subheader("⚙️ Edición y Eliminación")
        
        # Tabla editable para cambiar estados rápidamente
        df_edit = df.copy()
        df_edit.insert(0, "Borrar", False)
        
        res = st.data_editor(
            df_edit,
            column_config={
                "id": None,
                "Estado": st.column_config.SelectboxColumn("Estado", options=["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"]),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Auditoría Interna", "Otro"])
            },
            hide_index=True,
            use_container_width=True
        )

        # Guardar cambios si se editó la tabla (opcional)
        if st.button("💾 Guardar Cambios en la Tabla"):
            conn = get_db_connection()
            cursor = conn.cursor()
            for index, row in res.iterrows():
                cursor.execute("UPDATE clients SET estado=?, tipo_encargo=? WHERE id=?", (row['Estado'], row['Tipo'], row['id']))
            conn.commit()
            conn.close()
            st.success("Cambios guardados.")
            st.rerun()

        # Lógica de borrado
        ids_borrar = res[res["Borrar"] == True]["id"].tolist()
        if ids_borrar:
            if st.button("❌ Eliminar Seleccionados", type="primary"):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(ids_borrar))})", ids_borrar)
                conn.commit()
                conn.close()
                st.rerun()
    else:
        st.info("No se encontraron registros.")

if 'user_id' not in st.session_state:
    vista_login()
else:
    vista_principal()
