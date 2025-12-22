import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from fpdf import FPDF
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS (RESTAURADOS Y MEJORADOS) ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 10px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 15px; 
        margin-bottom: 10px; 
        border-radius: 5px;
        font-size: 14px;
        color: #0d47a1;
    }
    .report-preview {
        background-color: white; padding: 30px; border: 1px solid #ccc;
        font-family: 'Times New Roman', serif; line-height: 1.5;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS (MANTENIENDO TU ESTRUCTURA) ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente", updated_at TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB, file_hash TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS materiality 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                     benchmark TEXT, benchmark_value REAL, percentage REAL, planned_materiality REAL, performance_materiality REAL)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, user_name TEXT, action TEXT, timestamp TIMESTAMP)')
    conn.commit()
    conn.close()

create_tables()

# --- TU PLANTILLA MAESTRA ORIGINAL (CONSERVADA) ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación", "1000", "(ISA 220, 300) Evaluar la aceptación del cliente", "Revise la integridad de la gerencia, antecedentes penales y reputación en el mercado. Documente si existe algún conflicto de intereses."),
    ("100 - Aceptación y continuación", "2000", "(ISA 220) Designar un QRP (Quality Review Partner)", "Evaluar si la complejidad del encargo requiere un socio de revisión de calidad independiente para asegurar el cumplimiento normativo."),
    ("1100 - Administración", "1000", "(ISA 315) Entendimiento del cliente y su ambiente", "Realice un análisis del sector, marco regulatorio y naturaleza de la entidad. Incluya el sistema de información y control interno."),
    ("1100 - Administración", "5000", "(ISA 210) Carta de compromiso", "Asegúrese de que la carta de encargo esté firmada por el representante legal y cubra el alcance de la auditoría 2024-2025.")
]

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def log_action(client_id, action):
    conn = get_db_connection()
    conn.execute("INSERT INTO audit_log (client_id, user_name, action, timestamp) VALUES (?,?,?,?)", 
                 (client_id, st.session_state.user_name, action, datetime.now()))
    conn.commit()
    conn.close()

