import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema de Auditoría", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    .folder-style { font-weight: bold; color: #1f77b4; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, audit_year INTEGER, tipo_encargo TEXT, estado TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB, file_type TEXT)')
    conn.commit()
    conn.close()

create_tables()

# --- PLANTILLA MAESTRA INTEGRAL (Basada en tus imágenes) ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar alto riesgo."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Requisitos éticos e independencia", "Confirmar independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia", "Revisar servicios no auditoría."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Carta de contratación actualizada", "Adjuntar PDF firmado."),
    ("100 - Aceptación y continuación de clientes", "1200", "(ISA 600) Auditoría del grupo / Multilocation", "Alcance participación."),
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación recursos."),
    ("150 - Administración del proyecto", "3000", "(ISA 300) Monitorear avance del proyecto", "Control ejecución."),
    ("150 - Administración del proyecto", "2000", "Objetivos de desarrollo personal del equipo", "Reunión inicio."),
    ("1100 - Comprensión del cliente", "1000", "(ISA 315) Entendimiento del cliente y ambiente", "Análisis negocio."),
    ("1100 - Comprensión del cliente", "1500", "(ISA 315, 520) Revisión analítica preliminar", "Variaciones."),
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, 315) Responder al riesgo de fraude", "Triángulo fraude."),
    ("1700 - Evaluación del riesgo/significatividad", "2000", "(ISA 250, 315) Comprensión de leyes y reglamentaciones", "Matriz legal.")
]

# --- FUNCIONES LÓGICAS ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def inicializar_programa_auditoria(client_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM audit_steps WHERE client_id = ?", (client_id,))
    for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (client_id, sec, cod, desc, ins))
    conn.commit()
    conn.close()

def sincronizar_pasos_faltantes(client_id):
    conn = get_db_connection()
    existentes = [r[0] for r in conn.execute("SELECT step_code FROM audit_steps WHERE client_id = ?", (client_id,)).fetchall()]
    agregados = 0
    for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
        if cod not in existentes:
            conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (client_id, sec, cod, desc, ins))
            agregados += 1
    conn.commit(); conn.close()
    return agregados

# --- VISTA: LOGIN ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    with t1:
        if 'modo_recuperar' not in st.session_state:
            with st.form("login_form"):
                e = st.text_input("Correo electrónico", key="l_user", autocomplete="email")
                p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Ingresar"):
                    conn = get_db_connection()
                    u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                    conn.close()
                    if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
                    else: st.error("Datos incorrectos")
            if st.button("¿Olvidó su contraseña?"): st.session_state.modo_recuperar = True; st.rerun()
        else:
            with st.form("rec_form"):
                st.info("### Recuperar Contraseña")
                re = st.text_input("Correo registrado"); rn = st.text_input("Nombre completo")
                np = st.text_input("Nueva Contraseña", type="password")
                if st.form_submit_button("Resetear"):
                    conn = get_db_connection()
                    user = conn.execute("SELECT id FROM users WHERE email=? AND full_name=?", (re, rn)).fetchone()
                    if user:
                        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(np), user[0]))
                        conn.commit(); conn.close(); st.success("Éxito"); del st.session_state.modo_recuperar; st.rerun()
                    else: st.error("Datos no coinciden"); conn.close()
            if st.button("Volver"): del st.session_state.modo_recuperar; st.rerun()
    with t2:
        with st.form("reg_form"):
            n = st.text_input("Nombre Completo"); em = st.text_input("Correo"); ps = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Crear Cuenta"):
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (em, n, hash_pass(ps)))
                    conn.commit(); st.success("Registrado")
                except: st.error("Error en registro")
                finally: conn.close()

# --- VISTA: EXPEDIENTE CON CARPETAS ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    c_data = conn.execute("SELECT client_name, client_nit FROM clients WHERE id=?", (client_id,)).fetchone()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    c1, c2 = st.columns([1, 4])
    if c1.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = c2.toggle("⚙️ Configurar Encargo")

    if editar:
        col_iz, col_de = st.columns([2,1])
        with col_iz:
            with st.container(border=True):
                st.subheader("📝 Datos Generales")
                n_n = st.text_input("Empresa", value=c_data[0]); n_t = st.text_input("NIT", value=c_data[1])
                if st.button("Guardar Cambios"):
                    conn.execute("UPDATE clients SET client_name=?, client_nit=? WHERE id=?", (n_n, n_t, client_id))
                    conn.commit(); st.session_state.active_name = n_n; st.rerun()
                st.divider()
                if st.button("🔄 Sincronizar Pasos (Incluye 4010)"):
                    num = sincronizar_pasos_faltantes(client_id)
                    st.success(f"Se agregaron {num} pasos nuevos."); st.rerun()
        with col_de:
            with st.container(border=True):
                st.subheader("⚠️ Peligro")
                if st.checkbox("Confirmar eliminación"):
                    if st.button("🗑️ BORRAR TODO"):
                        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                        conn.execute("DELETE FROM audit_steps WHERE client_id=?", (client_id,))
                        conn.commit(); conn.close(); del st.session_state.active_id; st.rerun()

    # --- LISTADO POR CARPETAS (SECCIONES) ---
    steps_df = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    if steps_df.empty:
        if st.button("Cargar Programa Maestro"): inicializar_programa_auditoria(client_id); st.rerun()
    else:
        for seccion in steps_df['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_df[steps_df['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    col_txt, col_op = st.columns([3, 1])
                    with col_txt:
                        notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"nt_{sid}", height=80)
                        if st.button("💾 Guardar", key=f"sv_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                            conn.commit(); st.toast("Guardado")
                    with col_op:
                        nuevo_est = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"es_{sid}")
                        if nuevo_est != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo_est, sid)); conn.commit(); st.rerun()
    conn.close()

# --- DASHBOARD PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider(); st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa"); ct = st.text_input("NIT")
        st.markdown("[🔍 RUES](https://www.rues.org.co/) | [🔍 DIAN](https://muisca.dian.gov.co/)")
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, estado) VALUES (?,?,?,?)", (st.session_state.user_id, cn, ct, "🔴 Pendiente"))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Encargos")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        conn.close()
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Abrir", key=f"op_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
