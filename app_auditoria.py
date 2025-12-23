import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 12px; 
        margin-bottom: 15px; 
        border-radius: 5px;
        font-size: 13px;
        color: #0d47a1;
    }
    .stButton>button { border-radius: 5px; }
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
    
    # Asegurar columnas (Migración rápida)
    for table, col in [("clients", "is_deleted"), ("audit_steps", "is_deleted")]:
        try: cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 0')
        except: pass
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULO: PAPELERA DE RECICLAJE (VISTA COMPLETA) ---
def vista_papelera():
    st.title("♻️ Centro de Recuperación (Papelera)")
    if st.button("⬅️ Volver al Dashboard"):
        st.session_state.view = "dashboard"; st.rerun()
    
    conn = get_db_connection()
    tab1, tab2 = st.tabs(["🏢 Empresas Borradas", "📄 Pasos de Auditoría"])
    
    with tab1:
        deleted_clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
        if deleted_clients.empty:
            st.info("No hay empresas en la papelera.")
        for _, r in deleted_clients.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Restaurar ✅", key=f"res_cli_{r['id']}", use_container_width=True):
                    conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                    conn.commit(); st.toast("Empresa restaurada"); st.rerun()
                if c3.button("Eliminar 💀", key=f"perm_cli_{r['id']}", use_container_width=True):
                    conn.execute("DELETE FROM clients WHERE id=?", (r['id'],))
                    conn.execute("DELETE FROM audit_steps WHERE client_id=?", (r['id'],))
                    conn.commit(); st.rerun()

    with tab2:
        deleted_steps = pd.read_sql_query("SELECT s.*, c.client_name FROM audit_steps s JOIN clients c ON s.client_id = c.id WHERE s.is_deleted=1", conn)
        if deleted_steps.empty:
            st.info("No hay pasos individuales en la papelera.")
        for _, s in deleted_steps.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{s['step_code']}** - {s['description']} (Cliente: {s['client_name']})")
                if c2.button("Restaurar ✅", key=f"res_step_{s['id']}", use_container_width=True):
                    conn.execute("UPDATE audit_steps SET is_deleted=0 WHERE id=?", (s['id'],))
                    conn.commit(); st.toast("Paso restaurado"); st.rerun()
                if c3.button("Eliminar 💀", key=f"perm_step_{s['id']}", use_container_width=True):
                    conn.execute("DELETE FROM audit_steps WHERE id=?", (s['id'],))
                    conn.commit(); st.rerun()

    if not deleted_clients.empty or not deleted_steps.empty:
        st.divider()
        if st.button("⚠️ VACIAR TODO permanentemente", type="primary", use_container_width=True):
            conn.execute("DELETE FROM audit_steps WHERE is_deleted=1")
            conn.execute("DELETE FROM clients WHERE is_deleted=1")
            conn.commit(); st.rerun()
    conn.close()

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
        m_gen = valor_base * (p_gen / 100); m_perf = m_gen * (p_perf / 100); m_ranr = m_gen * (p_ranr / 100)
    
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
    for seccion in steps['section_name'].unique():
        st.subheader(f"📁 {seccion}")
        for _, row in steps[steps['section_name'] == seccion].iterrows():
            sid = row['id']
            with st.expander(f"{row['step_code']} - {row['description']} ({row['status']})"):
                n_nota = st.text_area("Evidencia", value=row['user_notes'] or "", key=f"nt_{sid}")
                n_est = st.selectbox("Estado", opciones_estado, index=opciones_estado.index(row['status'] if row['status'] in opciones_estado else "Sin Iniciar"), key=f"es_{sid}")
                c_up, c_de = st.columns(2)
                if c_up.button("Actualizar", key=f"upd_{sid}", use_container_width=True):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit(); st.rerun()
                with c_de.popover("🗑️ Borrar", use_container_width=True):
                    if st.button("Confirmar", key=f"del_{sid}", type="primary"):
                        conn.execute("UPDATE audit_steps SET is_deleted=1 WHERE id=?", (sid,))
                        conn.commit(); st.rerun()
    conn.close()

# --- VISTAS PRINCIPALES ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = user_role == "Admin"
    
    # Navegación a la papelera
    if st.session_state.get('view') == "papelera":
        vista_papelera()
        return

    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_name}** ({user_role})")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        if is_admin:
            if st.button("♻️ Abrir Papelera", use_container_width=True):
                st.session_state.view = "papelera"; st.rerun()
            st.divider()
        st.subheader("Nueva Empresa")
        name = st.text_input("Nombre"); nit = st.text_input("NIT")
        if st.button("Registrar Auditoría"):
            if name and nit:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, name, nit))
                cid = cur.lastrowid
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, status) VALUES (?,?,?,?,?)", (cid, "General", "101", "Planificación Inicial", "Sin Iniciar"))
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        # Vista de Expediente (Materialidad/Programa)
        if st.button("⬅️ Volver al Dashboard"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        m1, m2 = st.columns(2)
        if m1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if m2.button("📝 Programa", use_container_width=True): st.session_state.mod = "Prog"
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        # Dashboard Principal
        st.title("💼 Dashboard AuditPro")
        
        # Fila de botones de acción rápida
        c_p1, c_p2, c_p3 = st.columns([1,1,1])
        c_p1.link_button("🌐 DIAN RUT", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c_p2.link_button("🏢 RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        if is_admin:
            if c_p3.button("♻️ VER PAPELERA", type="secondary", use_container_width=True):
                st.session_state.view = "papelera"; st.rerun()
        
        st.divider()
        search = st.text_input("🔍 Buscar cliente...")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0 AND (client_name LIKE ? OR client_nit LIKE ?)", conn, params=(f"%{search}%", f"%{search}%"))
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if c2.button("Abrir", key=f"op_{r['id']}", use_container_width=True):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
                with c3:
                    if is_admin:
                        with st.popover("🗑️", use_container_width=True):
                            if st.button("Mover a Papelera", key=f"soft_del_{r['id']}", type="primary"):
                                conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                                conn.commit(); st.toast("Movido a papelera"); st.rerun()
                    else: st.write("🔒")
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.title("⚖️ Acceso AuditPro")
    e, p = st.text_input("Correo"), st.text_input("Pass", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
        else: st.error("Error")
    if c2.button("Registrar", use_container_width=True):
        if e and p:
            conn = get_db_connection()
            count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
            role = "Admin" if count == 0 else "Miembro"
            try:
                conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (e, "Auditor Senior", hash_pass(p), role))
                conn.commit(); st.success(f"Creado como {role}")
            except: st.error("Existe")
            finally: conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
