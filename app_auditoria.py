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
    .login-card { background-color: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 500px; margin: auto; }
    .main-title { color: #1e3a8a; font-weight: 700; text-align: center; }
    .stButton>button { border-radius: 8px; transition: all 0.3s; }
    .admin-badge { background-color: #fee2e2; color: #dc2626; padding: 2px 8px; border-radius: 5px; font-size: 12px; font-weight: bold; }
    .guia-box { background-color: #f0f7ff; border-left: 5px solid #1e3a8a; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    .area-header { background-color: #e2e8f0; padding: 5px 10px; border-radius: 5px; font-weight: bold; color: #1e40af; margin-top: 15px; }
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
    # Actualización de tabla: Se añade area_name
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        client_id INTEGER, 
        section_name TEXT, 
        area_name TEXT, 
        step_code TEXT, 
        description TEXT, 
        instructions TEXT, 
        user_notes TEXT, 
        status TEXT DEFAULT "Sin Iniciar", 
        is_deleted INTEGER DEFAULT 0)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    
    # Script de migración simple para bases de datos existentes
    try:
        cursor.execute("ALTER TABLE audit_steps ADD COLUMN area_name TEXT DEFAULT 'General'")
    except sqlite3.OperationalError:
        pass # La columna ya existe
        
    conn.commit()
    conn.close()

create_tables()

# --- HELPER: CARGA DE PASOS INICIALES ---
def cargar_pasos_iniciales(conn, client_id):
    # Estructura: (Sección, Área, Código, Descripción, Instrucciones)
    pasos = [
        ("Planeación", "Aceptación", "1000", "(ISA 220) Evaluación de aceptación", "Evaluar integridad de socios."),
        ("Planeación", "Aceptación", "2000", "(ISA 210) Carta de encargo", "Verificar firma de términos."),
        ("Planeación", "Independencia", "3000", "Declaración de independencia", "Confirmar ausencia de conflictos."),
    ]
    cursor = conn.cursor()
    for p in pasos:
        exist = cursor.execute("SELECT id FROM audit_steps WHERE client_id=? AND section_name=? AND area_name=? AND step_code=?", (client_id, p[0], p[1], p[2])).fetchone()
        if not exist:
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
    st.markdown("### 📝 Programa de Trabajo (Estructura: Sección > Área)")
    conn = get_db_connection()
    
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]

    if steps.empty:
        st.info("No hay pasos. Vaya al módulo de Importar.")
        conn.close()
        return

    # Filtros
    secciones = ["Todas"] + list(steps['section_name'].unique())
    seccion_f = st.selectbox("📁 Seleccionar Sección:", secciones)
    
    df_f = steps.copy()
    if seccion_f != "Todas":
        df_f = df_f[df_f['section_name'] == seccion_f]

    # Visualización Agrupada por Áreas
    for area in df_f['area_name'].unique():
        st.markdown(f'<div class="area-header">📍 Área: {area}</div>', unsafe_allow_html=True)
        subset = df_f[df_f['area_name'] == area]
        
        for _, row in subset.iterrows():
            sid = row['id']
            status_icon = "⚪" if row['status'] == "Sin Iniciar" else "🟡" if row['status'] == "En Proceso" else "🟢"
            with st.expander(f"{status_icon} [{row['step_code']}] {row['description'][:80]}..."):
                st.info(f"**Guía:** {row['instructions']}")
                n_nota = st.text_area("Conclusiones:", value=row['user_notes'] or "", key=f"nt_{sid}")
                c1, c2 = st.columns(2)
                n_est = c1.selectbox("Estado", opciones_estado, index=opciones_estado.index(row['status'] if row['status'] in opciones_estado else "Sin Iniciar"), key=f"es_{sid}")
                if c2.button("Guardar", key=f"bt_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                    conn.commit()
                    st.toast("Actualizado")
    conn.close()

def modulo_importacion(client_id):
    st.markdown("### 📥 Importar (Sección > Área > Pasos)")
    st.write("El archivo debe tener: `Seccion`, `Area`, `Codigo`, `Descripcion`, `Instrucciones`")

    plantilla = pd.DataFrame({'Seccion':['Activo'], 'Area':['Caja'], 'Codigo':['1.1'], 'Descripcion':['Arqueo'], 'Instrucciones':['NIA 500']})
    st.download_button("Descargar Plantilla", plantilla.to_csv(index=False).encode('utf-8'), "plantilla.csv", "text/csv")

    up = st.file_uploader("Subir Excel/CSV", type=['xlsx', 'csv'])
    if up:
        df = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
        if all(c in df.columns for c in ['Seccion', 'Area', 'Codigo', 'Descripcion', 'Instrucciones']):
            if st.button("🚀 Iniciar Importación con Validación"):
                conn = get_db_connection(); cursor = conn.cursor()
                existentes = pd.read_sql_query("SELECT section_name, area_name, step_code FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
                set_ex = set(existentes['section_name'] + "|" + existentes['area_name'] + "|" + existentes['step_code'])
                
                nuevos = 0; saltados = 0
                for _, r in df.iterrows():
                    clave = f"{r['Seccion']}|{r['Area']}|{r['Codigo']}"
                    if clave not in set_ex:
                        cursor.execute("INSERT INTO audit_steps (client_id, section_name, area_name, step_code, description, instructions) VALUES (?,?,?,?,?,?)",
                                       (client_id, r['Seccion'], r['Area'], r['Codigo'], r['Descripcion'], r['Instrucciones']))
                        set_ex.add(clave); nuevos += 1
                    else: saltados += 1
                conn.commit(); conn.close()
                st.success(f"Cargados: {nuevos} | Duplicados saltados: {saltados}")
        else: st.error("Columnas incorrectas.")

# --- VISTAS SISTEMA ---
def vista_principal():
    with st.sidebar:
        st.write(f"Usuario: {st.session_state.user_name}")
        if st.button("Salir"): st.session_state.clear(); st.rerun()
        st.divider()
        n_name = st.text_input("Nueva Empresa")
        n_nit = st.text_input("NIT")
        if st.button("Registrar"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
            cargar_pasos_iniciales(conn, cur.lastrowid)
            conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Listado"): del st.session_state.active_id; st.rerun()
        st.subheader(f"Cliente: {st.session_state.active_name}")
        m1, m2, m3 = st.columns(3)
        if m1.button("Materialidad"): st.session_state.mod = "Mat"
        if m2.button("Programa"): st.session_state.mod = "Prog"
        if m3.button("Importar"): st.session_state.mod = "Imp"
        
        if st.session_state.get('mod') == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        elif st.session_state.get('mod') == "Imp": modulo_importacion(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Mis Auditorías")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Abrir", key=f"o_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']
                    st.rerun()
        conn.close()

def vista_login():
    st.markdown('<h1 class="main-title">⚖️ AuditPro Master</h1>', unsafe_allow_html=True)
    e = st.text_input("Email"); p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", (e, hashlib.sha256(p.encode()).hexdigest())).fetchone()
        conn.close()
        if u:
            st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]
            st.rerun()
        else: st.error("Error")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
