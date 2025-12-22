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
    .status-text { font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS Y MIGRACIONES ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
    
    # MIGRACIÓN: Asegurar que existe la columna tipo_trabajo
    try:
        cursor.execute('SELECT tipo_trabajo FROM clients LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE clients ADD COLUMN tipo_trabajo TEXT DEFAULT "Auditoría"')
    
    conn.commit()
    conn.close()

create_tables()

# --- PLANTILLA MAESTRA ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar alto riesgo."),
    ("100 - Aceptación y continuación", "4000", "(ISA 200, 220, 300) Requisitos éticos e independencia", "Confirmar independencia."),
    ("100 - Aceptación y continuación", "4010", "Realizar otras tareas específicas relativas a independencia", "Verificar servicios no auditoría."),
    ("100 - Aceptación y continuación", "5000", "(ISA 210, 300) Carta de contratación actualizada", "Adjuntar PDF firmado."),
    ("150 - Administración", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación recursos."),
    ("1100 - Comprensión", "1000", "(ISA 315) Entendimiento del cliente y ambiente", "Análisis negocio."),
    ("1250 - Riesgo de Fraude", "1000", "(ISA 240, 315) Responder al riesgo de fraude", "Triángulo fraude.")
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

# --- VISTA: LOGIN ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    tab1, tab2 = st.tabs(["🔐 Ingreso", "📝 Registro"])
    with tab1:
        with st.form("login"):
            e = st.text_input("Correo")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                conn = get_db_connection()
                u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                conn.close()
                if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
                else: st.error("Acceso denegado")

# --- VISTA: PAPELERÍA ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    col_v, col_e = st.columns([1, 5])
    if col_v.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = col_e.toggle("⚙️ Configurar Encargo")

    if editar:
        with st.container(border=True):
            if st.button("🔄 Sincronizar Pasos (Incluir 4010)"):
                num = sincronizar_pasos_faltantes(client_id)
                st.success(f"Se agregaron {num} pasos."); st.rerun()
            if st.checkbox("Borrar encargo"):
                if st.button("🗑️ ELIMINAR"):
                    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                    conn.execute("DELETE FROM audit_steps WHERE client_id=?", (client_id,))
                    conn.commit(); conn.close(); del st.session_state.active_id; st.rerun()

    steps_df = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    if not steps_df.empty:
        for seccion in steps_df['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_df[steps_df['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    c_det, c_est = st.columns([3, 1])
                    with c_det:
                        notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"n_{sid}", height=80)
                        if st.button("💾 Guardar", key=f"s_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid)); conn.commit(); st.toast("Guardado")
                    with c_est:
                        colores = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
                        st.write(f"**Estado:** {colores.get(row['status'], '⚪')} {row['status']}")
                        nuevo = st.selectbox("Cambiar:", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid)); conn.commit(); st.rerun()
    conn.close()

# --- VISTA: DASHBOARD ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa"); ct = st.text_input("NIT")
        tipo_t = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Otros"])
        estado_i = st.selectbox("Estado Inicial", ["🔴 Pendiente", "🟡 En Proceso", "🟢 Cerrado"])
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo, estado) VALUES (?,?,?,?,?)", 
                       (st.session_state.user_id, cn, ct, tipo_t, estado_i.split(" ")[1]))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()
        st.divider()
        
        # --- LINKS HORIZONTALES ACTUALIZADOS ---
        st.subheader("🔗 Consultas Rápidas")
        c1, c2 = st.columns(2)
        with c1: st.markdown("[🔍 RUES](https://www.rues.org.co/)")
        with c2: st.markdown("[🔍 DIAN](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces)")

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Gestión de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, tipo_trabajo, estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                c2.write(f"_{r['tipo_trabajo']}_")
                cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
                c3.write(f"{cols_l.get(r['estado'], '⚪')} {r['estado']}")
                if c4.button("Abrir", key=f"b_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()
        conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
