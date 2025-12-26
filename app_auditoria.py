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
    .guia-box {
        background-color: #f0f7ff;
        border-left: 5px solid #1e3a8a;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
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

# --- FUNCIONES DE SEGURIDAD ---
def hash_pass(p): 
    return hashlib.sha256(p.encode()).hexdigest()

def validar_password(p, p_confirm):
    if p != p_confirm:
        return False, "Las contraseñas no coinciden."
    if len(p) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if not re.search("[a-z]", p) or not re.search("[0-9]", p):
        return False, "La contraseña debe incluir letras y números."
    return True, ""

# --- HELPER: CARGA DE PASOS INICIALES ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
        ("Aceptación/continuación", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Realice una evaluación de riesgos del cliente. Considere la integridad de los propietarios y la capacidad del equipo para realizar el trabajo."),
        ("Aceptación/continuación", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP", "Evaluar si el compromiso requiere una revisión de control de calidad del trabajo según la complejidad del cliente."),
        ("Aceptación/continuación", "4000", "(ISA 200, 220, 300) Cumplimiento de requisitos éticos", "Documentar la independencia de todo el equipo y verificar que no existan conflictos de interés."),
        ("Aceptación/continuación", "5000", "(ISA 210, 300) Carta de contratación", "Verificar que la carta de encargo esté firmada por el representante legal y cubra los periodos actuales."),
        ("Aceptación/continuación", "6000", "(ISA 510) Contacto con auditores anteriores", "En caso de ser primera auditoría, documentar la comunicación con el auditor predecesor.")
    ]
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)",
        [(client_id, p[0], p[1], p[2], p[3]) for p in pasos]
    )
    conn.commit()

# --- MÓDULOS DE AUDITORÍA ---
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
    st.markdown("### 📝 Programa de Trabajo (Optimizado)")
    conn = get_db_connection()
    query = "SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name, CAST(step_code AS INTEGER)"
    steps = pd.read_sql_query(query, conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]

    if steps.empty:
        st.info("No hay pasos cargados.")
        if st.button("Generar Pasos Iniciales"):
            cargar_pasos_iniciales(conn, client_id)
            st.rerun()
        conn.close()
        return

    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        search_query = st.text_input("🔍 Buscar en procedimientos:", placeholder="Ej: Riesgo...")
    with col_f2:
        seccion_f = st.selectbox("📁 Filtrar por Sección:", ["Todas"] + list(steps['section_name'].unique()))

    df_filtrado = steps.copy()
    if search_query:
        df_filtrado = df_filtrado[df_filtrado['description'].str.contains(search_query, case=False)]
    if seccion_f != "Todas":
        df_filtrado = df_filtrado[df_filtrado['section_name'] == seccion_f]

    items_por_pagina = 20
    total_pasos = len(df_filtrado)
    num_paginas = (total_pasos // items_por_pagina) + (1 if total_pasos % items_por_pagina > 0 else 0)
    
    pagina_actual = st.number_input(f"Página (de {num_paginas})", min_value=1, max_value=num_paginas, step=1) if num_paginas > 1 else 1

    inicio = (pagina_actual - 1) * items_por_pagina
    subset_pasos = df_filtrado.iloc[inicio:inicio+items_por_pagina]

    for _, row in subset_pasos.iterrows():
        sid = row['id']
        status_icon = "⚪" if row['status'] == "Sin Iniciar" else "🟡" if row['status'] == "En Proceso" else "🟢"
        with st.expander(f"{status_icon} Paso {row['step_code']}: {row['description'][:80]}..."):
            st.info(f"Instrucciones: {row['instructions']}")
            n_nota = st.text_area("Conclusiones:", value=row['user_notes'] or "", key=f"nt_{sid}")
            n_est = st.selectbox("Estado", opciones_estado, index=opciones_estado.index(row['status']), key=f"es_{sid}")
            if st.button("💾 Guardar", key=f"btn_{sid}"):
                conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (n_nota, n_est, sid))
                conn.commit()
                st.toast("Actualizado")
    conn.close()

def modulo_importacion(client_id):
    st.markdown("### 📥 Importar Procedimientos")
    uploaded_file = st.file_uploader("Archivo Excel/CSV", type=['xlsx', 'csv'])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            if st.button("🚀 Confirmar Importación"):
                conn = get_db_connection()
                for _, r in df.iterrows():
                    conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)",
                                 (client_id, str(r['Seccion']), str(r['Codigo']), str(r['Descripcion']), str(r['Instrucciones'])))
                conn.commit(); conn.close()
                st.success("Importado con éxito.")
        except Exception as e: st.error(f"Error: {e}")

# --- VISTAS DE AUTENTICACIÓN ---
def vista_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
