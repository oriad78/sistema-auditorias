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
    .guia-box {
        background-color: #f0f7ff;
        border-left: 5px solid #1e3a8a;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
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

# --- HELPER: CARGA DE PASOS INICIALES (BASADO EN TU IMAGEN) ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
        ("Aceptación/continuación", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Realice una evaluación de riesgos del cliente. Considere la integridad de los propietarios y la capacidad del equipo para realizar el trabajo."),
        ("Aceptación/continuación", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP", "Evaluar si el compromiso requiere una revisión de control de calidad del trabajo según la complejidad del cliente."),
        ("Aceptación/continuación", "4000", "(ISA 200, 220, 300) Cumplimiento de requisitos éticos", "Documentar la independencia de todo el equipo y verificar que no existan conflictos de interés."),
        ("Aceptación/continuación", "5000", "(ISA 210, 300) Carta de contratación", "Verificar que la carta de encargo esté firmada por el representante legal y cubra los periodos actuales."),
        ("Aceptación/continuación", "6000", "(ISA 510) Contacto con auditores anteriores", "En caso de ser primera auditoría, documentar la comunicación con el auditor predecesor.")
    ]
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)",
        [(client_id, p[0], p[1], p[2], p[3]) for p in pasos]
    )
    conn.commit()

# --- MÓDULOS DE AUDITORÍA ---
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
    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", 
                     (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Guardado.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name, CAST(step_code AS INTEGER)", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]
    
    if steps.empty:
        st.info("No hay pasos cargados.")
        if st.button("Generar Pasos Iniciales"):
            cargar_pasos_iniciales(conn, client_id); st.rerun()
    
    for seccion in steps['section_name'].unique():
        st.subheader(f"📁 {seccion}")
        for _, row in steps[steps['section_name'] == seccion].iterrows():
            sid = row['id']
            # Título del paso para el Expander (esto permite ocultar/mostrar)
            label = f"Paso {row['step_code']}: {row['description']} | [{row['status']}]"
            
            with st.expander(label):
                # 1. GUÍA (INSTRUCCIONES)
                st.markdown(f"""<div class="guia-box"><strong>📖 Guía para el auditor:</strong><br>{row['instructions'] or 'Siga los lineamientos de la NIA correspondiente para este paso.'}</div>""", unsafe_allow_html=True)
                
                # 2. ESPACIO PARA DESARROLLAR EL TRABAJO
                n_nota = st.text_area("📝 Trabajo realizado / Evidencia:", value=row['user_notes'] or "", key=f"nt_{sid}", height=200)
                
                c_est, c_save = st.columns([1, 1])
                with c_est:
                    estado_actual = row['status'] if row['status'] in opciones_estado else "Sin Iniciar"
                    n_est = st.selectbox("Estado del paso", opciones_estado, index=opciones_estado.index(estado_actual), key=f"es_{sid}")
                
                with c_save:
                    st.write(" ") # Espaciador
                    if st.button("💾 Guardar Avance", key=f"btn_{sid}", use_container_width=True):
                        conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                        conn.commit(); st.toast("Progreso guardado"); st.rerun()
    conn.close()

# --- VISTAS DASHBOARD (SIN CAMBIOS ESTRUCTURALES) ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    if st.session_state.get('view') == "papelera":
        vista_papelera(); return

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Registrar Empresa")
        n_name = st.text_input("Nombre"); n_nit = st.text_input("NIT")
        if st.button("Registrar Cliente"):
            if n_name:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                cargar_pasos_iniciales(conn, cur.lastrowid)
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver al Listado"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        m1, m2 = st.columns(2)
        if m1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.mod = "Prog"
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Dashboard AuditPro")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir", key=f"op_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']
                    st.session_state.mod = "Mat"; st.rerun()
        conn.close()

# --- LOGIN (SIN CAMBIOS) ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    e = st.text_input("Correo"); p = st.text_input("Pass", type="password")
    if st.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
