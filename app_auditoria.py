import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    .folder-label { font-size: 18px; font-weight: bold; color: #1f77b4; }
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

# --- PLANTILLA MAESTRA ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP", "Evaluar riesgo de la entidad."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Requisitos éticos e independencia", "Confirmar independencia del equipo."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia", "Verificar servicios no auditoría."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Carta de contratación actualizada", "Adjuntar PDF firmado."),
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación de recursos."),
    ("1100 - Comprensión del cliente", "1000", "(ISA 315) Entendimiento del cliente y su entorno", "Análisis del negocio."),
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, 315) Evaluar y responder al riesgo de fraude", "Triángulo del fraude."),
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
    conn.commit(); conn.close()

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

# --- VISTA: LOGIN Y RECUPERACIÓN ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registro"])
    with t1:
        if 'modo_rec' not in st.session_state:
            with st.form("l_form"):
                e = st.text_input("Correo"); p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Ingresar"):
                    conn = get_db_connection()
                    u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                    conn.close()
                    if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
                    else: st.error("Error de acceso")
            if st.button("¿Olvidó su contraseña?"): st.session_state.modo_rec = True; st.rerun()
        else:
            with st.form("r_form"):
                st.info("Validación de Identidad")
                re = st.text_input("Correo registrado"); rn = st.text_input("Nombre completo registrado")
                np = st.text_input("Nueva Contraseña", type="password")
                if st.form_submit_button("Resetear"):
                    conn = get_db_connection()
                    user = conn.execute("SELECT id FROM users WHERE email=? AND full_name=?", (re, rn)).fetchone()
                    if user:
                        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(np), user[0]))
                        conn.commit(); conn.close(); st.success("Contraseña actualizada"); del st.session_state.modo_rec; st.rerun()
                    else: st.error("Datos no coinciden"); conn.close()
            if st.button("Volver"): del st.session_state.modo_rec; st.rerun()

# --- VISTA: EXPEDIENTE NIA ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    c_data = conn.execute("SELECT client_name, client_nit FROM clients WHERE id=?", (client_id,)).fetchone()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    col_v, col_e = st.columns([1, 5])
    if col_v.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = col_e.toggle("⚙️ Configurar Encargo")

    if editar:
        c_iz, c_de = st.columns([2,1])
        with c_iz:
            with st.container(border=True):
                st.subheader("📝 Datos e Independencia")
                n_n = st.text_input("Nombre Empresa", value=c_data[0])
                n_t = st.text_input("NIT", value=c_data[1])
                if st.button("💾 Guardar Cambios"):
                    conn.execute("UPDATE clients SET client_name=?, client_nit=? WHERE id=?", (n_n, n_t, client_id))
                    conn.commit(); st.session_state.active_name = n_n; st.rerun()
                st.divider()
                if st.button("🔄 Sincronizar Pasos (Añadir 4010)"):
                    num = sincronizar_pasos_faltantes(client_id)
                    st.success(f"Se añadieron {num} pasos nuevos."); st.rerun()
        with c_de:
            with st.container(border=True):
                st.subheader("⚠️ Zona de Peligro")
                if st.checkbox("Confirmar borrado total"):
                    if st.button("🗑️ ELIMINAR ENCARGO"):
                        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                        conn.execute("DELETE FROM audit_steps WHERE client_id=?", (client_id,))
                        conn.commit(); conn.close(); del st.session_state.active_id; st.rerun()

    # --- RENDERIZADO DE CARPETAS ---
    steps_df = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    if steps_df.empty:
        if st.button("🚀 Cargar Programa NIA"): inicializar_programa_auditoria(client_id); st.rerun()
    else:
        for seccion in steps_df['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_df[steps_df['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    st.caption(f"Guía: {row['instructions']}")
                    
                    c_txt, c_stat = st.columns([3, 1])
                    with c_txt:
                        notas = st.text_area("Desarrollo / Hallazgos", value=row['user_notes'] or "", key=f"n_{sid}", height=100)
                        if st.button("💾 Guardar", key=f"s_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                            conn.commit(); st.toast("Guardado")
                    
                    with c_stat:
                        # BOTONES DE ESTADO
                        n_est = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], 
                                           index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if n_est != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (n_est, sid)); conn.commit(); st.rerun()
                        
                        # GESTIÓN DE ARCHIVOS
                        up = st.file_uploader("Adjuntar", key=f"u_{sid}")
                        if up:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", (sid, up.name, up.read()))
                            conn.commit(); st.rerun()
                        
                        # Listar archivos
                        files = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                        for fid, fname, fdata in files:
                            st.download_button(f"📄 {fname}", fdata, file_name=fname, key=f"d_{fid}")
    conn.close()

# --- VISTA: DASHBOARD ---
def vista_principal():
    with st.sidebar:
        st.write(f"💼 Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Nombre Empresa"); ct = st.text_input("NIT")
        if st.button("Crear Encargo"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, cn, ct))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()
        st.divider()
        st.subheader("🔗 Enlaces Externos")
        st.markdown("[🔍 RUES - Consulta Empresarial](https://www.rues.org.co/)")
        st.markdown("[🔍 DIAN - Consulta NIT](https://muisca.dian.gov.co/WebRutMuisca/ConsultaEstadoRut.faces)")

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("📂 Mis Encargos de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        conn.close()
        for _, r in df.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"### {r['client_name']}\nNIT: {r['client_nit']}")
                if col_b.button("Abrir Expediente", key=f"btn_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
