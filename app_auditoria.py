import hashlib
import sqlite3
import pandas as pd
import streamlit as st
import io

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
    .area-header {
        background-color: #f1f5f9;
        padding: 10px;
        border-radius: 8px;
        border-left: 8px solid #3b82f6;
        margin: 20px 0 10px 0;
        font-weight: bold;
        color: #1e40af;
        font-size: 1.1em;
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        client_id INTEGER, 
        section_name TEXT, 
        area_name TEXT DEFAULT "General",
        step_code TEXT, 
        description TEXT, 
        instructions TEXT, 
        user_notes TEXT, 
        status TEXT DEFAULT "Sin Iniciar", 
        is_deleted INTEGER DEFAULT 0)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    
    try:
        cursor.execute("ALTER TABLE audit_steps ADD COLUMN area_name TEXT DEFAULT 'General'")
    except:
        pass
        
    conn.commit()
    conn.close()

create_tables()

# --- HELPER: CARGA DE PASOS INICIALES ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
        ("Planeación", "Aceptación", "1000", "(ISA 220, 300) Evaluar aceptación", "Realice evaluación de riesgos."),
        ("Planeación", "Aceptación", "2000", "(ISA 220) Designar QRP", "Evaluar revisión de calidad."),
        ("Planeación", "Ética", "4000", "(ISA 200) Requisitos éticos", "Documentar independencia."),
        ("Planeación", "Contratación", "5000", "(ISA 210) Carta encargo", "Verificar firma representante.")
    ]
    cursor = conn.cursor()
    for p in pasos:
        cursor.execute("INSERT INTO audit_steps (client_id, section_name, area_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?, ?)", (client_id, p[0], p[1], p[2], p[3], p[4]))
    conn.commit()

