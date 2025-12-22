import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema de Auditoría", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, estado TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    conn.commit()
    conn.close()

create_tables()

# --- PLANTILLA MAESTRA (Incluye el paso 4010 y otros de tus imágenes) ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar alto riesgo."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Requisitos éticos e independencia", "Confirmar independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia", "Verificar servicios adicionales."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Carta de contratación actualizada", "Adjuntar documento firmado."),
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación de recursos."),
    ("150 - Administración del proyecto", "3000", "(ISA 300) Monitorear avance del proyecto", "Control de cronograma."),
    ("1100 - Comprensión del cliente", "1000", "(ISA 315) Entendimiento del cliente", "Análisis de entorno."),
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, 315) Responder al riesgo de fraude", "Triángulo del fraude.")
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
    # Buscamos qué códigos ya existen para no duplicar
    existentes = [r[0] for r in conn.execute("SELECT step_code FROM audit_steps WHERE client_id = ?", (client_id,)).fetchall()]
    agregados = 0
    for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
        if cod not in existentes:
            conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (client_id, sec, cod, desc, ins))
            agregados += 1
    conn.commit()
    conn.close()
    return agregados

# --- VISTAS ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    with st.form("login_form"):
        e = st.text_input("Correo")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar"):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
            else: st.error("Datos incorrectos")

def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    col1, col2 = st.columns([1, 4])
    if col1.button("⬅️ Volver"): del st.session_state.active_id; st.rerun()
    editar = col2.toggle("⚙️ Configurar Encargo")

    if editar:
        st.subheader("🛠️ Panel de Actualización")
        if st.button("🔄 Sincronizar Pasos Faltantes (Añadir 4010 y otros)"):
            num = sincronizar_pasos_faltantes(client_id)
            st.success(f"¡Sincronización exitosa! Se añadieron {num} pasos nuevos.")
            st.rerun()
        st.divider()

    # --- VISTA DE CARPETAS ---
    steps_df = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    if steps_df.empty:
        if st.button("Cargar Programa"): inicializar_programa_auditoria(client_id); st.rerun()
    else:
        for seccion in steps_df['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_df[steps_df['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"nt_{sid}")
                    if st.button("💾 Guardar", key=f"sv_{sid}"):
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                        conn.commit(); st.toast("Guardado")
    conn.close()

def vista_principal():
    with st.sidebar:
        st.write(f"Usuario: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa"); ct = st.text_input("NIT")
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, estado) VALUES (?,?,?,?)", (st.session_state.user_id, cn, ct, "Pendiente"))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Encargos")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        conn.close()
        for _, r in df.iterrows():
            if st.button(f"Abrir: {r['client_name']}", key=f"op_{r['id']}"):
                st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
