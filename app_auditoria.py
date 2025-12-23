import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from io import BytesIO
from docx import Document
from fpdf import FPDF

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
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    # Aumentamos el timeout para evitar colisiones en escrituras simultáneas
    return sqlite3.connect('audit_management.db', timeout=30, check_same_thread=False)

def create_tables():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
        cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, user_id INTEGER, action TEXT, old_value TEXT, new_value TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER UNIQUE, benchmark_name TEXT, benchmark_value REAL, percentage REAL, planned_materiality REAL)''')
        conn.commit()

create_tables()

def log_change(step_id, user_id, action, old_val, new_val):
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO audit_logs (step_id, user_id, action, old_value, new_value) VALUES (?,?,?,?,?)",
                         (step_id, user_id, action, str(old_val), str(new_val)))
            conn.commit()
    except Exception as e:
        print(f"Error log: {e}")

# --- LÓGICA DE MATERIALIDAD ---
def seccion_materialidad(client_id):
    st.subheader("📊 Cálculo de Materialidad (NIA 320)")
    
    with get_db_connection() as conn:
        data = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        benchmark = st.selectbox("Referencia (Benchmark)", ["Utilidad antes de Impuestos", "Activos Totales", "Ingresos Totales", "Patrimonio"], 
                                 index=0 if not data else ["Utilidad antes de Impuestos", "Activos Totales", "Ingresos Totales", "Patrimonio"].index(data[2]))
    with col2:
        valor = st.number_input("Valor de la Referencia ($)", value=float(data[3]) if data else 0.0, format="%.2f")
    with col3:
        porcentaje = st.slider("% Materialidad", 0.5, 5.0, float(data[4]) if data else 1.0, 0.1)

    resultado = valor * (porcentaje / 100)
    st.info(f"**Materialidad de Planeación Calculada: ${resultado:,.2f}**")
    
    if st.button("💾 Guardar Materialidad"):
        with get_db_connection() as conn:
            conn.execute("""INSERT OR REPLACE INTO materiality (client_id, benchmark_name, benchmark_value, percentage, planned_materiality) 
                            VALUES (?,?,?,?,?)""", (client_id, benchmark, valor, porcentaje, resultado))
            conn.commit()
        st.success("Materialidad actualizada")

# --- VISTA PAPELES DE TRABAJO ---
def vista_papeles_trabajo(client_id, client_name):
    st.markdown(f"## 📂 Expediente: {client_name}")
    if st.button("⬅️ Volver al Panel"):
        del st.session_state.active_id
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["📝 Ejecución", "⚖️ Materialidad", "📜 Historial (NIA 230)"])

    with tab1:
        # Abrimos conexión específica para la consulta de pasos
        with get_db_connection() as conn:
            steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
        
        cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
        for seccion in steps_db['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_db[steps_db['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>{cols_l.get(row['status'], '⚪')} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    
                    c_det, c_est, c_file = st.columns([3, 1, 1.5])
                    with c_det:
                        notas = st.text_area("Hallazgos / Notas", value=row['user_notes'] or "", key=f"n_{sid}")
                        if st.button("Guardar", key=f"s_{sid}"):
                            log_change(sid, st.session_state.user_id, "Nota", row['user_notes'], notas)
                            with get_db_connection() as conn_upd:
                                conn_upd.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                                conn_upd.commit()
                            st.toast("Guardado")

                    with c_est:
                        nuevo = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo != row['status']:
                            log_change(sid, st.session_state.user_id, "Estado", row['status'], nuevo)
                            with get_db_connection() as conn_upd:
                                conn_upd.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid))
                                conn_upd.commit()
                            st.rerun()
                    
                    with c_file:
                        up = st.file_uploader("Adjuntar", key=f"up_{sid}")
                        if up:
                            with get_db_connection() as conn_upd:
                                conn_upd.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", (sid, up.name, up.read()))
                                conn_upd.commit()
                            st.rerun()

    with tab2:
        seccion_materialidad(client_id)

    with tab3:
        st.subheader("Trazabilidad de la Auditoría")
        # Corrección: Abrimos una conexión limpia para el reporte de logs de Pandas
        with get_db_connection() as conn_logs:
            query = """SELECT timestamp, action, old_value, new_value 
                       FROM audit_logs 
                       WHERE step_id IN (SELECT id FROM audit_steps WHERE client_id=?) 
                       ORDER BY timestamp DESC"""
            logs_df = pd.read_sql_query(query, conn_logs, params=(client_id,))
        
        if not logs_df.empty:
            st.dataframe(logs_df, use_container_width=True)
        else:
            st.info("No hay registros de cambios para este cliente aún.")

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.title("AuditPro 2025")
        st.write(f"👤 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Cliente")
        cn = st.text_input("Nombre Empresa")
        tipo = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría", "Impuestos"])
        if st.button("Crear Encargo"):
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, tipo_trabajo) VALUES (?,?,?)", (st.session_state.user_id, cn, tipo))
                cid = cur.lastrowid
                plantilla = [
                    ("100 - Inicio", "1000", "Aceptación", "Validar integridad y NIA 210"),
                    ("200 - Riesgos", "2000", "Materialidad", "Calcular umbrales NIA 320"),
                    ("300 - Ejecución", "3000", "Pruebas Sustantivas", "Documentar hallazgos")
                ]
                for sec, cod, desc, ins in plantilla:
                    conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
                conn.commit()
            st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("🚀 Dashboard de Auditoría")
        with get_db_connection() as conn:
            clients = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
            
        for _, r in clients.iterrows():
            with get_db_connection() as conn:
                steps = pd.read_sql_query("SELECT status FROM audit_steps WHERE client_id=?", conn, params=(r['id'],))
            
            total = len(steps)
            cerrados = len(steps[steps['status'] == 'Cerrado'])
            progreso = (cerrados / total) if total > 0 else 0
            
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 4, 1])
                c1.write(f"### {r['client_name']}")
                c1.write(f"_{r['tipo_trabajo']}_")
                c2.write(f"**Avance: {progreso*100:.0f}%**")
                c2.progress(progreso)
                if c3.button("Abrir", key=f"btn_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()

def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_login():
    st.title("⚖️ AuditPro")
    t1, t2 = st.tabs(["Ingreso", "Registro"])
    with t1:
        with st.form("l"):
            e, p = st.text_input("Correo"), st.text_input("Clave", type="password")
            if st.form_submit_button("Entrar"):
                with get_db_connection() as conn:
                    u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                if u: 
                    st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                    st.rerun()
                else: st.error("Usuario o clave incorrectos")
    with t2:
        with st.form("r"):
            n, e, p = st.text_input("Nombre"), st.text_input("Correo"), st.text_input("Clave", type="password")
            if st.form_submit_button("Registrar"):
                try:
                    with get_db_connection() as conn:
                        conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, n, hash_pass(p)))
                        conn.commit()
                    st.success("Usuario registrado exitosamente.")
                except:
                    st.error("El correo ya existe.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
