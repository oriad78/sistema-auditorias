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
    .status-text { font-weight: bold; font-size: 14px; }
    .file-box { background-color: #f8f9fa; padding: 8px; border-radius: 5px; border: 1px dashed #ccc; margin-bottom: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS Y MIGRACIONES ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB)')
    
    try:
        cursor.execute('SELECT tipo_trabajo FROM clients LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE clients ADD COLUMN tipo_trabajo TEXT DEFAULT "Auditoría"')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                      benchmark_value REAL, percentage REAL, planned_materiality REAL)''')
    conn.commit()
    conn.close()

create_tables()

# --- PLANTILLA MAESTRA ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente", "Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar alto riesgo."),
    ("100 - Aceptación y continuación", "4000", "(ISA 200, 220, 300) Requisitos éticos e independencia", "Confirmar independencia."),
    ("100 - Aceptación y continuación", "4010", "Realizar otras tareas específicas relativas a independencia", "Verificar servicios no auditoría."),
    ("100 - Aceptación y continuación", "5000", "(ISA 210, 300) Carta de contratación actualizada", "Adjuntar PDF firmado."),
    ("150 - Administración", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación recursos."),
    ("1100 - Comprensión", "1000", "(ISA 315) Entendimiento del cliente y ambiente", "Análisis negocio."),
    ("1250 - Riesgo de Fraude", "1000", "(ISA 240, 315) Responder al riesgo de fraude", "Triángulo fraude.")
]

# --- FUNCIONES DE EXPORTACIÓN ---
def crear_word(df, client_name):
    doc = Document()
    doc.add_heading(f'INFORME DE AUDITORÍA: {client_name.upper()}', 0)
    for _, row in df.iterrows():
        doc.add_heading(f"{row['step_code']} - {row['description']}", level=2)
        doc.add_paragraph(f"Estado: {row['status']}")
        doc.add_paragraph(f"Comentarios: {row['user_notes'] or 'Sin observaciones'}")
    target = BytesIO()
    doc.save(target)
    return target.getvalue()

def crear_pdf(df, client_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(211, 47, 47)
    pdf.cell(190, 10, "AUDITPRO - REPORTE DE EJECUCIÓN", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 10, f"Cliente: {client_name}", ln=True, align='C')
    pdf.line(10, 32, 200, 32)
    for _, row in df.iterrows():
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.multi_cell(190, 7, f"PASO {row['step_code']}: {row['description']}")
        pdf.set_font("Arial", size=9)
        pdf.cell(190, 7, f"ESTADO: {row['status']}", ln=True)
        pdf.multi_cell(190, 7, f"NOTAS: {row['user_notes'] or 'N/A'}")
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- FUNCIONES LÓGICAS ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def inicializar_programa_auditoria(client_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM audit_steps WHERE client_id = ?", (client_id,))
    for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (client_id, sec, cod, desc, ins))
    conn.commit(); conn.close()

# --- COMPONENTES DE INTERFAZ ---
def seccion_materialidad(client_id):
    st.subheader("📊 Cálculo de Materialidad (NIA 320)")
    conn = get_db_connection()
    mat_data = conn.execute("SELECT benchmark_value, percentage, planned_materiality FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        base = col1.number_input("Base (Ingresos/Activos)", value=mat_data[0] if mat_data else 0.0)
        porc = col2.slider("% Aplicable", 0.5, 5.0, mat_data[1] if mat_data else 1.0)
        res = base * (porc / 100)
        col3.metric("Materialidad", f"${res:,.2f}")
        if st.button("Actualizar Materialidad"):
            conn.execute("DELETE FROM materiality WHERE client_id=?", (client_id,))
            conn.execute("INSERT INTO materiality (client_id, benchmark_value, percentage, planned_materiality) VALUES (?,?,?,?)", (client_id, base, porc, res))
            conn.commit(); st.success("Guardado")
    conn.close()

def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    col_v, col_e = st.columns([1, 5])
    if col_v.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = col_e.toggle("⚙️ Herramientas / Materialidad / Exportar")

    if editar:
        seccion_materialidad(client_id)
        st.subheader("📥 Exportar Informe")
        steps_df = pd.read_sql_query("SELECT section_name, step_code, description, user_notes, status FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
        steps_df['user_notes'] = steps_df['user_notes'].fillna('')
        c1, c2, c3 = st.columns(3)
        out_ex = BytesIO()
        with pd.ExcelWriter(out_ex, engine='xlsxwriter') as wr: steps_df.to_excel(wr, index=False)
        c1.download_button("📊 Excel", data=out_ex.getvalue(), file_name=f"Audit_{client_name}.xlsx")
        c2.download_button("📝 Word", data=crear_word(steps_df, client_name), file_name=f"Audit_{client_name}.docx")
        c3.download_button("📕 PDF", data=crear_pdf(steps_df, client_name), file_name=f"Audit_{client_name}.pdf")

    steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
    
    for seccion in steps_db['section_name'].unique():
        with st.expander(f"📁 {seccion}", expanded=True):
            pasos = steps_db[steps_db['section_name'] == seccion]
            for _, row in pasos.iterrows():
                sid = row['id']
                # Título con bolita de color
                st.markdown(f"<div class='step-header'>{cols_l.get(row['status'], '⚪')} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                
                c_det, c_est, c_file = st.columns([3, 1, 1.5])
                with c_det:
                    notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"n_{sid}", height=80)
                    if st.button("💾 Guardar", key=f"s_{sid}"):
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid)); conn.commit(); st.toast("Guardado")
                with c_est:
                    st.write(f"**Estado:** {cols_l.get(row['status'], '⚪')}")
                    nuevo = st.selectbox("Cambiar:", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                    if nuevo != row['status']:
                        conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid)); conn.commit(); st.rerun()
                with c_file:
                    up = st.file_uploader("Adjuntar", key=f"up_{sid}", label_visibility="collapsed")
                    if up:
                        conn.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", (sid, up.name, up.read()))
                        conn.commit(); st.success("Ok"); st.rerun()
                    archivos = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                    for fid, fname, fdata in archivos:
                        st.markdown(f"<div class='file-box'>📎 {fname}</div>", unsafe_allow_html=True)
                        st.download_button("📥", data=fdata, file_name=fname, key=f"dl_{fid}")
    conn.close()

def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    tab1, tab2 = st.tabs(["🔐 Ingreso", "📝 Registro"])
    with tab1:
        with st.form("login"):
            e = st.text_input("Correo")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                conn = get_db_connection()
                u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                conn.close()
                if u: 
                    st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                    st.rerun()
                else: st.error("Acceso denegado")
    with tab2:
        with st.form("registro"):
            n = st.text_input("Nombre Completo")
            e = st.text_input("Correo")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Crear Cuenta"):
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?,?,?)", (n, e, hash_pass(p)))
                    conn.commit(); st.success("Usuario creado")
                except: st.error("El correo ya existe")
                finally: conn.close()

def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa"); ct = st.text_input("NIT")
        tipo_t = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Otros"])
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo, estado) VALUES (?,?,?,?,?)", 
                       (st.session_state.user_id, cn, ct, tipo_t, "Pendiente"))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()
        st.divider()
        
        # --- LINKS HORIZONTALES (CORREGIDOS) ---
        st.subheader("🔗 Consultas Rápidas")
        c_r1, c_r2 = st.columns(2)
        with c_r1: st.markdown("[🔍 RUES](https://www.rues.org.co/busqueda-avanzada)")
        with c_r2: st.markdown("[🔍 DIAN](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces)")

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Gestión de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, tipo_trabajo, estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
        
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                # Bolita de color en la lista principal
                c1.write(f"{cols_l.get(r['estado'], '⚪')} **{r['client_name']}** (NIT: {r['client_nit']})")
                c2.write(f"_{r['tipo_trabajo']}_")
                c3.write(f"{r['estado']}")
                if c4.button("Abrir", key=f"b_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()
        conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
