import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { 
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
        color: #333; 
        font-weight: bold; 
        font-size: 16px; 
        margin-bottom: 5px; 
    }
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 12px; 
        margin-bottom: 15px; 
        border-radius: 5px;
        font-size: 13px;
        color: #0d47a1;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Sin Iniciar")')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    
    # Asegurar que pasos antiguos tengan estado
    cursor.execute("UPDATE audit_steps SET status = 'Sin Iniciar' WHERE status IS NULL OR status = ''")
    
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULOS DE CONTENIDO ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Determinación de la Materialidad (NIA 320)")
    
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            benchmark = st.selectbox("Benchmark (Base)", ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"],
                index=0 if not datos else ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"].index(datos[1]))
            valor_base = st.number_input("Valor Base Contable ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance (Planeación)", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR (Ajustes)", 0.0, 10.0, datos[7] if datos else 5.0)

        m_gen = valor_base * (p_gen / 100)
        m_perf = m_gen * (p_perf / 100)
        m_ranr = m_gen * (p_ranr / 100)

    res1, res2, res3 = st.columns(3)
    res1.metric("Mat. General", f"$ {m_gen:,.2f}")
    res2.metric("Mat. Desempeño", f"$ {m_perf:,.2f}")
    res3.metric("Límite RANR", f"$ {m_ranr:,.2f}")

    if st.button("💾 Guardar Cálculos de Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Información financiera actualizada.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Ejecución del Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    iconos = {"Sin Iniciar": "🔴", "En Proceso": "🟡", "Terminado": "🟢"}
    colores = {"Sin Iniciar": "#d32f2f", "En Proceso": "#fbc02d", "Terminado": "#388e3c"}

    for seccion in steps['section_name'].unique():
        st.subheader(f"📁 {seccion}")
        pasos_seccion = steps[steps['section_name'] == seccion]
        for _, row in pasos_seccion.iterrows():
            sid, est = row['id'], (row['status'] or "Sin Iniciar")
            color = colores.get(est, "#d32f2f")
            
            st.markdown(f"""<div style="border-left: 10px solid {color}; background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-weight: bold; margin-bottom: 5px;">
                {iconos.get(est)} {row['step_code']} - {row['description']}</div>""", unsafe_allow_html=True)
            
            if row['instructions']:
                st.markdown(f"<div class='instruction-box'><b>💡 Guía del Auditor:</b> {row['instructions']}</div>", unsafe_allow_html=True)
            
            c_nota, c_estado = st.columns([3, 1])
            with c_nota:
                n_nota = st.text_area("Notas y Evidencia", value=row['user_notes'] or "", key=f"nt_{sid}")
            with c_estado:
                n_est = st.selectbox("Estado", ["Sin Iniciar", "En Proceso", "Terminado"], index=["Sin Iniciar", "En Proceso", "Terminado"].index(est), key=f"es_{sid}")
                if st.button("Actualizar Paso", key=f"bt_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit(); st.rerun()
            st.divider()
    conn.close()

# --- VISTA: EXPEDIENTE DEL CLIENTE ---
def vista_expediente(client_id, client_name):
    c1, c2 = st.columns([5, 1])
    c1.title(f"📂 {client_name}")
    if c2.button("⬅️ Cerrar Expediente"):
        if 'active_id' in st.session_state: del st.session_state.active_id
        st.rerun()

    if 'current_module' not in st.session_state: st.session_state.current_module = "Materialidad"

    # NAVEGACIÓN PRINCIPAL
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    if m1.button("📊 Materialidad", use_container_width=True): st.session_state.current_module = "Materialidad"
    if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.current_module = "Programa"
    if m3.button("📥 Exportar Datos", use_container_width=True): st.session_state.current_module = "Exportar"
    
    # ENLACES EXTERNOS EN EL EXPEDIENTE
    st.markdown(" **🔍 Herramientas de Consulta Legal:**")
    col_links = st.columns([1, 1, 4])
    with col_links[0]:
        st.link_button("🌐 Estado RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
    with col_links[1]:
        st.link_button("🏢 Búsqueda RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
    
    st.markdown("---")

    if st.session_state.current_module == "Materialidad":
        modulo_materialidad(client_id)
    elif st.session_state.current_module == "Programa":
        modulo_programa_trabajo(client_id)

# --- VISTA PRINCIPAL (DASHBOARD) ---
def vista_principal():
    with st.sidebar:
        st.write(f"Sesión activa: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Registrar Empresa")
        name = st.text_input("Nombre o Razón Social"); nit = st.text_input("NIT")
        if st.button("Crear Auditoría"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, name, nit))
            cid = cur.lastrowid
            pasos = [
                ("100 Planeación", "101", "Aceptación del Cliente", "Validar antecedentes y vinculación económica."),
                ("200 Ejecución", "201", "Arqueos", "Realizar verificación de cajas y fondos fijos."),
            ]
            for sec, cod, desc, ins in pasos:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions, status) VALUES (?,?,?,?,?,?)", (cid, sec, cod, desc, ins, "Sin Iniciar"))
            conn.commit(); conn.close(); st.rerun()

    # --- CONTENIDO DEL DASHBOARD ---
    st.title("💼 Dashboard de Auditoría")
    
    # ENLACES EXTERNOS EN EL DASHBOARD (PARA CONSULTA RÁPIDA)
    st.markdown(" **🔍 Consultas Rápidas:**")
    col_dash_links = st.columns([1, 1, 4])
    with col_dash_links[0]:
        st.link_button("🌐 Estado RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
    with col_dash_links[1]:
        st.link_button("🏢 Búsqueda RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
    
    st.divider()

    if 'active_id' in st.session_state:
        vista_expediente(st.session_state.active_id, st.session_state.active_name)
    else:
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        if clients.empty:
            st.info("No hay auditorías registradas. Utilice el panel lateral para crear una.")
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if c2.button("Abrir Expediente", key=f"op_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
        conn.close()

# --- ACCESO Y SEGURIDAD ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.title("⚖️ AuditPro")
    e, p = st.text_input("Correo electrónico"), st.text_input("Contraseña", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
        else: st.error("Acceso denegado")
    if c2.button("Crear Cuenta", use_container_width=True):
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, "Auditor Senior", hash_pass(p)))
            conn.commit(); st.success("Cuenta creada exitosamente.")
        except: st.error("El usuario ya existe.")
        conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