# --- MÓDULOS ---
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
        conn.commit(); conn.close()
        st.success("Guardado.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    # Cargamos y ordenamos
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name ASC, area_name ASC, step_code ASC", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]

    if steps.empty:
        st.info("No hay pasos. Use el módulo de importación.")
        conn.close()
        return

    # Filtros superiores
    c_f1, c_f2 = st.columns([2, 1])
    search = c_f1.text_input("🔍 Buscar por descripción o código:", "")
    sec_options = ["Todas"] + sorted(list(steps['section_name'].unique()))
    seccion_f = c_f2.selectbox("📁 Filtrar por Sección:", sec_options)

    df_f = steps.copy()
    if search:
        df_f = df_f[df_f['description'].str.contains(search, case=False) | df_f['step_code'].str.contains(search, case=False)]
    if seccion_f != "Todas":
        df_f = df_f[df_f['section_name'] == seccion_f]

    # Renderizado: ÁREA (Header) -> PASOS (Expanders)
    for area in df_f['area_name'].unique():
        st.markdown(f'<div class="area-header">📍 Área: {area}</div>', unsafe_allow_html=True)
        subset_area = df_f[df_f['area_name'] == area]
        
        for _, row in subset_area.iterrows():
            sid = row['id']
            status_icon = "⚪" if row['status'] == "Sin Iniciar" else "🟡" if row['status'] == "En Proceso" else "🟢"
            
            with st.expander(f"{status_icon} [{row['step_code']}] - {row['description'][:100]}..."):
                st.markdown(f"**Procedimiento:** {row['description']}")
                st.markdown(f'<div class="guia-box"><strong>Guía Técnica / Instrucciones:</strong><br>{row["instructions"]}</div>', unsafe_allow_html=True)
                
                n_nota = st.text_area("Conclusiones y evidencia:", value=row['user_notes'] or "", key=f"nt_{sid}", height=120)
                col_e, col_b = st.columns([1, 1])
                n_est = col_e.selectbox("Estado del paso", opciones_estado, index=opciones_estado.index(row['status'] if row['status'] in opciones_estado else "Sin Iniciar"), key=f"es_{sid}")
                if col_b.button("💾 Actualizar Paso", key=f"btn_{sid}", use_container_width=True):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit()
                    st.toast(f"Paso {row['step_code']} guardado.")
    conn.close()

def modulo_importacion(client_id):
    st.markdown("### 📥 Importar Pasos")
    
    # Plantilla de ejemplo
    st.markdown("#### 1. Obtener Plantilla")
    p_data = {
        'Seccion': ['Activo', 'Pasivo'],
        'Area': ['Caja', 'Proveedores'],
        'Codigo': ['101', '201'],
        'Descripcion': ['Arqueo de caja', 'Confirmación de saldos'],
        'Instrucciones': ['NIA 500', 'NIA 505']
    }
    df_p = pd.DataFrame(p_data)
    csv_p = df_p.to_csv(index=False).encode('utf-8-sig')
    st.download_button("⬇️ Descargar Formato CSV", data=csv_p, file_name="plantilla_auditpro.csv", mime="text/csv")
    
    st.divider()
    st.markdown("#### 2. Subir Archivo")
    up = st.file_uploader("Subir Excel o CSV", type=['xlsx', 'csv'])
    if up:
        try:
            df = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
            req = ['Seccion', 'Area', 'Codigo', 'Descripcion', 'Instrucciones']
            if all(c in df.columns for c in req):
                st.dataframe(df.head(3))
                if st.button("🚀 Procesar e Importar"):
                    conn = get_db_connection(); cursor = conn.cursor()
                    existentes = pd.read_sql_query("SELECT section_name, area_name, step_code FROM audit_steps WHERE client_id=? AND is_deleted=0", conn, params=(client_id,))
                    set_ex = set(existentes['section_name'].astype(str) + "|" + existentes['area_name'].astype(str) + "|" + existentes['step_code'].astype(str))
                    
                    nuevos = 0
                    for _, r in df.iterrows():
                        clave = f"{r['Seccion']}|{r['Area']}|{r['Codigo']}"
                        if clave not in set_ex:
                            cursor.execute("INSERT INTO audit_steps (client_id, section_name, area_name, step_code, description, instructions) VALUES (?,?,?,?,?,?)",
                                           (client_id, r['Seccion'], r['Area'], r['Codigo'], r['Descripcion'], r['Instrucciones']))
                            nuevos += 1
                    conn.commit(); conn.close()
                    st.success(f"Se importaron {nuevos} pasos correctamente.")
            else:
                st.error(f"El archivo debe contener las columnas: {req}")
        except Exception as e:
            st.error(f"Error: {e}")

# --- VISTAS PRINCIPALES ---
def vista_principal():
    is_admin = "Administrador" in st.session_state.get('user_role', "Miembro")

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.markdown(f"<span class='admin-badge'>{st.session_state.user_role}</span>", unsafe_allow_html=True)
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Nueva Auditoría")
        n_name = st.text_input("Nombre Empresa")
        n_nit = st.text_input("NIT")
        if st.button("Crear Cliente"):
            if n_name:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
                cargar_pasos_iniciales(conn, cur.lastrowid)
                conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver al Panel"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 {st.session_state.active_name}")
        
        m1, m2, m3 = st.columns(3)
        if m1.button("📊 Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.mod = "Prog"
        if m3.button("📥 Importar Pasos", use_container_width=True): st.session_state.mod = "Imp"
        
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        elif st.session_state.get('mod') == "Imp": modulo_importacion(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Mis Auditorías")
        c1, c2 = st.columns(2)
        c1.link_button("🌐 Consultar RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c2.link_button("🏢 Consultar RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        st.divider()
        
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1.5, 0.5])
                col1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                if col2.button("Abrir Auditoría", key=f"op_{r['id']}", use_container_width=True):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']
                    st.rerun()
                if is_admin:
                    with col3.popover("🗑️"):
                        if st.button("Confirmar", key=f"del_{r['id']}"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],))
                            conn.commit(); st.rerun()
        conn.close()

def vista_login():
    st.markdown('<div class="login-card"><h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    e = st.text_input("Usuario (Email)"); p = st.text_input("Clave", type="password")
    if st.button("Acceder", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hashlib.sha256(p.encode()).hexdigest())).fetchone()
        conn.close()
        if u:
            st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]
            st.rerun()
        else: st.error("Credenciales inválidas")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
