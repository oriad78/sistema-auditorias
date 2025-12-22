import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro + NIA Compliance", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .instruction-box { background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 10px; border-radius: 5px; font-size: 14px; color: #0d47a1; }
    .audit-log { font-size: 12px; color: #666; font-style: italic; }
    .materiality-box { background-color: #f1f8e9; border: 1px solid #8bc34a; padding: 15px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- GESTIÓN DE BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_pro_v2.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Usuarios y Clientes
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente")')
    
    # NIA 230: Papeles de trabajo y Logs (Audit Trail)
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, user_name TEXT, action TEXT, timestamp DATETIME)')
    
    # NIA 320: Materialidad
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, benchmark_type TEXT, benchmark_value REAL, percentage REAL, planned_materiality REAL, tolerable_error REAL)')
    
    # Archivos
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
    
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

# --- PLANTILLA NIA ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación", "1010", "(NIA 220) Evaluación de Integridad", "Evaluar antecedentes y ética del cliente."),
    ("1100 - Planeación", "1110", "(NIA 300) Estrategia Global", "Documentar el alcance y tiempos del encargo."),
    ("1100 - Planeación", "1120", "(NIA 315) Control Interno", "Identificar riesgos de error material.")
]

# --- VISTAS ---
def vista_materialidad(client_id):
    st.markdown("### 📊 Calculadora de Materialidad (NIA 320)")
    conn = get_db_connection()
    
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            base = st.selectbox("Benchmark", ["Utilidad neta", "Activos Totales", "Ingresos Totales"])
            valor = st.number_input("Valor del Benchmark ($)", min_value=0.0)
        with col2:
            porc = st.slider("% Materialidad", 0.5, 10.0, 1.0)
        
        mp = valor * (porc / 100)
        et = mp * 0.75
        
        with col3:
            st.metric("Mat. Planeación", f"${mp:,.0f}")
            st.metric("Error Tolerable", f"${et:,.0f}")
            
        if st.button("Fijar Materialidad"):
            conn.execute("DELETE FROM materiality WHERE client_id=?", (client_id,))
            conn.execute("INSERT INTO materiality (client_id, benchmark_type, benchmark_value, percentage, planned_materiality, tolerable_error) VALUES (?,?,?,?,?,?)",
                         (client_id, base, valor, porc, mp, et))
            conn.commit()
            st.success("Materialidad guardada en papeles de trabajo.")
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
            
            nota_actual = st.text_area("Hallazgos y Conclusiones", value=row['user_notes'] or "", key=f"txt_{row['id']}")
            
            c1, c2 = st.columns(2)
            with c1:
                nuevo_estado = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"st_{row['id']}")
            
            if st.button("💾 Guardar y Firmar", key=f"btn_{row['id']}"):
                conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (nota_actual, nuevo_estado, row['id']))
                conn.commit()
                registrar_log(row['id'], st.session_state.user_name, f"Cambió estado a {nuevo_estado} y actualizó notas.")
                st.toast("Cambios registrados con éxito")
                st.rerun()
            
            # Mostrar Audit Trail (NIA 230)
            logs = conn.execute("SELECT user_name, action, timestamp FROM audit_logs WHERE step_id=? ORDER BY timestamp DESC", (row['id'],)).fetchall()
            if logs:
                st.markdown("**Historial de Cambios (Audit Trail):**")
                for l_user, l_act, l_time in logs:
                    st.markdown(f"<div class='audit-log'>• {l_time} - {l_user}: {l_act}</div>", unsafe_allow_html=True)
    conn.close()

def vista_principal():
    with st.sidebar:
        st.header(f"👤 {st.session_state.user_name}")
        if st.button("Salir"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.subheader("🆕 Nuevo Cliente")
        n_nom = st.text_input("Nombre Empresa")
        n_nit = st.text_input("NIT")
        if st.button("Crear Auditoría"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_nom, n_nit))
            cid = cur.lastrowid
            for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
            conn.commit()
            st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Auditorías")
        conn = get_db_connection()
        cls = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in cls.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if col_b.button("Abrir", key=f"open_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

def vista_login():
    st.title("⚖️ AuditPro: Sistema de Gestión de Auditoría")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ingresar")
        em = st.text_input("Correo")
        pw = st.text_input("Clave", type="password")
        if st.button("Entrar"):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (em, hash_pass(pw))).fetchone()
            if u:
                st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                st.rerun()
            else: st.error("Datos incorrectos")
    with col2:
        st.subheader("Registrarse")
        r_em = st.text_input("Nuevo Correo")
        r_fn = st.text_input("Nombre Completo")
        r_pw = st.text_input("Nueva Clave", type="password")
        if st.button("Crear Cuenta"):
            conn = get_db_connection()
            try:
                conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (r_em, r_fn, hash_pass(r_pw)))
                conn.commit()
                st.success("Cuenta creada. Ya puedes ingresar.")
            except: st.error("El correo ya existe")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
