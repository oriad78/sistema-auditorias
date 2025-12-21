import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Papeles de Trabajo", layout="wide")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 16px; margin-top: 10px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS Y ESTRUCTURA ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE, full_name TEXT, password_hash TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        client_name TEXT, client_nit TEXT, audit_year INTEGER,
        tipo_encargo TEXT, estado TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER,
        section_name TEXT, step_code TEXT, description TEXT, 
        instructions TEXT, user_notes TEXT, status TEXT DEFAULT 'Pendiente',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS step_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER,
        file_name TEXT, file_data BLOB, file_type TEXT)''')
    conn.commit()
    conn.close()

create_tables()

# --- TEMPLATE DE AUDITORÍA (NIA - TUS IMÁGENES) ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente, incorporar el resumen y actualizar en función de los acontecimientos.", "Instrucciones: Revise la integridad de la gerencia. Sub-fase: A Other Required steps."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP (Quality Review Partner).", "Instrucciones: Evaluar si es entidad de interés público o alto riesgo."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Considerar el cumplimiento de requisitos éticos, las amenazas a la independencia y las protecciones relacionadas, y preparar/aprobar el resumen.", "Instrucciones: Completar confirmaciones de independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia.", "Instrucciones: Revisar servicios no auditoría prestados."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Asegurarse de que la carta de contratación esté actualizada, firmada por el cliente y modificarla si cambian los términos del trabajo.", "Instrucciones: Adjuntar Carta de Encargo vigente."),
    ("100 - Aceptación y continuación de clientes", "1200", "(ISA 600) Considerar el alcance de la participación en la auditoría del grupo.", "Instrucciones: Sub-fase: B Multilocation audit."),
    ("100 - Aceptación y continuación de clientes", "3000", "Revisar la necesidad de rotación de los miembros del equipo de trabajo.", "Instrucciones: Cumplimiento de normas de rotación."),
    ("100 - Aceptación y continuación de clientes", "4100", "Confirmación de independencia individual (Communications file).", "Instrucciones: Firma de todo el equipo."),
    ("100 - Aceptación y continuación de clientes", "4200", "Confirmación de independencia de una oficina PwC del exterior.", "Instrucciones: Solo auditoría de grupo."),
    ("100 - Aceptación y continuación de clientes", "6000", "(ISA 510) Contactarse con los auditores anteriores.", "Instrucciones: Comunicación con auditor predecesor."),
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo.", "Instrucciones: Asignación de recursos."),
    ("150 - Administración del proyecto", "3000", "(ISA 300) Preparar y monitorear el avance con relación al plan del proyecto.", "Instrucciones: Control de ejecución."),
    ("150 - Administración del proyecto", "2000", "Discutir y acordar objetivos de desarrollo personal para todos los miembros del equipo.", "Instrucciones: Reunión de inicio."),
    ("1100 - Comprensión del cliente y de la industria", "1000", "(ISA 315) Obtener o actualizar la comprensión del cliente y el ambiente en el que opera.", "Instrucciones: Entendimiento del negocio."),
    ("1100 - Comprensión del cliente y de la industria", "1500", "(ISA 315, ISA 520) Realizar procedimientos de revisión analítica preliminares.", "Instrucciones: Variaciones significativas."),
    ("1100 - Comprensión del cliente y de la industria", "3000", "Revisar las actas de reuniones y asambleas y obtener y revisar los nuevos contratos y acuerdos significativos.", "Instrucciones: Resumen de actas."),
    ("1100 - Comprensión del cliente y de la industria", "1750", "Prepararse para y realizar la reunión de tipo 'demostrativo' con el directorio.", "Instrucciones: Reunión con Gobierno Corporativo."),
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, ISA 315) Evaluar y responder al riesgo de fraude.", "Instrucciones: Triángulo del fraude."),
    ("1700 - Evaluación del riesgo/significatividad", "2000", "(ISA 250, ISA 315) Obtener una comprensión general de las leyes y reglamentaciones.", "Instrucciones: Matriz legal.")
]

# --- FUNCIONES DE APOYO ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def inicializar_programa_auditoria(client_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM audit_steps WHERE client_id = ?", (client_id,))
    for seccion, codigo, desc, instr in TEMPLATE_AUDITORIA:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)",
                     (client_id, seccion, codigo, desc, instr))
    conn.commit()
    conn.close()

def generar_pdf(df, auditor):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16); pdf.cell(190, 10, "REPORTE DE ENCARGOS", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10); pdf.cell(190, 10, f"Auditor: {auditor}", ln=True, align='C'); pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 9)
    for col, w in zip(["Cliente", "NIT", "Año", "Estado"], [70, 40, 30, 40]): pdf.cell(w, 10, col, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Helvetica", '', 8)
    for _, row in df.iterrows():
        est = str(row['Estado']).replace("🔴 ", "").replace("🟡 ", "").replace("🟢 ", "")
        pdf.cell(70, 10, str(row['Cliente'])[:35], 1); pdf.cell(40, 10, str(row['NIT']), 1)
        pdf.cell(30, 10, str(row['Año']), 1); pdf.cell(40, 10, est, 1); pdf.ln()
    return bytes(pdf.output())

# --- VISTAS ---def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    
    with t1:
        # Usamos un contenedor para inyectar un pequeño truco de autocompletado
        with st.form("login_form", clear_on_submit=False):
            st.markdown("### Bienvenido de nuevo")
            
            # El parámetro 'autocomplete' ayuda al navegador a recordar el correo
            email = st.text_input(
                "Correo electrónico", 
                key="l_user", 
                help="El navegador recordará los correos ingresados previamente",
                autocomplete="email" 
            )
            
            password = st.text_input(
                "Contraseña", 
                type="password", 
                key="l_pass",
                autocomplete="current-password"
            )
            
            submit = st.form_submit_button("Ingresar")
            
            if submit:
                if not email or not password:
                    st.warning("Por favor complete todos los campos")
                else:
                    conn = get_db_connection()
                    u = conn.execute(
                        "SELECT id, full_name FROM users WHERE email=? AND password_hash=?", 
                        (email, hash_pass(password))
                    ).fetchone()
                    conn.close()
                    
                    if u:
                        st.session_state.user_id = u[0]
                        st.session_state.user_name = u[1]
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas")
    
    with t2:
        # (El código de registro se mantiene igual con el campo de confirmación)
        n = st.text_input("Nombre Completo")
        em = st.text_input("Correo Institucional", autocomplete="email")
        ps = st.text_input("Contraseña", type="password", autocomplete="new-password")
        ps_c = st.text_input("Confirmar Contraseña", type="password")
        
        if st.button("Crear mi cuenta"):
            if ps != ps_c: 
                st.error("Las contraseñas no coinciden")
            elif len(ps) < 4: 
                st.error("La clave debe tener al menos 4 caracteres")
            else:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", 
                                 (em, n, hash_pass(ps)))
                    conn.commit()
                    conn.close()
                    st.success("¡Registro exitoso! Ya puedes iniciar sesión en la pestaña de al lado.")
                except:
                    st.error("Este correo ya se encuentra registrado")

def vista_papeles_trabajo(client_id, client_name):
    st.markdown(f"## 📂 Expediente Digital: {client_name}")
    if st.button("⬅️ Volver a Encargos"): del st.session_state['active_id']; st.rerun()
    
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id = ? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    if steps.empty:
        if st.button("🔄 Cargar Programa NIA"): inicializar_programa_auditoria(client_id); st.rerun()
    else:
        for seccion in steps['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                for _, row in steps[steps['section_name'] == seccion].iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        with st.expander("📘 Guía Metodológica"): st.info(row['instructions'])
                        notas = st.text_area("Desarrollo / Hallazgos", value=row['user_notes'] if row['user_notes'] else "", key=f"n_{sid}", height=100)
                        if st.button("💾 Guardar", key=f"s_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid)); conn.commit(); st.toast("Guardado")
                    with c2:
                        nuevo_est = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo_est != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo_est, sid)); conn.commit(); st.rerun()
                        up_file = st.file_uploader("Adjuntar", key=f"f_{sid}")
                        if up_file:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data, file_type) VALUES (?,?,?,?)", (sid, up_file.name, up_file.read(), up_file.type))
                            conn.commit(); st.rerun()
                        files = pd.read_sql_query("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", conn, params=(sid,))
                        for _, f in files.iterrows(): st.download_button(f"⬇️ {f['file_name']}", f['file_data'], f['file_name'], key=f"d_{f['id']}")
    conn.close()

def vista_principal():
    with st.sidebar:
        st.title(f"👨‍💼 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        c_n = st.text_input("Empresa"); c_t = st.text_input("NIT")
        
        # LINKS REINCORPORADOS
        st.caption("Consultas Oficiales:")
        col1, col2 = st.columns(2)
        col1.markdown("[🔍 RUES](https://www.rues.org.co/busqueda-avanzada)")
        col2.markdown("[🔍 DIAN](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces)")
        
        c_y = st.number_input("Año", value=2025); c_tp = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa"])
        if st.button("💾 Crear"):
            if c_n and c_t:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit, audit_year, tipo_encargo, estado) VALUES (?,?,?,?,?,?)", (st.session_state.user_id, c_n, c_t, c_y, c_tp, "🔴 Pendiente"))
                cid = cur.lastrowid; conn.commit(); conn.close()
                inicializar_programa_auditoria(cid); st.success("Creado"); st.rerun()
    
    if 'active_id' in st.session_state: vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/9334/9334544.png", width=80) 
        st.title("💼 Encargos de Auditoría")
        q = st.text_input("🔍 Buscar por NIT o Nombre")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name as Cliente, client_nit as NIT, audit_year as Año, estado as Estado FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        conn.close()
        if q: df = df[df['Cliente'].str.contains(q, case=False) | df['NIT'].str.contains(q, case=False)]
        
        if not df.empty:
            c_a, c_b = st.columns(2)
            c_a.download_button("📊 Excel", df.to_csv(index=False).encode('utf-8'), "encargos.csv")
            c_b.download_button("📕 PDF", generar_pdf(df, st.session_state.user_name), "reporte.pdf")
            for _, r in df.iterrows():
                with st.container():
                    cols = st.columns([3, 2, 2, 2])
                    cols[0].write(f"**{r['Cliente']}**"); cols[1].write(f"NIT: {r['NIT']}")
                    cols[2].write(f"{r['Estado']}")
                    if cols[3].button("📂 Abrir", key=f"btn_{r['id']}"):
                        st.session_state.active_id, st.session_state.active_name = r['id'], r['Cliente']; st.rerun()
                    st.divider()
        else: st.info("No hay encargos registrados.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()

