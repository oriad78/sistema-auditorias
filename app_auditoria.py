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

# --- MÓDULO: PAPELERA DE RECICLAJE (SOLO ADMIN) ---
def vista_papelera():
    st.title("♻️ Centro de Recuperación")
    if st.button("⬅️ Volver al Dashboard"):
        st.session_state.view = "dashboard"; st.rerun()
    
    conn = get_db_connection()
    tab1, tab2 = st.tabs(["🏢 Empresas Borradas", "📄 Pasos de Auditoría"])
    
    with tab1:
        deleted_clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
        if deleted_clients.empty: st.info("No hay empresas para recuperar.")
        for _, r in deleted_clients.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1.5])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Restaurar ✅", key=f"res_cli_{r['id']}"):
                    conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                    conn.commit(); st.rerun()
                if c3.button("Eliminar Permanente", key=f"perm_cli_{r['id']}"):
                    conn.execute("DELETE FROM clients WHERE id=?", (r['id'],))
                    conn.commit(); st.rerun()
    conn.close()

# --- VISTAS PRINCIPALES ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = user_role == "Administrador"
    
    if st.session_state.get('view') == "papelera":
        vista_papelera()
        return

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.markdown(f"<span class='admin-badge'>{user_role}</span>", unsafe_allow_html=True)
        if st.button("Cerrar Sesión", type="primary", use_container_width=True): 
            st.session_state.clear(); st.rerun()
        st.divider()
        if is_admin:
            if st.button("♻️ GESTIONAR PAPELERA", use_container_width=True):
                st.session_state.view = "papelera"; st.rerun()
        st.divider()
        st.subheader("Nueva Empresa")
        n_name = st.text_input("Nombre")
        n_nit = st.text_input("NIT")
        if st.button("Registrar Auditoría", use_container_width=True):
            if n_name and n_nit:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                cid = cur.lastrowid
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description) VALUES (?,?,?,?)", (cid, "General", "101", "Planificación Inicial"))
                conn.commit(); conn.close(); st.rerun()

    st.title("💼 Dashboard AuditPro")
    c_l1, c_l2 = st.columns(2)
    c_l1.link_button("🌐 DIAN RUT", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
    c_l2.link_button("🏢 RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
    st.divider()
    
    conn = get_db_connection()
    clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
    for _, r in clients.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
            col2.button("Abrir", key=f"op_{r['id']}", use_container_width=True)
            with col3:
                if is_admin:
                    with st.popover("🗑️", use_container_width=True):
                        if st.button("Confirmar Borrado", key=f"soft_d_{r['id']}", type="primary"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                            conn.commit(); st.rerun()
                else:
                    st.button("🔒", key=f"lock_{r['id']}", help="Solo administradores pueden eliminar", use_container_width=True)
    conn.close()

# --- LOGIN Y REGISTRO ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    
    tab_in, tab_reg = st.tabs(["🔐 Ingresar", "📝 Registrarse"])
    
    with tab_in:
        e = st.text_input("Correo electrónico", key="l_email")
        p = st.text_input("Contraseña", type="password", key="l_pass")
        if st.button("Entrar", use_container_width=True):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u:
                st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]
                st.rerun()
            else: st.error("Credenciales incorrectas.")

    with tab_reg:
        n_name = st.text_input("Nombre Completo")
        n_email = st.text_input("Correo electrónico ")
        
        # DIFERENCIACIÓN DE ROL EN REGISTRO
        n_role = st.selectbox("Tipo de Usuario", ["Miembro del Equipo", "Administrador"])
        
        p1 = st.text_input("Contraseña ", type="password")
        p2 = st.text_input("Confirmar Contraseña", type="password")
        
        if st.button("Crear Cuenta", use_container_width=True):
            if p1 != p2: st.error("Las contraseñas no coinciden.")
            elif len(p1) < 6: st.error("Contraseña demasiado corta.")
            elif n_email and p1:
                conn = get_db_connection()
                # Seguridad: Si es el primer usuario, forzar Administrador
                count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
                final_role = "Administrador" if count == 0 else n_role
                
                try:
                    conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (n_email, n_name, hash_pass(p1), final_role))
                    conn.commit(); st.success(f"¡Cuenta como {final_role} creada!"); st.balloons()
                except: st.error("El correo ya existe.")
                finally: conn.close()
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