# --- MOTOR DE REPORTES (NIA 700) ---
def generar_pdf_final(client_name, nit, opinion, hallazgos, auditor):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 10, "INFORME DE AUDITORÍA INDEPENDIENTE", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(190, 10, f"A los Accionistas de {client_name}", ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(190, 7, f"Hemos auditado los estados financieros de la entidad con NIT {nit}...")
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(190, 10, "Opinión", ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(190, 7, f"En nuestra opinión, la cual calificamos como {opinion.upper()}, los estados financieros...")
    if hallazgos:
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(190, 10, "Fundamentos y Hallazgos", ln=True)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(190, 7, hallazgos)
    pdf.ln(20)
    pdf.cell(190, 10, f"Firma: {auditor}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- VISTA PAPELES DE TRABAJO (TUS FUNCIONES + MEJORAS) ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Papeles de Trabajo", "📊 Materialidad (NIA 320)", "📄 Informe Final (NIA 700)", "📜 Pista de Auditoría"])

    with tab1:
        if st.button("⬅️ Volver al Panel"):
            del st.session_state.active_id
            st.rerun()

        steps_db = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
        cols_l = {"Pendiente": "🔴", "En Proceso": "🟡", "Cerrado": "🟢"}
        
        for seccion in steps_db['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos = steps_db[steps_db['section_name'] == seccion]
                for _, row in pasos.iterrows():
                    sid = row['id']
                    # TU ENCABEZADO ORIGINAL
                    st.markdown(f"<div class='step-header'>{cols_l.get(row['status'], '⚪')} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    
                    # TU BLOQUE DE INSTRUCCIÓN / GUÍA (RESTAURADO)
                    if row['instructions']:
                        st.markdown(f"<div class='instruction-box'><strong>💡 Guía de Auditoría:</strong><br>{row['instructions']}</div>", unsafe_allow_html=True)
                    
                    c_det, c_est, c_file = st.columns([3, 1, 1.5])
                    with c_det:
                        notas = st.text_area("Desarrollo de la Auditoría", value=row['user_notes'] or "", key=f"n_{sid}", height=150)
                        if st.button("💾 Guardar Notas", key=f"s_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=?, updated_at=? WHERE id=?", (notas, datetime.now(), sid))
                            conn.commit()
                            log_action(client_id, f"Guardó notas en paso {row['step_code']}")
                            st.toast("Notas guardadas")

                    with c_est:
                        nuevo = st.selectbox("Cambiar Estado:", ["Pendiente", "En Proceso", "Cerrado"], 
                                           index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo, sid))
                            conn.commit()
                            log_action(client_id, f"Cambió estado a {nuevo} en {row['step_code']}")
                            st.rerun()

                    with c_file:
                        up = st.file_uploader("Adjuntar Evidencia", key=f"up_{sid}")
                        if up:
                            data = up.read()
                            f_hash = hashlib.sha256(data).hexdigest()
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data, file_hash) VALUES (?,?,?,?)", (sid, up.name, data, f_hash))
                            conn.commit()
                            log_action(client_id, f"Subió archivo {up.name}")
                            st.rerun()
                        
                        archivos = conn.execute("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", (sid,)).fetchall()
                        for fid, fname, fdata in archivos:
                            col_n, col_d, col_dl = st.columns([3, 1, 1])
                            col_n.caption(f"📄 {fname[:10]}")
                            if col_d.button("🗑️", key=f"del_{fid}"):
                                conn.execute("DELETE FROM step_files WHERE id=?", (fid,))
                                conn.commit()
                                st.rerun()
                            col_dl.download_button("📥", data=fdata, file_name=fname, key=f"dl_{fid}")

    with tab2:
        st.subheader("Cálculo de Importancia Relativa")
        col1, col2 = st.columns(2)
        with col1:
            benchmark = st.selectbox("Base (Benchmark)", ["Activos", "Ingresos", "Utilidad"], key="bm")
            v_base = st.number_input("Valor Base ($)", min_value=0.0)
        with col2:
            p_mat = st.slider("Materialidad (%)", 0.5, 5.0, 1.0)
            mat_p = v_base * (p_mat / 100)
            st.metric("Materialidad Planeada", f"${mat_p:,.2f}")
            if st.button("Guardar Estrategia"):
                conn.execute("INSERT INTO materiality (client_id, benchmark, benchmark_value, percentage, planned_materiality) VALUES (?,?,?,?,?)", 
                             (client_id, benchmark, v_base, p_mat, mat_p))
                conn.commit()
                st.success("Estrategia NIA 320 guardada")

    with tab3:
        st.subheader("Dictamen de Auditoría")
        op = st.radio("Tipo de Opinión", ["Limpia", "Con Salvedades", "Adversa"])
        incluir = st.checkbox("Extraer hallazgos automáticamente", value=True)
        h_texto = ""
        if incluir:
            resumen = pd.read_sql_query("SELECT step_code, user_notes FROM audit_steps WHERE client_id=? AND user_notes IS NOT NULL", conn, params=(client_id,))
            for _, r in resumen.iterrows(): h_texto += f"Paso {r['step_code']}: {r['user_notes']}\n"
        
        if st.button("🚀 Generar y Descargar PDF"):
            nit_c = conn.execute("SELECT client_nit FROM clients WHERE id=?", (client_id,)).fetchone()[0]
            pdf_bytes = generar_pdf_final(client_name, nit_c, op, h_texto, st.session_state.user_name)
            st.download_button("📥 Click para descargar PDF", data=pdf_bytes, file_name=f"Informe_{client_name}.pdf")

    with tab4:
        st.subheader("Pista de Auditoría (Trazabilidad NIA 230)")
        logs = pd.read_sql_query("SELECT timestamp, user_name, action FROM audit_log WHERE client_id=? ORDER BY timestamp DESC", conn, params=(client_id,))
        st.dataframe(logs, use_container_width=True)

    conn.close()

# --- VISTA PRINCIPAL (TU LÓGICA CONSERVADA) ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"):
            del st.session_state.user_id
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa")
        ct = st.text_input("NIT")
        tipo = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa", "Otros"])
        if st.button("Crear"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo) VALUES (?,?,?,?)", (st.session_state.user_id, cn, ct, tipo))
            cid = cur.lastrowid
            # TU TEMPLATE ORIGINAL SE INSERTA AQUÍ
            for sec, cod, desc, ins in TEMPLATE_AUDITORIA:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
            conn.commit()
            log_action(cid, "Creación de expediente")
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
                    st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                    st.rerun()
                else: st.error("Acceso incorrecto")
    with t2:
        with st.form("reg"):
            ne, nn, np = st.text_input("Email"), st.text_input("Nombre"), st.text_input("Clave", type="password")
            if st.form_submit_button("Registrar"):
                conn = get_db_connection()
                conn.execute("INSERT OR IGNORE INTO users (email, full_name, password_hash) VALUES (?,?,?)", (ne, nn, hash_pass(np)))
                conn.commit()
                st.success("Registrado.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
