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
    .nav-button-container { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    
    # Tabla Materialidad (Aseguramos columnas correctas)
    cursor.execute("DROP TABLE IF EXISTS materiality")
    cursor.execute('''CREATE TABLE materiality 
                     (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, 
                      p_general REAL, mat_general REAL, p_performance REAL, 
                      mat_performance REAL, p_ranr REAL, mat_ranr REAL)''')
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULO: MATERIALIDAD ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Determinación de la Materialidad (NIA 320)")
    
    
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
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0 # Simplificado para el ejemplo
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR", 0.0, 10.0, datos[7] if datos else 5.0)

        m_gen = valor_base * (p_gen / 100)
        m_perf = m_gen * (p_perf / 100)
        m_ranr = m_gen * (p_ranr / 100)

    res1, res2, res3 = st.columns(3)
    res1.metric("General", f"$ {m_gen:,.2f}")
    res2.metric("Desempeño", f"$ {m_perf:,.2f}")
    res3.metric("RANR", f"$ {m_ranr:,.2f}")

    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", 
                     (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit()
        conn.close()
        st.success("Guardado")

# --- MÓDULO: PROGRAMA DE TRABAJO ---
def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name", conn, params=(client_id,))
    for seccion in steps['section_name'].unique():
        with st.expander(f"📁 {seccion}", expanded=True):
            for _, row in steps[steps['section_name'] == seccion].iterrows():
                st.markdown(f"**{row['step_code']}** - {row['description']}")
                notas = st.text_area("Notas", value=row['user_notes'] or "", key=f"n_{row['id']}")
                if st.button("Guardar", key=f"b_{row['id']}"):
                    conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, row['id']))
                    conn.commit()
                    st.toast("Guardado")
    conn.close()

# --- VISTA: EXPEDIENTE (CON NAVEGADOR DE BOTONES) ---
def vista_expediente(client_id, client_name):
    col_t, col_v = st.columns([4, 1])
    col_t.title(f"📂 {client_name}")
    if col_v.button("⬅️ Salir"):
        del st.session_state.active_id
        st.rerun()

    # INICIALIZAR EL MÓDULO ACTIVO SI NO EXISTE
    if 'current_module' not in st.session_state:
        st.session_state.current_module = "Materialidad"

    # BARRA DE NAVEGACIÓN (BOTONES)
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    
    if c1.button("📊 Materialidad", use_container_width=True):
        st.session_state.current_module = "Materialidad"
    if c2.button("📝 Prog. Trabajo", use_container_width=True):
        st.session_state.current_module = "Programa"
    if c3.button("➕ Otros Campos", use_container_width=True):
        st.session_state.current_module = "Otros"
    if c4.button("📥 Exportar", use_container_width=True):
        st.session_state.current_module = "Exportar"
    st.markdown("---")

    # LÓGICA DE CAMBIO DE PÁGINA
    if st.session_state.current_module == "Materialidad":
        modulo_materialidad(client_id)
    elif st.session_state.current_module == "Programa":
        modulo_programa_trabajo(client_id)
    elif st.session_state.current_module == "Otros":
        st.info("Aquí podrás agregar futuros campos y formularios.")
    elif st.session_state.current_module == "Exportar":
        st.write("Configuración de exportación a PDF/Excel.")

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Usuario: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.subheader("Nuevo Encargo")
        cn = st.text_input("Empresa")
        ct = st.text_input("NIT")
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, cn, ct))
            cid = cur.lastrowid
            conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description) VALUES (?,?,?,?)", (cid, "100-Planeación", "1010", "Aceptación"))
            conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        vista_expediente(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Auditorías")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Abrir", key=f"ab_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.title("⚖️ AuditPro")
    e, p = st.text_input("Correo"), st.text_input("Pass", type="password")
    if st.button("Entrar"):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
        else: st.error("Error")
    if st.button("Registrar (Demo)"):
        conn = get_db_connection()
        conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, "Usuario Demo", hash_pass(p)))
        conn.commit(); conn.close(); st.success("Registrado")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
