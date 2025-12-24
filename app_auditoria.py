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
        background-color: white; padding: 40px; border-radius: 15px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 500px; margin: auto;
    }
    .main-title { color: #1e3a8a; font-weight: 700; text-align: center; }
    .stButton>button { border-radius: 8px; transition: all 0.3s; }
    .admin-badge {
        background-color: #fee2e2; color: #dc2626;
        padding: 2px 8px; border-radius: 5px; font-size: 12px; font-weight: bold;
    }
    .guia-box {
        background-color: #f0f7ff; border-left: 5px solid #1e3a8a;
        padding: 15px; border-radius: 5px; margin-bottom: 10px;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: #f8fafc;
        border-radius: 10px 10px 0px 0px; padding: 0 20px;
    }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
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
    conn.commit(); conn.close()

create_tables()

# --- HELPERS: CARGA DE PASOS (Actualizado con Administración del Proyecto) ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
        # SECCIÓN 1: Aceptación/continuación
        ("1. Aceptación/continuación", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Realice una evaluación de riesgos del cliente. Considere la integridad de los propietarios y la capacidad del equipo para realizar el trabajo."),
        ("1. Aceptación/continuación", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP", "Evaluar si el compromiso requiere una revisión de control de calidad del trabajo según la complejidad del cliente."),
        ("1. Aceptación/continuación", "4000", "(ISA 200, 220, 300) Cumplimiento de requisitos éticos", "Documentar la independencia de todo el equipo y verificar que no existan conflictos de interés."),
        ("1. Aceptación/continuación", "5000", "(ISA 210, 300) Carta de contratación", "Verificar que la carta de encargo esté firmada por el representante legal y cubra los periodos actuales."),
        ("1. Aceptación/continuación", "6000", "(ISA 510) Contacto con auditores anteriores", "En caso de ser primera auditoría, documentar la comunicación con el auditor predecesor."),
        
        # SECCIÓN 2: Administración del proyecto (NUEVOS PASOS)
        ("2. Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Organizar la logística inicial, asignar roles específicos a los miembros del equipo y programar la reunión de inicio (kick-off)."),
        ("2. Administración del proyecto", "2000", "Discutir y acordar objetivos de desarrollo personal", "Establecer las metas de aprendizaje y desempeño para cada miembro del equipo durante el encargo."),
        ("2. Administración del proyecto", "3000", "(ISA 300) Preparar y monitorear el avance con relación al plan del proyecto", "Actualizar el cronograma de auditoría y verificar que los hitos se estén cumpliendo según lo planeado en la estrategia general.")
    ]
    cursor = conn.cursor()
    cursor.executemany("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)",
                       [(client_id, p[0], p[1], p[2], p[3]) for p in pasos])
    conn.commit()

# --- MÓDULOS DE RENDERIZADO ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Materialidad (NIA 320)")
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            options = ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"]
            idx = options.index(datos[1]) if datos and datos[1] in options else 0
            benchmark = st.selectbox("Benchmark", options, index=idx)
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
    if st.button("💾 Guardar Materialidad", key="save_mat_btn"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Guardado.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name, CAST(step_code AS INTEGER)", conn, params=(client_id,))
    if steps.empty:
        st.info("No hay pasos cargados.")
        if st.button("Generar Pasos Iniciales"):
            cargar_pasos_iniciales(conn, client_id); st.rerun()
    else:
        for seccion in steps['section_name'].unique():
            st.subheader(f"📁 {seccion}")
            for _, row in steps[steps['section_name'] == seccion].iterrows():
                with st.expander(f"Paso {row['step_code']}: {row['description']} | [{row['status']}]"):
                    st.markdown(f'<div class="guia-box"><strong>📖 Guía:</strong> {row["instructions"]}</div>', unsafe_allow_html=True)
                    n_nota = st.text_area("📝 Evidencia:", value=row['user_notes'] or "", key=f"nt_{row['id']}", height=150)
                    c1, c2 = st.columns(2)
                    op = ["Sin Iniciar", "En Proceso", "Terminado"]
                    n_est = c1.selectbox("Estado", op, index=op.index(row['status']) if row['status'] in op else 0, key=f"es_{row['id']}")
                    if c2.button("💾 Guardar", key=f"btn_{row['id']}", use_container_width=True):
                        conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, row['id']))
                        conn.commit(); st.toast("Guardado"); st.rerun()
    conn.close()

# --- VISTA PAPELERA ---
def vista_papelera():
    st.title("🗑️ Papelera de Reciclaje")
    if st.button("⬅️ Volver"): st.session_state.view = "main"; st.rerun()
    conn = get_db_connection()
    deleted = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
    for _, r in deleted.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
            if col2.button("Restaurar", key=f"res_{r['id']}"):
                conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                conn.commit(); st.rerun()
            if col3.button("Eliminar Permanente", key=f"per_{r['id']}"):
                conn.execute("DELETE FROM clients WHERE id=?", (r['id'],))
                conn.commit(); st.rerun()
    conn.close()

# --- VISTA PRINCIPAL ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = "Administrador" in user_role
    if st.session_state.get('view') == "papelera": vista_papelera(); return

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.markdown(f"<span class='admin-badge'>{user_role}</span>", unsafe_allow_html=True)
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Registrar Empresa")
        n_name = st.text_input("Nombre"); n_nit = st.text_input("NIT")
        if st.button("Registrar Cliente"):
            if n_name:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                cargar_pasos_iniciales(conn, cur.lastrowid); conn.commit(); conn.close(); st.rerun()
        if is_admin:
            st.divider()
            if st.button("🗑️ Ver Papelera"): st.session_state.view = "papelera"; st.rerun()
        st.divider()
        orden_tabs = st.radio("Orden de pestañas:", ["Materialidad primero", "Programa primero"])

    if 'active_id' in st.session_state:
        if st.button("⬅️ Dashboard"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        tabs_config = {"📊 Materialidad": modulo_materialidad, "📝 Programa de Trabajo": modulo_programa_trabajo}
        nombres = list(tabs_config.keys())
        if orden_tabs == "Programa primero": nombres.reverse()
        tabs = st.tabs(nombres)
        for i, nombre in enumerate(nombres):
            with tabs[i]: tabs_config[nombre](st.session_state.active_id)
    else:
        st.title("💼 Dashboard AuditPro")
        c1, c2 = st.columns(2)
        c1.link_button("🌐 RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c2.link_button("🏢 RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        st.divider()
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1.5, 0.5])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir Auditoría", key=f"op_{r['id']}", use_container_width=True):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
                if is_admin:
                    with col3.popover("🗑️"):
                        if st.button("Confirmar Borrado", key=f"del_{r['id']}"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],)); conn.commit(); st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.markdown('<div class="login-card"><h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    e = st.text_input("Correo"); p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
        else: st.error("Credenciales incorrectas")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
