import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from fpdf import FPDF
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro Elite - NIA 700 Edition", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .step-header { color: #1e40af; font-weight: bold; font-size: 16px; margin-top: 15px; border-bottom: 2px solid #cbd5e1; }
    .instruction-box { 
        background-color: #eff6ff; 
        border-left: 5px solid #3b82f6; 
        padding: 12px; border-radius: 6px; font-size: 13px; color: #1e3a8a; margin: 10px 0;
    }
    .report-preview {
        background-color: white; padding: 40px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        font-family: 'Times New Roman', serif; line-height: 1.6; color: #1a202c;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Pendiente", updated_at TIMESTAMP, updated_by TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB, file_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, benchmark TEXT, benchmark_value REAL, percentage REAL, planned_materiality REAL, performance_materiality REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, user_name TEXT, action TEXT, timestamp TIMESTAMP)')
    conn.commit()
    conn.close()

def log_action(client_id, action):
    conn = get_db_connection()
    conn.execute("INSERT INTO audit_log (client_id, user_name, action, timestamp) VALUES (?,?,?,?)", (client_id, st.session_state.user_name, action, datetime.now()))
    conn.commit()
    conn.close()

init_db()

# --- MOTOR DE REPORTES (NIA 700) ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'INFORME DE AUDITORÍA INDEPENDIENTE', 0, 1, 'C')
        self.ln(5)

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 11)
        self.cell(0, 10, label, 0, 1, 'L')
        self.ln(2)

    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, body)
        self.ln()

def generar_pdf_nia(client_name, nit, opinion_type, hallazgos, auditor):
    pdf = PDFReport()
    pdf.add_page()
    
    pdf.chapter_title("A los Accionistas de " + client_name)
    pdf.chapter_body(f"Identificación fiscal (NIT): {nit}")
    
    pdf.chapter_title("Opinión")
    opinion_text = {
        "Limpia": "En nuestra opinión, los estados financieros adjuntos presentan razonablemente, en todos los aspectos materiales, la situación financiera...",
        "Con Salvedades": "En nuestra opinión, excepto por los efectos del hecho descrito en la sección de Fundamento de la Opinión con Salvedades...",
        "Adversa": "Debido a la significatividad de la cuestión descrita, los estados financieros no presentan razonablemente..."
    }
    pdf.chapter_body(opinion_text.get(opinion_type))

    pdf.chapter_title("Fundamento de la Opinión")
    pdf.chapter_body("Hemos llevado a cabo nuestra auditoría de conformidad con las Normas Internacionales de Auditoría (NIA). Nuestras responsabilidades se describen más adelante en la sección Responsabilidades del Auditor.")
    
    if hallazgos:
        pdf.chapter_title("Hallazgos Clave Identificados")
        pdf.chapter_body(hallazgos)

    pdf.ln(20)
    pdf.cell(0, 10, "_"*40, 0, 1, 'L')
    pdf.cell(0, 10, f"Firma: {auditor}", 0, 1, 'L')
    pdf.cell(0, 10, f"Fecha de emisión: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
    
    return pdf.output(dest='S').encode('latin-1')

# --- INTERFAZ DE USUARIO ---
def vista_papeles_trabajo(client_id, client_name):
    st.title(f"📂 Gestión de Auditoría: {client_name}")
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Papeles", "📏 Materialidad", "📜 Log", "📄 Informe Final"])

    conn = get_db_connection()
    client_data = conn.execute("SELECT client_nit FROM clients WHERE id=?", (client_id,)).fetchone()

    with tab1:
        steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
        for _, row in steps.iterrows():
            with st.container():
                st.markdown(f"<div class='step-header'>{row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                c1, c2 = st.columns([3, 1])
                with c1:
                    notas = st.text_area("Evidencia/Notas", value=row['user_notes'] or "", key=f"n_{row['id']}")
                    if st.button("Guardar", key=f"b_{row['id']}"):
                        conn.execute("UPDATE audit_steps SET user_notes=?, updated_at=?, updated_by=? WHERE id=?", (notas, datetime.now(), st.session_state.user_name, row['id']))
                        conn.commit()
                        st.toast("Guardado")
                with c2:
                    st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"s_{row['id']}")
                    up = st.file_uploader("Subir", key=f"u_{row['id']}")

    with tab4:
        st.subheader("🏛️ Generación de Dictamen (NIA 700)")
        col_inf1, col_inf2 = st.columns([1, 2])
        
        with col_inf1:
            opinion = st.radio("Tipo de Opinión", ["Limpia", "Con Salvedades", "Adversa"])
            incluir_hallazgos = st.checkbox("Incluir notas de ejecución en el informe", value=True)
            
            # Recopilar notas si se solicita
            hallazgos_text = ""
            if incluir_hallazgos:
                notas_ejecucion = pd.read_sql_query("SELECT description, user_notes FROM audit_steps WHERE client_id=? AND user_notes IS NOT NULL", conn, params=(client_id,))
                for _, n in notas_ejecucion.iterrows():
                    hallazgos_text += f"- {n['description']}: {n['user_notes']}\n"

            if st.button("🚀 Generar Reporte Final"):
                pdf_bytes = generar_pdf_nia(client_name, client_data[0], opinion, hallazgos_text, st.session_state.user_name)
                st.download_button("📥 Descargar PDF", data=pdf_bytes, file_name=f"Informe_{client_name}.pdf", mime="application/pdf")

        with col_inf2:
            st.markdown("**Vista Previa del Contenido:**")
            st.markdown(f"""
            <div class='report-preview'>
                <h4>INFORME DE AUDITORÍA INDEPENDIENTE</h4>
                <p>A los Accionistas de <b>{client_name}</b></p>
                <p><b>Opinión:</b><br> {opinion}: Presentamos los resultados obtenidos...</p>
                <hr>
                <p><b>Hallazgos detectados:</b><br>{hallazgos_text if hallazgos_text else "Sin hallazgos significativos documentados."}</p>
            </div>
            """, unsafe_allow_html=True)

    if st.button("⬅️ Volver"):
        del st.session_state.active_id
        st.rerun()
    conn.close()

# --- LOGIN Y PRINCIPAL (Consolidado) ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def vista_principal():
    with st.sidebar:
        st.title("🛡️ AuditPro v2.5")
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Salir"):
            del st.session_state.user_id
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Cliente")
        n = st.text_input("Nombre")
        nit = st.text_input("NIT")
        if st.button("Crear"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, tipo_trabajo) VALUES (?,?,?,'Auditoría Financiera')", (st.session_state.user_id, n, nit))
            cid = cur.lastrowid
            template = [("100", "101", "Aceptación", "NIA 210"), ("200", "201", "Planeación", "NIA 300"), ("300", "301", "Ejecución", "NIA 500")]
            for s, c, d, i in template:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, s, c, d, i))
            conn.commit()
            st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Panel de Control")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Abrir", key=f"o_{r['id']}"):
                    st.session_state.active_id = r['id']
                    st.session_state.active_name = r['client_name']
                    st.rerun()
        conn.close()

def vista_login():
    st.title("⚖️ Ingreso al Sistema")
    e = st.text_input("Email")
    p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        if u:
            st.session_state.user_id, st.session_state.user_name = u[0], u[1]
            st.rerun()
        else: st.error("Error")
    if st.button("Crear cuenta"): # Registro rápido para pruebas
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, "Auditor Senior", hash_pass(p)))
        conn.commit()
        st.info("Usuario creado (si no existía). Intenta entrar.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
