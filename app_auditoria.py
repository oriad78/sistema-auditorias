import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Gestión Segura", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .instruction-box { background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 10px; border-radius: 5px; font-size: 14px; color: #0d47a1; }
    .audit-log { font-size: 11px; color: #777; border-top: 1px solid #eee; padding-top: 2px; }
    </style>
""", unsafe_allow_html=True)

# --- GESTIÓN DE BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_pro_v3.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, user_name TEXT, action TEXT, timestamp DATETIME)')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, benchmark_type TEXT, benchmark_value REAL, percentage REAL, planned_materiality REAL, tolerable_error REAL)')
    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES LÓGICAS ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def registrar_log(step_id, user_name, action):
    conn = get_db_connection()
    conn.execute("INSERT INTO audit_logs (step_id, user_name, action, timestamp) VALUES (?,?,?,?)",
                 (step_id, user_name, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# --- VISTAS ---
def vista_materialidad(client_id):
    st.markdown("### 📊 Materialidad (NIA 320)")
    conn = get_db_connection()
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            base = st.selectbox("Base", ["Utilidad neta", "Activos Totales", "Ingresos Totales"])
            valor = st.number_input("Valor Base ($)", min_value=0.0)
        with col2:
            porc = st.slider("% Materialidad", 0.5, 10.0, 1.0)
        mp = valor * (porc / 100)
        et = mp * 0.75
        with col3:
            st.metric("MP (Planeación)", f"${mp:,.0f}")
            st.metric("ET (Ejecución)", f"${et:,.0f}")
        if st.button("Guardar Materialidad"):
            conn.execute("DELETE FROM materiality WHERE client_id=?", (client_id,))
            conn.execute("INSERT INTO materiality (client_id, benchmark_type, benchmark_value, percentage, planned_materiality, tolerable_error) VALUES (?,?,?,?,?,?)",
                         (client_id, base, valor, porc, mp, et))
            conn.commit()
            st.success("Cálculo guardado.")
    conn.close()

def vista_papeles(client_id, client_name):
    st.title(f"📂 Expediente: {client_name}")
    if st.button("⬅️ Regresar"):
        del st.session_state.active_id
        st.rerun()
    vista_materialidad(client_id)
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
    for _, row in steps.iterrows():
        with st.expander(f"🔹 {row['step_code']} - {row['description']} ({row['status']})"):
            st.markdown(f"<div class='instruction-box'>{row['instructions']}</div>", unsafe_allow_html=True)
            nota_actual = st.text_area("Hallazgos", value=row['user_notes'] or "", key=f"txt_{row['id']}")
            if st.button("💾 Guardar y Firmar", key=f"btn_{row['id']}"):
                conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (nota_actual, row['id']))
                conn.commit()
                registrar_log(row['id'], st.session_state.user_name, "Actualizó papeles de trabajo.")
                st.toast("Documentación firmada")
    conn.close()

def vista_principal():
    with st.sidebar:
        st.header(f"👤 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            st.session_state.clear()
            st.rerun()
    
    if 'active_id' in st.session_state:
        vista_papeles(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Dashboard de Auditorías")
        conn = get_db_connection()
        cls = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in cls.iterrows():
            if st.button(f"📄 Abrir {r['client_name']}", key=f"cl_{r['id']}"):
                st.session_state.active_id = r['id']
                st.session_state.active_name = r['client_name']
                st.rerun()
        conn.close()

def vista_login():
    st.title("⚖️ AuditPro")
    tab1, tab2, tab3 = st.tabs(["Ingresar", "Registrarse", "Recuperar Acceso"])
    
    with tab1:
        em = st.text_input("Correo", key="l_em")
        pw = st.text_input("Clave", type="password", key="l_pw")
        if st.button("Acceder"):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (em, hash_pass(pw))).fetchone()
            if u:
                st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                st.rerun()
            else: st.error("Credenciales inválidas")
            conn.close()

    with tab2:
        r_fn = st.text_input("Nombre Completo")
        r_em = st.text_input("Correo")
        r_pw1 = st.text_input("Contraseña", type="password", key="r1")
        r_pw2 = st.text_input("Confirme Contraseña", type="password", key="r2")
        if st.button("Crear Cuenta"):
            if r_pw1 != r_pw2: st.error("Las claves no coinciden")
            elif len(r_pw1) < 6: st.warning("Mínimo 6 caracteres")
            else:
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (r_em, r_fn, hash_pass(r_pw1)))
                    conn.commit()
                    st.success("¡Listo! Ya puedes ingresar.")
                except: st.error("El correo ya está en uso")
                conn.close()

    with tab3:
        st.subheader("Restablecer Clave")
        f_em = st.text_input("Introduce tu correo electrónico")
        st.info("Validación: ¿Cuánto es 5 + 7?")
        f_ans = st.number_input("Tu respuesta", step=1)
        f_pwnew = st.text_input("Nueva Contraseña", type="password", key="f_pw")
        
        if st.button("Cambiar Contraseña"):
            if f_ans == 12:
                conn = get_db_connection()
                user = conn.execute("SELECT id FROM users WHERE email=?", (f_em,)).fetchone()
                if user:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(f_pwnew), user[0]))
                    conn.commit()
                    st.success("Contraseña actualizada exitosamente.")
                else:
                    st.error("Correo no encontrado.")
                conn.close()
            else:
                st.error("Validación incorrecta.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
