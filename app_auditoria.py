import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 10px; 
        margin-bottom: 10px; 
        border-radius: 5px;
        font-size: 14px;
        color: #0d47a1;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
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
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, user_id INTEGER, action TEXT, old_value TEXT, new_value TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Tabla de Materialidad Mejorada
    cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                     (client_id INTEGER PRIMARY KEY, 
                      benchmark TEXT,
                      benchmark_value REAL, 
                      p_general REAL, 
                      mat_general REAL,
                      p_performance REAL,
                      mat_performance REAL,
                      p_ranr REAL,
                      mat_ranr REAL)''')
    conn.commit()
    conn.close()

create_tables()

# --- LÓGICA DE MATERIALIDAD ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Cálculo de Materialidad (NIA 320)")
    
    conn = get_db_connection()
    # Intentar cargar datos previos
    datos_previos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()

    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            benchmark = st.selectbox("Benchmark (Base)", 
                ["Utilidad/Pérdida Neta", "Ingresos Totales", "Activos Totales", "EBITDA"],
                index=0 if not datos_previos else ["Utilidad/Pérdida Neta", "Ingresos Totales", "Activos Totales", "EBITDA"].index(datos_previos[1]))
            
            valor_base = st.number_input("Valor del Benchmark ($)", min_value=0.0, value=datos_previos[2] if datos_previos else 0.0, format="%.2f")
            
        with col2:
            if benchmark == "Utilidad/Pérdida Neta": max_p = 10.0
            elif benchmark == "Ingresos Totales": max_p = 5.0
            elif benchmark == "Activos Totales": max_p = 2.5
            else: max_p = 3.5 # EBITDA
            
            p_general = st.slider(f"% Materialidad General (Máx {max_p}%)", 0.0, max_p, datos_previos[3] if datos_previos else max_p / 2)
            p_performance = st.slider("% Planeación/Performance (Máx 75%)", 0.0, 75.0, datos_previos[5] if datos_previos else 50.0)
            
        with col3:
            p_ranr = st.slider("% Límite Errores (RANR) (Máx 10%)", 0.0, 10.0, datos_previos[7] if datos_previos else 5.0)

        # Cálculos
        mat_general = valor_base * (p_general / 100)
        mat_performance = mat_general * (p_performance / 100)
        mat_ranr = mat_general * (p_ranr / 100)

    # Resultados visuales
    
    res1, res2, res3 = st.columns(3)
    res1.metric("Materialidad General", f"$ {mat_general:,.2f}")
    res2.metric("Mat. Desempeño", f"$ {mat_performance:,.2f}")
    res3.metric("Límite RANR", f"$ {mat_ranr:,.2f}")

    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("""INSERT OR REPLACE INTO materiality 
            (client_id, benchmark, benchmark_value, p_general, mat_general, p_performance, mat_performance, p_ranr, mat_ranr) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
            (client_id, benchmark, valor_base, p_general, mat_general, p_performance, mat_performance, p_ranr, mat_ranr))
        conn.commit()
        conn.close()
        st.success("Cálculos guardados en el expediente.")

# --- VISTA PAPELES DE TRABAJO ---
def vista_papeles_trabajo(client_id, client_name):
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    if st.button("⬅️ Volver al Panel"):
        del st.session_state.active_id
        st.rerun()

    # CREACIÓN DE PESTAÑAS
    tab1, tab2 = st.tabs(["📊 Materialidad", "📝 Programa de Trabajo"])

    with tab1:
        modulo_materialidad(client_id)

    with tab2:
        conn = get_db_connection()
        steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
        cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
        
        for seccion in steps_db['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_db[steps_db['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>{cols_l.get(row['status'], '⚪')} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    
                    c_det, c_est = st.columns([4, 1])
                    with c_det:
                        notas = st.text_area("Hallazgos / Notas", value=row['user_notes'] or "", key=f"n_{sid}")
                        if st.button("Guardar Nota", key=f"s_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                            conn.commit()
                            st.toast("Guardado")
                    with c_est:
                        nuevo = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], 
                                             index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid))
                            conn.commit()
                            st.rerun()
        conn.close()

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa")
        ct = st.text_input("NIT")
        tipo = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa"])
        if st.button("Crear"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo) VALUES (?,?,?,?)", (st.session_state.user_id, cn, ct, tipo))
            cid = cur.lastrowid
            TEMPLATE_AUDITORIA = [("100 - Aceptación", "1000", "Evaluación de Integridad", "NIA 220")]
            for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
            conn.commit()
            conn.close()
            st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Gestión de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, tipo_trabajo, estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                c1.write(f"**{r['client_name']}**")
                c2.write(f"_{r['tipo_trabajo']}_")
                c3.write(f"{r['estado']}")
                if c4.button("Abrir", key=f"b_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def vista_login():
    st.title("⚖️ AuditPro")
    t1, t2 = st.tabs(["Ingreso", "Registro"])
    with t1:
        with st.form("login"):
            e, p = st.text_input("Correo"), st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                conn = get_db_connection()
                u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                conn.close()
                if u: 
                    st.session_state.user_id = u[0]
                    st.session_state.user_name = u[1]
                    st.rerun()
                else: st.error("Acceso incorrecto")
    with t2:
        with st.form("reg"):
            n, e, p = st.text_input("Nombre"), st.text_input("Email"), st.text_input("Pass", type="password")
            if st.form_submit_button("Registrar"):
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, n, hash_pass(p)))
                    conn.commit()
                    st.success("OK")
                except: st.error("Error")
                conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
