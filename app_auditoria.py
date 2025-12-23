import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS PROFESIONALES (CSS) ---
st.markdown("""
    <style>
    .login-card {
        background-color: white;
        padding: 40px;
        border-radius: 15px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        max-width: 500px;
        margin: auto;
    }
    .main-title { color: #1e3a8a; font-weight: 700; text-align: center; }
    .stButton>button { border-radius: 8px; transition: all 0.3s; }
    .admin-badge {
        background-color: #fee2e2;
        color: #dc2626;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT, role TEXT DEFAULT "Miembro")')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, is_deleted INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Sin Iniciar", is_deleted INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULOS DE AUDITORÍA ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Materialidad (NIA 320)")
    
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            benchmark = st.selectbox("Benchmark", ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"],
                index=0 if not datos else ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"].index(datos[1]))
            valor_base = st.number_input("Valor Base ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR", 0.0, 10.0, datos[7] if datos else 5.0)
        
        m_gen = valor_base * (p_gen / 100)
        m_perf = m_gen * (p_perf / 100)
        m_ranr = m_gen * (p_ranr / 100)
    
    st.columns(3)[0].metric("Mat. General", f"$ {m_gen:,.2f}")
    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Guardado.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name, step_code", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]
    
    if steps.empty:
        st.info("No hay pasos cargados para esta auditoría.")
        if st.button("Generar Paso Inicial"):
            conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description) VALUES (?,?,?,?)", (client_id, "General", "101", "Planificación Inicial"))
            conn.commit(); st.rerun()
    
    for seccion in steps['section_name'].unique():
        st.subheader(f"📁 {seccion}")
        for _, row in steps[steps['section_name'] == seccion].iterrows():
            sid = row['id']
            estado_actual = row['status'] if row['status'] in opciones_estado else "Sin Iniciar"
            with st.expander(f"{row['step_code']} - {row['description']} ({estado_actual})"):
                n_nota = st.text_area("Evidencia", value=row['user_notes'] or "", key=f"nt_{sid}")
                n_est = st.selectbox("Estado", opciones_estado, index=opciones_estado.index(estado_actual), key=f"es_{sid}")
                if st.button("Actualizar Paso", key=f"upd_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit(); st.rerun()
    conn.close()

# --- VISTAS PRINCIPALES ---
def vista_papelera():
    st.title("♻️ Papelera")
    if st.button("⬅️ Dashboard"): st.session_state.view = "dashboard"; st.rerun()
    conn = get_db_connection()
    deleted = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
    for _, r in deleted.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.write(f"🏢 **{r['client_name']}**")
            if c2.button("Restaurar", key=f"res_{r['id']}"):
                conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                conn.commit(); st.rerun()
    conn.close()

def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = "Administrador" in user_role
    
    if st.session_state.get('view') == "papelera":
        vista_papelera(); return

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.markdown(f"<span class='admin-badge'>{user_role}</span>", unsafe_allow_html=True)
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        if is_admin:
            if st.button("♻️ PAPELERA"): st.session_state.view = "papelera"; st.rerun()
        st.subheader("Nueva Empresa")
        n_name = st.text_input("Nombre"); n_nit = st.text_input("NIT")
        if st.button("Registrar"):
            if n_name:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                cid = cur.lastrowid
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description) VALUES (?,?,?,?)", (cid, "General", "101", "Planificación Inicial"))
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver al Dashboard"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        m1, m2 = st.columns(2)
        if m1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if m2.button("📝 Programa", use_container_width=True): st.session_state.mod = "Prog"
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Dashboard AuditPro")
        c1, c2 = st.columns(2)
        c1.link_button("🌐 DIAN RUT", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c2.link_button("🏢 RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        st.divider()
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir", key=f"op_{r['id']}", use_container_width=True):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']
                    st.session_state.mod = "Mat"; st.rerun()
                if is_admin:
                    with col3.popover("🗑️"):
                        if st.button("Borrar", key=f"del_{r['id']}"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                            conn.commit(); st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["🔐 Entrar", "📝 Registro"])
    with t1:
        e = st.text_input("Correo", key="l_e"); p = st.text_input("Pass", type="password", key="l_p")
        if st.button("Ingresar", use_container_width=True):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
            else: st.error("Error")
    with t2:
        n = st.text_input("Nombre"); em = st.text_input("Correo "); r = st.selectbox("Rol", ["Miembro del Equipo", "Administrador"])
        p1 = st.text_input("Pass ", type="password"); p2 = st.text_input("Confirmar", type="password")
        if st.button("Crear", use_container_width=True):
            if p1 == p2 and em:
                conn = get_db_connection()
                count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
                role = "Administrador" if count == 0 else r
                try:
                    conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (em, n, hash_pass(p1), role))
                    conn.commit(); st.success("Creado"); st.balloons()
                except: st.error("Existe")
                finally: conn.close()
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
