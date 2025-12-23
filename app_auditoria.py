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
    .admin-badge {
        background-color: #ff4b4b;
        color: white;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 10px;
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
    
    # Migraciones de seguridad
    try: cursor.execute('ALTER TABLE clients ADD COLUMN is_deleted INTEGER DEFAULT 0')
    except: pass
    try: cursor.execute('ALTER TABLE audit_steps ADD COLUMN is_deleted INTEGER DEFAULT 0')
    except: pass
    try: cursor.execute('ALTER TABLE users ADD COLUMN role TEXT DEFAULT "Miembro"')
    except: pass
    
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULO: PAPELERA DE RECICLAJE (ADMIN) ---
def modulo_papelera():
    st.subheader("♻️ Papelera de Reciclaje")
    conn = get_db_connection()
    
    # 1. Auditorías Borradas
    st.write("**Auditorías en espera de eliminación:**")
    deleted_clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
    if deleted_clients.empty:
        st.caption("No hay auditorías para eliminar.")
    for _, r in deleted_clients.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1.5])
            c1.write(f"🏢 {r['client_name']}")
            if c2.button("Restaurar", key=f"rest_cli_{r['id']}"):
                conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                conn.commit(); st.rerun()
            if c3.button("Eliminar Permanente", key=f"perm_cli_{r['id']}"):
                conn.execute("DELETE FROM clients WHERE id=?", (r['id'],))
                conn.execute("DELETE FROM audit_steps WHERE client_id=?", (r['id'],))
                conn.execute("DELETE FROM materiality WHERE client_id=?", (r['id'],))
                conn.commit(); st.rerun()

    st.divider()
    
    # 2. Pasos Borrados
    st.write("**Pasos individuales eliminados:**")
    deleted_steps = pd.read_sql_query("SELECT s.*, c.client_name FROM audit_steps s JOIN clients c ON s.client_id = c.id WHERE s.is_deleted=1", conn)
    if deleted_steps.empty:
        st.caption("No hay pasos para eliminar.")
    for _, s in deleted_steps.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1.5])
            c1.write(f"📄 {s['step_code']} ({s['client_name']})")
            if c2.button("Restaurar", key=f"rest_step_{s['id']}"):
                conn.execute("UPDATE audit_steps SET is_deleted=0 WHERE id=?", (s['id'],))
                conn.commit(); st.rerun()
            if c3.button("Eliminar Permanente", key=f"perm_step_{s['id']}"):
                conn.execute("DELETE FROM audit_steps WHERE id=?", (s['id'],))
                conn.commit(); st.rerun()

    if not deleted_clients.empty or not deleted_steps.empty:
        st.divider()
        if st.button("⚠️ VACIAR TODA LA PAPELERA", use_container_width=True, type="primary"):
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
        pasos_seccion = steps[steps['section_name'] == seccion]
        for _, row in pasos_seccion.iterrows():
            sid = row['id']
            with st.expander(f"{row['step_code']} - {row['description']}"):
                n_nota = st.text_area("Evidencia", value=row['user_notes'] or "", key=f"nt_{sid}")
                n_est = st.selectbox("Estado", opciones_estado, index=opciones_estado.index(row['status'] or "Sin Iniciar"), key=f"es_{sid}")
                if st.button("Actualizar", key=f"upd_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit(); st.rerun()
                with st.popover("🗑️ Borrar"):
                    if st.button("Mover a papelera", key=f"del_{sid}"):
                        conn.execute("UPDATE audit_steps SET is_deleted=1 WHERE id=?", (sid,))
                        conn.commit(); st.rerun()
    conn.close()

# --- VISTAS PRINCIPALES ---
def vista_expediente(client_id, client_name):
    if st.button("⬅️ Volver al Dashboard"):
        if 'active_id' in st.session_state: del st.session_state.active_id
        st.rerun()
    st.title(f"📂 {client_name}")
    m1, m2 = st.columns(2)
    if m1.button("📊 Materialidad", use_container_width=True): st.session_state.current_module = "Materialidad"
    if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.current_module = "Programa"
    if st.session_state.get('current_module') == "Programa": modulo_programa_trabajo(client_id)
    else: modulo_materialidad(client_id)

def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = user_role == "Admin"
    
    with st.sidebar:
        st.write(f"Usuario: **{st.session_state.user_name}** ({user_role})")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        if is_admin:
            with st.expander("♻️ Papelera de Reciclaje"): modulo_papelera()
            st.divider()
        st.subheader("Nueva Empresa")
        name = st.text_input("Nombre"); nit = st.text_input("NIT")
        if st.button("Registrar"):
            if name and nit:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, name, nit))
                cid = cur.lastrowid
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description) VALUES (?,?,?,?)", (cid, "General", "101", "Planificación Inicial"))
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        vista_expediente(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Dashboard AuditPro")
        
        # --- BLOQUE DE ENLACES REINTEGRADO ---
        st.markdown("**🔍 Consultas Externas:**")
        col_dash_links = st.columns(2)
        col_dash_links[0].link_button("🌐 Estado RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        col_dash_links[1].link_button("🏢 Búsqueda RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        
        st.divider()
        search = st.text_input("🔍 Buscar cliente por Nombre o NIT...")
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
                        with st.popover("🗑️"):
                            if st.button("Mover a papelera", key=f"soft_del_{r['id']}"):
                                conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                                conn.commit(); st.rerun()
                    else: st.write("🔒")
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.title("⚖️ Acceso AuditPro")
    e, p = st.text_input("Correo electrónico"), st.text_input("Contraseña", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Ingresar", use_container_width=True):
        if e and p:
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u: 
                st.session_state.user_id = u[0]
                st.session_state.user_name = u[1]
                st.session_state.user_role = u[2] if u[2] else "Miembro"
                st.rerun()
            else: st.error("Credenciales incorrectas")
    if c2.button("Registrar", use_container_width=True):
        if e and p:
            conn = get_db_connection()
            count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
            role = "Admin" if count == 0 else "Miembro"
            try:
                conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (e, "Auditor Senior", hash_pass(p), role))
                conn.commit(); st.success(f"Creado como {role}. Ya puede ingresar.")
            except: st.error("El usuario ya existe.")
            finally: conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
