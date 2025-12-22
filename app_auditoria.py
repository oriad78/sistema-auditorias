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
    .file-box { background-color: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px dashed #ccc; margin-top: 5px; }
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
    # Encabezado formal
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(211, 47, 47) # Color rojo AuditPro
    pdf.cell(190, 10, "AUDITPRO - REPORTE DE EJECUCIÓN", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 10, f"Cliente: {client_name}", ln=True, align='C')
    pdf.line(10, 32, 200, 32)
    
    for _, row in df.iterrows():
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 11)
        pdf.multi_cell(190, 7, f"PASO {row['step_code']}: {row['description']}")
        pdf.set_font("Arial", size=10)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(190, 7, f"ESTADO: {row['status']}", ln=True, fill=True)
        pdf.multi_cell(190, 7, f"DETALLE: {row['user_notes'] or 'N/A'}")
        pdf.ln(2)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- FUNCIONES LÓGICAS ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- VISTA: PAPELERÍA ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    col_v, col_e = st.columns([1, 5])
    if col_v.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = col_e.toggle("⚙️ Configuración / Exportar / Materialidad")
    
    if editar:
        # Reutilizamos la lógica de materialidad
        import __main__
        if hasattr(__main__, 'seccion_materialidad'): __main__.seccion_materialidad(client_id)
        
        st.subheader("📥 Generar Reportes Finales")
        steps_df = pd.read_sql_query("SELECT section_name, step_code, description, user_notes, status FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
        steps_df['user_notes'] = steps_df['user_notes'].fillna('')
        
        c1, c2, c3 = st.columns(3)
        # Excel
        out_ex = BytesIO()
        with pd.ExcelWriter(out_ex, engine='xlsxwriter') as wr: steps_df.to_excel(wr, index=False)
        c1.download_button("📊 Planilla Excel", data=out_ex.getvalue(), file_name=f"Audit_{client_name}.xlsx")
        # Word y PDF
        c2.download_button("📝 Informe Word", data=crear_word(steps_df, client_name), file_name=f"Audit_{client_name}.docx")
        c3.download_button("📕 Informe PDF", data=crear_pdf(steps_df, client_name), file_name=f"Audit_{client_name}.pdf")

    # Listado de pasos con Gestión de Archivos
    steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    for seccion in steps_db['section_name'].unique():
        with st.expander(f"📁 {seccion}", expanded=True):
            pasos = steps_db[steps_db['section_name'] == seccion]
            for _, row in pasos.iterrows():
                sid = row['id']
                st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                
                c_det, c_est, c_file = st.columns([3, 1, 1.5])
                with c_det:
                    notas = st.text_area("Desarrollo", value=row['user_notes'] or "", key=f"n_{sid}", height=80)
                    if st.button("💾 Guardar", key=f"s_{sid}"):
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid)); conn.commit(); st.toast("Guardado")
                
                with c_est:
                    nuevo = st.selectbox("Estado:", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                    if nuevo != row['status']:
                        conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid)); conn.commit(); st.rerun()
                
                with c_file:
                    # GESTIÓN DE ARCHIVOS (Subir y Ver)
                    up = st.file_uploader("Adjuntar", key=f"up_{sid}", label_visibility="collapsed")
                    if up:
                        conn.execute("INSERT INTO step_files (step_id, file_name, file_data) VALUES (?,?,?)", (sid, up.name, up.read()))
                        conn.commit(); st.success("Cargado"); st.rerun()
                    
                    # Mostrar archivos existentes
                    archivos = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                    for fid, fname, fdata in archivos:
                        st.markdown(f"<div class='file-box'>📎 {fname}</div>", unsafe_allow_html=True)
                        st.download_button("📥", data=fdata, file_name=fname, key=f"dl_{fid}", help="Descargar archivo")
    conn.close()

# --- VISTAS RESTANTES (Se mantienen igual para conservar funcionalidad) ---
def seccion_materialidad(client_id):
    st.subheader("📊 Cálculo de Materialidad (NIA 320)")
    conn = get_db_connection()
    mat_data = conn.execute("SELECT benchmark_value, percentage, planned_materiality FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        base = col1.number_input("Base (Ingresos/Activos)", value=mat_data[0] if mat_data else 0.0)
        porc = col2.slider("% NIA", 0.5, 5.0, mat_data[1] if mat_data else 1.0)
        res = base * (porc / 100)
        col3.metric("Materialidad", f"${res:,.2f}")
        if st.button("Actualizar Materialidad"):
            conn.execute("REPLACE INTO materiality (client_id, benchmark_value, percentage, planned_materiality) VALUES ((SELECT id FROM materiality WHERE client_id=?),?,?,?)", (client_id, base, porc, res))
            conn.commit()
    conn.close()

# (Aquí iría el resto de las funciones vista_login, vista_principal e inicializar_programa_auditoria que ya posees)
# ... [El código de login y dashboard se mantiene idéntico al anterior]
