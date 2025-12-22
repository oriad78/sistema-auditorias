import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Profesional", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; }
    .instruction-box { background-color: #f0f7ff; border-left: 5px solid #007bff; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    .stButton>button { border-radius: 20px; font-weight: bold; }
    .audit-log { font-size: 11px; color: #777; border-top: 1px dotted #ccc; padding: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- GESTIÓN DE BASE DE DATOS ---
def get_db_connection():
    # Versión final estable
    return sqlite3.connect('audit_pro_final.db', timeout=10, check_same_thread=False)

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

# --- FUNCIONES DE SEGURIDAD Y LOGS ---
def normalizar_correo(email):
    return email.strip().lower()

def hash_pass(password):
    """Limpia espacios y genera hash SHA-256."""
    clean_password = password.strip()
    return hashlib.sha256(clean_password.encode()).hexdigest()

def registrar_log(step_id, user_name, action):
    conn = get_db_connection()
    conn.execute("INSERT INTO audit_logs (step_id, user_name, action, timestamp) VALUES (?,?,?,?)",
                 (step_id, user_name, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# --- VISTAS DE NEGOCIO ---
def vista_materialidad(client_id):
    st.markdown("### 📊 Importancia Relativa (NIA 320)")
    conn = get_db_connection()
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            base = st.selectbox("Benchmark", ["Utilidad neta", "Activos Totales", "Ingresos Totales"])
            valor = st.number_input("Valor Base ($)", min_value=0.0, format="%.2f")
        with col2:
            porc = st.slider("% Materialidad", 0.5, 5.0, 1.0, step=0.1)
        
        mp = valor * (porc / 100)
        et = mp * 0.75 # Error Tolerable estándar
        
        with col3:
            st.metric("Mat. Planeación", f"${mp:,.2f}")
            st.metric("Error Tolerable", f"${et:,.2f}")
            
        if st.button("💾 Guardar Materialidad"):
            conn.execute("DELETE FROM materiality WHERE client_id=?", (client_id,))
            conn.execute("INSERT INTO materiality (client_id, benchmark_type, benchmark_value, percentage, planned_materiality, tolerable_error) VALUES (?,?,?,?,?,?)",
                         (client_id, base, valor, porc, mp, et))
            conn.commit()
            st.success("Cifras de materialidad actualizadas.")
    conn.close()

def vista_papeles(client_id, client_name):
    st.title(f"📂 Cliente: {client_name}")
    if st.button("⬅️ Volver al Listado"):
        del st.session_state.active_id
        st.rerun()
    
    vista_materialidad(client_id)
    
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
    for _, row in steps.iterrows():
        with st.expander(f"📝 {row['step_code']} - {row['description']} ({row['status']})"):
            st.markdown(f"<div class='instruction-box'>{row['instructions']}</div>", unsafe_allow_html=True)
            nota = st.text_area("Hallazgos / Desarrollo", value=row['user_notes'] or "", key=f"t_{row['id']}", height=150)
            
            c1, c2 = st.columns([1, 4])
            with c1:
                estado = st.selectbox("Estado", ["Pendiente", "Cerrado"], index=0 if row['status']=="Pendiente" else 1, key=f"s_{row['id']}")
            
            if st.button("💾 Guardar y Firmar", key=f"b_{row['id']}"):
                conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (nota, estado, row['id']))
                conn.commit()
                registrar_log(row['id'], st.session_state.user_name, f"Cambió estado a {estado} y actualizó notas.")
                st.toast("Papel de trabajo actualizado")
                st.rerun()
                
            # Línea de tiempo NIA 230
            logs = conn.execute("SELECT user_name, action, timestamp FROM audit_logs WHERE step_id=? ORDER BY timestamp DESC", (row['id'],)).fetchall()
            for l_user, l_act, l_time in logs:
                st.markdown(f"<div class='audit-log'>🕒 {l_time} - {l_user}: {l_act}</div>", unsafe_allow_html=True)
    conn.close()

def vista_principal():
    with st.sidebar:
        st.header(f"💼 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Cliente")
        entidad = st.text_input("Nombre Entidad")
        nit = st.text_input("NIT")
        if st.button("Crear Encargo"):
            if entidad and nit:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, entidad, nit))
                cid = cur.lastrowid
                # Pasos básicos NIA
                pasos = [
                    ("Planeación", "P1", "Aceptación (NIA 210)", "Evaluar integridad y capacidad técnica."),
                    ("Planeación", "P2", "Conocimiento del Cliente (NIA 315)", "Identificar riesgos de control interno.")
                ]
                for sec, cod, desc, ins in pasos:
                    conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
                conn.commit()
                st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Dashboard de Auditoría")
        conn = get_db_connection()
        cls = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in cls.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if c2.button("Abrir Archivo", key=f"o_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

# --- ACCESO Y SEGURIDAD ---
def vista_login():
    st.title("⚖️ Acceso a AuditPro")
    t1, t2, t3 = st.tabs(["🔑 Ingresar", "📝 Registrarse", "🆘 Recuperar"])
    
    with t1:
        with st.form("login"):
            em = st.text_input("Correo").strip().lower()
            pw = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Acceder"):
                conn = get_db_connection()
                u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (em, hash_pass(pw))).fetchone()
                conn.close()
                if u:
                    st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                    st.rerun()
                else: st.error("Error: Credenciales no válidas.")

    with t2:
        with st.form("reg"):
            r_fn = st.text_input("Nombre y Apellido")
            r_em = st.text_input("Correo Electrónico").strip().lower()
            r_p1 = st.text_input("Nueva Contraseña", type="password")
            r_p2 = st.text_input("Confirmar Contraseña", type="password")
            if st.form_submit_button("Crear Cuenta"):
                if r_p1 != r_p2: st.error("Las contraseñas no coinciden.")
                elif len(r_p1) < 6: st.warning("La clave debe tener al menos 6 caracteres.")
                else:
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (r_em, r_fn, hash_pass(r_p1)))
                        conn.commit()
                        st.success("Cuenta creada. Ya puedes ingresar en la primera pestaña.")
                    except: st.error("El correo ya está registrado.")
                    conn.close()

    with t3:
        st.subheader("Restablecer Acceso")
        f_em = st.text_input("Correo registrado").strip().lower()
        f_val = st.number_input("Validación: ¿Cuánto es 12 + 13?", step=1)
        f_new = st.text_input("Nueva Contraseña", type="password")
        if st.button("Cambiar Clave"):
            if f_val == 25:
                conn = get_db_connection()
                user = conn.execute("SELECT id FROM users WHERE email=?", (f_em,)).fetchone()
                if user:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(f_new), user[0]))
                    conn.commit()
                    st.success("Contraseña actualizada exitosamente.")
                else: st.error("Correo no encontrado.")
                conn.close()
            else: st.error("Respuesta de seguridad incorrecta.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
