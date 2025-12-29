import hashlib
import sqlite3
import pandas as pd
import streamlit as st
import io
import re

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
    .trash-section {
        background-color: #f8fafc;
        padding: 20px;
        border-radius: 10px;
        border: 1px dashed #cbd5e1;
        margin-top: 40px;
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

# --- SEGURIDAD ---
def hash_pass(p): 
    return hashlib.sha256(p.encode()).hexdigest()

def validar_password(p, p_confirm):
    if not p or not p_confirm:
        return False, "Debe completar ambos campos de contraseña."
    if p != p_confirm:
        return False, "Las contraseñas NO coinciden."
    if len(p) < 8 or not re.search("[a-z]", p) or not re.search("[0-9]", p):
        return False, "La contraseña debe tener al menos 8 caracteres (letras y números)."
    return True, ""

# --- PASOS INICIALES ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
        ("Aceptación/continuación", "1000", "(ISA 220, 300) Evaluar aceptación", "Evaluar riesgos."),
        ("Aceptación/continuación", "2000", "(ISA 220) Designar QRP", "Complejidad."),
        ("Aceptación/continuación", "4000", "(ISA 200) Independencia", "Ética."),
        ("Aceptación/continuación", "5000", "(ISA 210) Carta", "Contrato."),
        ("Aceptación/continuación", "6000", "(ISA 510) Predecesor", "Comunicación.")
    ]
    cursor = conn.cursor()
    cursor.executemany("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)",
                       [(client_id, p[0], p[1], p[2], p[3]) for p in pasos])
    conn.commit()

# --- MÓDULOS TÉCNICOS ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Materialidad")
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            opts = ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"]
            idx = opts.index(datos[1]) if datos and datos[1] in opts else 0
            benchmark = st.selectbox("Benchmark", opts, index=idx)
            v_base = st.number_input("Base ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Perf", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR", 0.0, 10.0, datos[7] if datos else 5.0)
        
        m_gen = v_base * (p_gen/100)
    
    st.metric("Mat. General", f"$ {m_gen:,.2f}")
    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", 
                     (client_id, benchmark, v_base, p_gen, m_gen, p_perf, m_gen*(p_perf/100), p_ranr, m_gen*(p_ranr/100)))
        conn.commit(); conn.close(); st.success("Guardado.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name, CAST(step_code AS INTEGER)", conn, params=(client_id,))
    if steps.empty:
        if st.button("Generar Pasos Iniciales"): cargar_pasos_iniciales(conn, client_id); st.rerun()
        conn.close(); return
    for _, row in steps.iterrows():
        with st.expander(f"Paso {row['step_code']}: {row['description'][:50]}..."):
            n = st.text_area("Notas", value=row['user_notes'] or "", key=f"n_{row['id']}")
            s = st.selectbox("Estado", ["Sin Iniciar", "En Proceso", "Terminado"], index=["Sin Iniciar", "En Proceso", "Terminado"].index(row['status']), key=f"s_{row['id']}")
            if st.button("Guardar", key=f"b_{row['id']}"):
                conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n, s, row['id']))
                conn.commit(); st.toast("Ok")
    conn.close()

# --- VISTAS LOGIN ---
def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Ingresar", "Registrarse", "Recuperar"])
    with t1:
        e = st.text_input("Email", key="l1").lower().strip()
        p = st.text_input("Clave", type="password", key="l2")
        if st.button("Entrar", use_container_width=True):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
            else: st.error("Credenciales incorrectas.")
    with t2:
        n = st.text_input("Nombre Completo", key="reg_nom")
        em = st.text_input("Email", key="r1").lower().strip()
        p1 = st.text_input("Crear Clave", type="password", key="r2")
        p2 = st.text_input("Confirmar Clave", type="password", key="r3")
        r = st.selectbox("Rol", ["Miembro", "Administrador"])
        if st.button("Crear Cuenta", use_container_width=True):
            v, msg = validar_password(p1, p2)
            if v and n and em:
                try:
                    conn = get_db_connection(); conn.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (em, n, hash_pass(p1), r)); conn.commit(); conn.close(); st.success("Creado.")
                except: st.error("Email ya registrado.")
            else: st.warning(msg if not v else "Llene todos los campos.")
    with t3:
        em_rec = st.text_input("Email", key="rc1").lower().strip()
        nom_rec = st.text_input("Nombre Completo", key="rc_nom")
        p1_rec = st.text_input("Nueva Clave", type="password", key="rc2")
        p2_rec = st.text_input("Confirmar Nueva Clave", type="password", key="rc3")
        if st.button("Actualizar", use_container_width=True):
            v, msg = validar_password(p1_rec, p2_rec)
            if v:
                conn = get_db_connection(); u = conn.execute("SELECT id FROM users WHERE email=? AND full_name=?", (em_rec, nom_rec)).fetchone()
                if u: conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(p1_rec), u[0])); conn.commit(); st.success("Ok.")
                else: st.error("Datos no coinciden.")
            else: st.warning(msg)
    st.markdown('</div>', unsafe_allow_html=True)

# --- VISTA PRINCIPAL ---
def vista_principal():
    is_admin = st.session_state.user_role == "Administrador"

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name} ({st.session_state.user_role})")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.markdown("### 🔗 Consultas")
        st.markdown("[🔍 RUES](https://www.rues.org.co/busqueda-avanzada)", unsafe_allow_html=True)
        st.markdown("[📑 DIAN](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces;jsessionid=4D13ACA9FD43DD9D01CB14CEB87CC780.nodo26Rutmuisca)", unsafe_allow_html=True)
        st.divider()
        st.subheader("Nueva Empresa")
        n, nit = st.text_input("Nombre"), st.text_input("NIT")
        if st.button("Registrar Cliente"):
            if n:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n, nit))
                cargar_pasos_iniciales(conn, cur.lastrowid); conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        c1, c2 = st.columns(2)
        if c1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if c2.button("📝 Programa", use_container_width=True): st.session_state.mod = "Prog"
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Dashboard AuditPro")
        conn = get_db_connection()
        
        # LISTADO DE EMPRESAS ACTIVAS
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 0.5])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir", key=f"o_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
                
                if is_admin:
                    if col3.button("🗑️", key=f"del_btn_{r['id']}"):
                        st.session_state[f"confirm_del_{r['id']}"] = True
                    
                    if st.session_state.get(f"confirm_del_{r['id']}"):
                        st.warning(f"¿Eliminar {r['client_name']}?")
                        if st.button("Confirmar", key=f"conf_del_{r['id']}"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                            conn.commit()
                            del st.session_state[f"confirm_del_{r['id']}"]
                            st.rerun()
                        if st.button("Cancelar", key=f"canc_del_{r['id']}"):
                            del st.session_state[f"confirm_del_{r['id']}"]
                            st.rerun()

        # PAPELERA DE RECICLAJE (Solo Admin)
        if is_admin:
            deleted_clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=1", conn)
            if not deleted_clients.empty:
                st.markdown('<div class="trash-section">', unsafe_allow_html=True)
                st.subheader("♻️ Papelera de Reciclaje")
                for _, dr in deleted_clients.iterrows():
                    tc1, tc2 = st.columns([5, 1])
                    tc1.write(f"{dr['client_name']} (NIT: {dr['client_nit']})")
                    if tc2.button("Restaurar", key=f"rest_{dr['id']}"):
                        conn.execute("UPDATE clients SET is_deleted=0 WHERE id=?", (dr['id'],))
                        conn.commit(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
