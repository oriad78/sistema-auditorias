import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stButton>button { border-radius: 5px; }
    .main-header { font-size: 24px; font-weight: bold; color: #1e3a8a; }
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

# --- MÓDULO: PAPELERA DE RECICLAJE ---
def vista_papelera():
    st.subheader("♻️ Centro de Recuperación")
    if st.button("⬅️ Volver al Dashboard", key="back_to_dash"):
        st.session_state.view = "dashboard"; st.rerun()
    
    conn = get_db_connection()
    t1, t2 = st.tabs(["🏢 Empresas", "📄 Pasos"])
    
    with t1:
        deleted_clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
        for _, r in deleted_clients.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{r['client_name']}**")
                if c2.button("Restaurar", key=f"res_c_{r['id']}"):
                    conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (r['id'],))
                    conn.commit(); st.rerun()
                if c3.button("Eliminar", key=f"del_p_c_{r['id']}"):
                    conn.execute("DELETE FROM clients WHERE id=?", (r['id'],))
                    conn.commit(); st.rerun()

    with t2:
        deleted_steps = pd.read_sql_query("SELECT s.*, c.client_name FROM audit_steps s JOIN clients c ON s.client_id = c.id WHERE s.is_deleted=1", conn)
        for _, s in deleted_steps.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{s['step_code']}** ({s['client_name']})")
                if c2.button("Restaurar", key=f"res_s_{s['id']}"):
                    conn.execute("UPDATE audit_steps SET is_deleted=0 WHERE id=?", (s['id'],))
                    conn.commit(); st.rerun()
                if c3.button("Eliminar", key=f"del_p_s_{s['id']}"):
                    conn.execute("DELETE FROM audit_steps WHERE id=?", (s['id'],))
                    conn.commit(); st.rerun()
    conn.close()

# --- VISTAS PRINCIPALES ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    
    if st.session_state.get('view') == "papelera":
        vista_papelera()
        return

    with st.sidebar:
        st.header("AuditPro Menu")
        st.write(f"Usuario: **{st.session_state.user_name}**")
        st.caption(f"Rol: {user_role}")
        
        if st.button("♻️ GESTIONAR PAPELERA", use_container_width=True):
            st.session_state.view = "papelera"; st.rerun()
        
        st.divider()
        if st.button("Cerrar Sesión", type="primary"): st.session_state.clear(); st.rerun()

    if 'active_id' in st.session_state:
        # Aquí iría el modulo_materialidad y modulo_programa_trabajo (idénticos a los anteriores)
        if st.button("⬅️ Volver"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        st.info("Módulos de Auditoría cargados.")
    else:
        st.title("💼 Dashboard AuditPro")
        
        # Enlaces rápidos
        c1, c2 = st.columns(2)
        c1.link_button("🌐 DIAN RUT", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c2.link_button("🏢 RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        
        st.divider()
        
        # Creación de empresa para que siempre tengas acceso
        with st.expander("➕ Registrar Nueva Auditoría"):
            n_name = st.text_input("Nombre de la Empresa")
            n_nit = st.text_input("NIT")
            if st.button("Crear"):
                conn = get_db_connection()
                conn.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                conn.commit(); conn.close(); st.rerun()

        st.divider()
        
        # Lista de clientes
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir", key=f"open_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
                
                # BOTÓN DE BORRADO: Ahora forzamos que sea funcional
                with col3.popover("🗑️"):
                    st.warning("¿Mover a papelera?")
                    if st.button("Borrar", key=f"soft_d_{r['id']}", type="primary"):
                        conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                        conn.commit(); st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.title("⚖️ Acceso AuditPro")
    e, p = st.text_input("Correo"), st.text_input("Contraseña", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u:
            st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]
            st.rerun()
        else: st.error("Datos incorrectos")
    
    if c2.button("Crear Cuenta", use_container_width=True):
        conn = get_db_connection()
        # El primero que se registre siempre será Admin
        count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        role = "Admin" if count == 0 else "Miembro"
        try:
            conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (e, "Usuario Nuevo", hash_pass(p), role))
            conn.commit(); st.success(f"Cuenta {role} creada. Ya puedes ingresar.")
        except: st.error("El correo ya existe")
        finally: conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
