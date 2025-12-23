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
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 10px; 
        margin-bottom: 10px; 
        border-radius: 5px;
        font-size: 14px;
        color: #0d47a1;
    }
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
    
    # Tabla para Logs de Auditoría (Cumplimiento NIA 230)
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      step_id INTEGER, 
                      user_id INTEGER, 
                      action TEXT, 
                      old_value TEXT, 
                      new_value TEXT, 
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    try:
        cursor.execute('SELECT tipo_trabajo FROM clients LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE clients ADD COLUMN tipo_trabajo TEXT DEFAULT "Auditoría"')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                     benchmark_value REAL, percentage REAL, planned_materiality REAL)''')
    conn.commit()
    conn.close()

# --- Función para registrar cambios (Corregida y Blindada) ---
def log_change(step_id, user_id, action, old_val, new_val):
    conn = get_db_connection()
    try:
        # Intentamos insertar el log
        conn.execute("INSERT INTO audit_logs (step_id, user_id, action, old_value, new_value) VALUES (?,?,?,?,?)",
                     (step_id, user_id, action, str(old_val), str(new_val)))
        conn.commit()
    except sqlite3.OperationalError as e:
        # Si falla porque la tabla no existe, la creamos al vuelo y reintentamos
        if "no such table" in str(e):
            conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            step_id INTEGER, 
                            user_id INTEGER, 
                            action TEXT, 
                            old_value TEXT, 
                            new_value TEXT, 
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
            # Reintentamos la inserción ahora que la tabla existe
            conn.execute("INSERT INTO audit_logs (step_id, user_id, action, old_value, new_value) VALUES (?,?,?,?,?)",
                         (step_id, user_id, action, str(old_val), str(new_val)))
            conn.commit()
        else:
            # Si es otro error (ej: base de datos bloqueada), lo dejamos pasar para verlo
            raise e
    finally:
        conn.close()

create_tables()

# --- PLANTILLA MAESTRA ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación", "1000", "(ISA 220, 300) Evaluar la aceptación del cliente", "Revise la integridad de la gerencia, antecedentes penales y reputación en el mercado. Documente si existe algún conflicto de intereses."),
    ("100 - Aceptación y continuación", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar si la complejidad del encargo requiere un socio de revisión de calidad independiente para asegurar el cumplimiento normativo."),
    ("1100 - Administración", "1000", "(ISA 315) Entendimiento del cliente y su ambiente", "Realice un análisis del sector, marco regulatorio y naturaleza de la entidad. Incluya el sistema de información y control interno."),
    ("1100 - Administración", "5000", "(ISA 210) Carta de compromiso", "Asegúrese de que la carta de encargo esté firmada por el representante legal y cubra el alcance de la auditoría 2024-2025.")
]

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
                
                if row['instructions']:
                    st.markdown(f"<div class='instruction-box'><strong>💡 Guía:</strong><br>{row['instructions']}</div>", unsafe_allow_html=True)
                
                c_det, c_est, c_file = st.columns([3, 1, 1.5])
                with c_det:
                    notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"n_{sid}", height=150)
                    if st.button("💾 Guardar Notas", key=f"s_{sid}"):
                        log_change(sid, st.session_state.user_id, "Cambio de Notas", row['user_notes'], notas)
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                        conn.commit()
                        st.toast("Notas y log guardados")

                with c_est:
                    st.write(f"Estado: {cols_l.get(row['status'])}")
                    nuevo = st.selectbox("Cambiar:", ["Pendiente", "En Proceso", "Cerrado"], 
                                         index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), 
                                         key=f"e_{sid}")
                    if nuevo != row['status']:
                        log_change(sid, st.session_state.user_id, "Cambio de Estado", row['status'], nuevo)
                        conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid))
                        conn.commit()
                        st.rerun()

                with c_file:
                    up = st.file_uploader("Adjuntar", key=f"up_{sid}", label_visibility="collapsed")
                    if up is not None:
                        last_up_key = f"last_up_{sid}"
                        if st.session_state.get(last_up_key) != up.name:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", 
                                        (sid, up.name, up.read()))
                            conn.commit()
                            st.session_state[last_up_key] = up.name
                            st.rerun()
                    
                    archivos = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                    for fid, fname, fdata in archivos:
                        col_n, col_d, col_dl = st.columns([3, 1, 1])
                        col_n.markdown(f"📄 {fname[:10]}...")
                        if col_d.button("🗑️", key=f"del_{fid}"):
                            conn.execute("DELETE FROM step_files WHERE id=?", (fid,))
                            conn.commit()
                            st.rerun()
                        col_dl.download_button("📥", data=fdata, file_name=fname, key=f"dl_{fid}")
    conn.close()

# --- VISTA PRINCIPAL & LOGIN (Resto del código permanece igual) ---
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
            for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", 
                            (cid, sec, cod, desc, ins))
            conn.commit()
            conn.close()
            st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Gestión de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, tipo_trabajo, estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                c1.write(f"**{r['client_name']}**")
                c2.write(f"_{r['tipo_trabajo']}_")
                c3.write(f"{r['estado']}")
                if c4.button("Abrir", key=f"b_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

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
                if u: 
                    st.session_state.user_id = u[0]
                    st.session_state.user_name = u[1]
                    st.rerun()
                else: st.error("Acceso incorrecto")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()

