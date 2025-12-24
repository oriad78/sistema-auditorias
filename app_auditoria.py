import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS PROFESIONALES (CSS) ---
st.markdown("""
    <style>
    .login-card { background-color: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 500px; margin: auto; }
    .main-title { color: #1e3a8a; font-weight: 700; text-align: center; }
    .stButton>button { border-radius: 8px; transition: all 0.3s; }
    .admin-badge { background-color: #fee2e2; color: #dc2626; padding: 2px 8px; border-radius: 5px; font-size: 12px; font-weight: bold; }
    .guia-box { background-color: #f0f7ff; border-left: 5px solid #1e3a8a; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
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

# --- MÓDULO: IMPORTACIÓN MASIVA (NUEVO) ---
def modulo_importacion_masiva(client_id):
    st.markdown("### 📥 Carga Masiva desde Excel (NIA 230)")
    st.info("Asegúrese de que su Excel tenga estas columnas: section_name, step_code, description, instructions")
    
    archivo = st.file_uploader("Subir archivo Excel de Auditoría", type=['xlsx'])
    
    if archivo is not None:
        try:
            df_import = pd.read_excel(archivo)
            st.write(f"📊 Se han detectado {len(df_import)} procedimientos para cargar.")
            
            if st.button("🚀 Ejecutar Carga Masiva"):
                conn = get_db_connection()
                for _, fila in df_import.iterrows():
                    conn.execute("""
                        INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (client_id, str(fila['section_name']), str(fila['step_code']), str(fila['description']), str(fila['instructions'])))
                conn.commit()
                conn.close()
                st.success("✅ Importación completada con éxito.")
                st.balloons()
        except Exception as e:
            st.error(f"Error al leer el Excel: {e}. Verifique que los nombres de las columnas coincidan.")

# --- MÓDULO: MATERIALIDAD ---
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

# --- MÓDULO: PROGRAMA DE TRABAJO (OPTIMIZADO) ---
def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    
    # Filtro de búsqueda
    busqueda = st.text_input("🔍 Buscar procedimiento...")
    
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]
    
    if steps.empty:
        st.info("No hay pasos cargados. Use el botón 'Carga Masiva' para añadir procedimientos.")
        conn.close()
        return

    # Si hay búsqueda, filtramos
    if busqueda:
        steps = steps[steps['description'].str.contains(busqueda, case=False)]

    # Paginación simple para no saturar
    items_por_pagina = 15
    total_pasos = len(steps)
    if total_pasos > items_por_pagina:
        pagina = st.number_input(f"Página (1 de {int(total_pasos/items_por_pagina)+1})", min_value=1, step=1)
        inicio = (pagina - 1) * items_por_pagina
        steps = steps.iloc[inicio:inicio+items_por_pagina]

    for _, row in steps.iterrows():
        sid = row['id']
        with st.expander(f"Paso {row['step_code']}: {row['description'][:80]}..."):
            st.markdown(f'<div class="guia-box"><strong>Instrucciones:</strong><br>{row["instructions"]}</div>', unsafe_allow_html=True)
            n_nota = st.text_area("Evidencia/Notas:", value=row['user_notes'] or "", key=f"nt_{sid}")
            n_est = st.selectbox("Estado", opciones_estado, index=opciones_estado.index(row['status']), key=f"es_{sid}")
            if st.button("💾 Guardar", key=f"btn_{sid}"):
                conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                conn.commit(); st.toast("Guardado"); st.rerun()
    conn.close()

# --- VISTA PRINCIPAL ---
def vista_principal():
    user_role = st.session_state.get('user_role', "Miembro")
    is_admin = "Administrador" in user_role

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
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver al Listado"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        
        # AQUÍ ESTÁN LOS 3 BOTONES QUE BUSCÁBAMOS
        m1, m2, m3 = st.columns(3)
        if m1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.mod = "Prog"
        if m3.button("📥 Carga Masiva", use_container_width=True): st.session_state.mod = "Imp"
        
        if st.session_state.get('mod') == "Prog": 
            modulo_programa_trabajo(st.session_state.active_id)
        elif st.session_state.get('mod') == "Imp":
            modulo_importacion_masiva(st.session_state.active_id)
        else: 
            modulo_materialidad(st.session_state.active_id)
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

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    e = st.text_input("Correo"); p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]; st.rerun()
        else: st.error("Credenciales incorrectas")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state:
        vista_login()
    else:
        vista_principal()
