import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from io import BytesIO
from docx import Document
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    .file-box { background-color: #f8f9fa; padding: 5px; border-radius: 5px; border: 1px solid #eee; margin-bottom: 2px; display: flex; justify-content: space-between; align-items: center; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
    
    # Asegurar columna tipo_trabajo
    try:
        cursor.execute('SELECT tipo_trabajo FROM clients LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE clients ADD COLUMN tipo_trabajo TEXT DEFAULT "Auditoría"')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                      benchmark_value REAL, percentage REAL, planned_materiality REAL)''')
    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES DE EXPORTACIÓN ---
def crear_pdf(df, client_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(211, 47, 47)
    pdf.cell(190, 10, "AUDITPRO - REPORTE DE EJECUCIÓN", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(190, 10, f"Cliente: {client_name}", ln=True, align='C')
    pdf.line(10, 32, 200, 32)
    for _, row in df.iterrows():
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.multi_cell(190, 7, f"PASO {row['step_code']}: {row['description']}")
        pdf.set_font("Arial", size=9)
        pdf.cell(190, 7, f"ESTADO: {row['status']}", ln=True)
        pdf.multi_cell(190, 7, f"NOTAS: {row['user_notes'] or 'N/A'}")
    return bytes(pdf.output())

# --- VISTA PAPELES DE TRABAJO ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    if st.button("⬅️ Volver"):
        del st.session_state.active_id
        conn.close()
        st.rerun()

    steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
    
    for seccion in steps_db['section_name'].unique():
        with st.expander(f"📁 {seccion}", expanded=True):
            pasos = steps_db[steps_db['section_name'] == seccion]
            for _, row in pasos.iterrows():
                sid = row['id']
                st.markdown(f"<div class='step-header'>{cols_l.get(row['status'], '⚪')} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                
                c_det, c_est, c_file = st.columns([3, 1, 1.5])
                with c_det:
                    notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"n_{sid}", height=100)
                    if st.button("💾 Guardar Notas", key=f"s_{sid}"):
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                        conn.commit()
                        st.toast("Notas guardadas")

                with c_est:
                    st.write(f"Estado: {cols_l.get(row['status'])}")
                    nuevo = st.selectbox("Cambiar:", ["Pendiente", "En Proceso", "Cerrado"], 
                                         index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), 
                                         key=f"e_{sid}")
                    if nuevo != row['status']:
                        conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid))
                        conn.commit()
                        st.rerun()

                with c_file:
                    # SUBIDA DE ARCHIVOS MEJORADA
                    up = st.file_uploader("Adjuntar archivo", key=f"up_{sid}", label_visibility="collapsed")
                    if up is not None:
                        # Evitar duplicados comparando nombre y paso en la sesión
                        last_up_key = f"last_up_{sid}"
                        if st.session_state.get(last_up_key) != up.name:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", 
                                        (sid, up.name, up.read()))
                            conn.commit()
                            st.session_state[last_up_key] = up.name
                            st.rerun()

                    # LISTADO DE ARCHIVOS CON BOTÓN DE ELIMINAR
                    archivos = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                    for fid, fname, fdata in archivos:
                        col_name, col_del, col_dl = st.columns([3, 1, 1])
                        col_name.markdown(f"📄 {fname[:15]}...")
                        
                        # Botón Eliminar
                        if col_del.button("🗑️", key=f"del_{fid}"):
                            conn.execute("DELETE FROM step_files WHERE id=?", (fid,))
                            conn.commit()
                            st.rerun()
                        
                        # Botón Descargar
                        col_dl.download_button("📥", data=fdata, file_name=fname, key=f"dl_{fid}")
    conn.close()

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa")
        ct = st.text_input("NIT")
        tipo = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa", "Otros"])
        if st.button("Crear"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo) VALUES (?,?,?,?)", 
                        (st.session_state.user_id, cn, ct, tipo))
            cid = cur.lastrowid
            # Inicializar pasos
            for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", 
                            (cid, sec, cod, desc, ins))
            conn.commit()
            conn.close()
            st.rerun()
        st.divider()
        st.subheader("🔗 Consultas Rápidas")
        c1, c2 = st.columns(2)
        with c1: st.markdown("[🔍 RUES](https://www.rues.org.co/busqueda-avanzada)")
        with c2: st.markdown("[🔍 DIAN](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces)")

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Gestión de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, tipo_trabajo, estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
        
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                c1.write(f"{cols_l.get(r['estado'], '⚪')} **{r['client_name']}**")
                c2.write(f"_{r['tipo_trabajo']}_")
                c3.write(f"{r['estado']}")
                if c4.button("Abrir", key=f"b_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

# Se mantienen las funciones de hash_pass, vista_login y el bloque main igual al código anterior.
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación", "1000", "Evaluar cliente", "Integridad"),
    ("1100 - Comprensión", "1000", "Entendimiento negocio", "Análisis")
]

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def vista_login():
    st.title("⚖️ AuditPro")
    t1, t2 = st.tabs(["Ingreso", "Registro"])
    with t1:
        with st.form("login"):
            e, p = st.text_input("Correo"), st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                conn = get_db_connection()
                u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                conn.close()
                if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
                else: st.error("Acceso incorrecto")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
