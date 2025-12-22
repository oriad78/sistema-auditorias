import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Papeles de Trabajo", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, audit_year INTEGER, tipo_encargo TEXT, estado TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT 'Pendiente', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS step_files (id INTEGER PRIMARY KEY AUTOINCREMENT, step_id INTEGER, file_name TEXT, file_data BLOB, file_type TEXT)''')
    conn.commit()
    conn.close()

create_tables()

# --- PLANTILLA MAESTRA INTEGRAL (Basada en tus imágenes) ---
TEMPLATE_AUDITORIA = [
    # SECCIÓN 100
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente, incorporar el resumen y actualizar en función de los acontecimientos.", "Instrucciones: Revise la integridad de la gerencia. Sub-fase: A Other Required steps."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP (Quality Review Partner).", "Instrucciones: Evaluar si es entidad de interés público o alto riesgo."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Considerar el cumplimiento de requisitos éticos, las amenazas a la independencia y las protecciones relacionadas.", "Instrucciones: Completar confirmaciones de independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia.", "Instrucciones: Revisar servicios no auditoría prestados."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Asegurarse de que la carta de contratación esté actualizada y firmada.", "Instrucciones: Adjuntar Carta de Encargo vigente."),
    ("100 - Aceptación y continuación de clientes", "1200", "(ISA 600) Considerar el alcance de la participación en la auditoría del grupo.", "Instrucciones: Sub-fase: B Multilocation audit."),
    
    # SECCIÓN 150
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo.", "Instrucciones: Asignación de recursos."),
    ("150 - Administración del proyecto", "3000", "(ISA 300) Preparar y monitorear el avance con relación al plan del proyecto.", "Instrucciones: Control de ejecución."),
    ("150 - Administración del proyecto", "2000", "Discutir y acordar objetivos de desarrollo personal para todos los miembros del equipo.", "Instrucciones: Reunión de inicio."),

    # SECCIÓN 1100
    ("1100 - Comprensión del cliente y de la industria", "1000", "(ISA 315) Obtener o actualizar la comprensión del cliente y el ambiente en el que opera.", "Instrucciones: Entendimiento del negocio."),
    ("1100 - Comprensión del cliente y de la industria", "1500", "(ISA 315, ISA 520) Realizar procedimientos de revisión analítica preliminares.", "Instrucciones: Variaciones significativas."),
    ("1100 - Comprensión del cliente y de la industria", "3000", "Revisar las actas de reuniones y asambleas y obtener y revisar los nuevos contratos.", "Instrucciones: Resumen de actas."),

    # SECCIONES NUEVAS (Imagen 2)
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, ISA 315) Evaluar y responder al riesgo de fraude.", "Instrucciones: Triángulo del fraude."),
    ("1300 - Identificar las unidades de administración", "1000", "Identificar las unidades de administración, incluyendo aquellas que requieren apoyo de auditoría.", "Instrucciones: Identificación de localidades."),
    ("1700 - Evaluación del riesgo/significatividad", "2000", "(ISA 250, ISA 315) Obtener una comprensión general de las leyes y reglamentaciones.", "Instrucciones: Matriz legal.")
]

# --- FUNCIONES LÓGICAS ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def inicializar_programa_auditoria(client_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM audit_steps WHERE client_id = ?", (client_id,))
    for seccion, codigo, desc, instr in TEMPLATE_AUDITORIA:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)", (client_id, seccion, codigo, desc, instr))
    conn.commit()
    conn.close()

def sincronizar_pasos_faltantes(client_id):
    conn = get_db_connection()
    existentes = [r[0] for r in conn.execute("SELECT step_code FROM audit_steps WHERE client_id = ?", (client_id,)).fetchall()]
    agregados = 0
    for seccion, codigo, desc, instr in TEMPLATE_AUDITORIA:
        if codigo not in existentes:
            conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)", (client_id, seccion, codigo, desc, instr))
            agregados += 1
    conn.commit()
    conn.close()
    return agregados

# --- VISTAS ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    with t1:
        if 'modo_recuperar' not in st.session_state:
            with st.form("login_form"):
                e = st.text_input("Correo electrónico", key="l_user", autocomplete="email")
                p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Ingresar"):
                    conn = get_db_connection()
                    u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
                    conn.close()
                    if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
                    else: st.error("Datos incorrectos")
            if st.button("¿Olvidó su contraseña?"): st.session_state.modo_recuperar = True; st.rerun()
        else:
            with st.form("rec_form"):
                st.info("### Recuperar Contraseña")
                re = st.text_input("Correo registrado")
                rn = st.text_input("Nombre completo")
                np = st.text_input("Nueva Contraseña", type="password")
                if st.form_submit_button("Resetear"):
                    conn = get_db_connection()
                    user = conn.execute("SELECT id FROM users WHERE email=? AND full_name=?", (re, rn)).fetchone()
                    if user:
                        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pass(np), user[0]))
                        conn.commit(); conn.close(); st.success("Éxito"); del st.session_state.modo_recuperar; st.rerun()
                    else: st.error("Datos no coinciden"); conn.close()
            if st.button("Volver"): del st.session_state.modo_recuperar; st.rerun()

def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    c_data = conn.execute("SELECT client_name, client_nit, audit_year, tipo_encargo, estado FROM clients WHERE id=?", (client_id,)).fetchone()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    c1, c2, c3 = st.columns([2,2,4])
    if c1.button("⬅️ Volver"): del st.session_state.active_id; conn.close(); st.rerun()
    editar = c2.toggle("⚙️ Configurar Encargo")

    if editar:
        col_iz, col_de = st.columns([2,1])
        with col_iz:
            with st.container(border=True):
                st.subheader("📝 Datos e Independencia")
                n_n = st.text_input("Empresa", value=c_data[0])
                n_t = st.text_input("NIT", value=c_data[1])
                if st.button("Guardar Cambios"):
                    conn.execute("UPDATE clients SET client_name=?, client_nit=? WHERE id=?", (n_n, n_t, client_id))
                    conn.commit(); st.rerun()
                st.divider()
                if st.button("🔄 Sincronizar Pasos Faltantes (Incluye 4010)"):
                    num = sincronizar_pasos_faltantes(client_id)
                    st.success(f"Se agregaron {num} pasos."); st.rerun()
        with col_de:
            with st.container(border=True):
                st.subheader("⚠️ Peligro")
                if st.checkbox("Confirmar borrado"):
                    if st.button("🗑️ ELIMINAR ENCARGO"):
                        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                        conn.execute("DELETE FROM audit_steps WHERE client_id=?", (client_id,))
                        conn.commit(); conn.close(); del st.session_state.active_id; st.rerun()

    # --- VISTA AGRUPADA POR SECCIONES (Como solicitaste) ---
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    if steps.empty:
        if st.button("Cargar Programa"): inicializar_programa_auditoria(client_id); st.rerun()
    else:
        for seccion in steps['section_name'].unique():
            with st.expander(f"📁 {seccion}", expanded=True):
                for _, row in steps[steps['section_name'] == seccion].iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    col_info, col_status = st.columns([3, 1])
                    with col_info:
                        st.caption(f"**Guía:** {row['instructions']}")
                        notas = st.text_area("Hallazgos / Desarrollo", value=row['user_notes'] or "", key=f"nt_{sid}", height=100)
                        if st.button("💾 Guardar", key=f"sv_{sid}"):
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                            conn.commit(); st.toast("Guardado")
                    with col_status:
                        nuevo_est = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], 
                                               index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"est_{sid}")
                        if nuevo_est != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo_est, sid))
                            conn.commit(); st.rerun()
                        up_file = st.file_uploader("Adjuntar", key=f"up_{sid}")
                        if up_file:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data, file_type) VALUES (?,?,?,?)", 
                                         (sid, up_file.name, up_file.read(), up_file.type))
                            conn.commit(); st.rerun()
    conn.close()

def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"): del st.session_state.user_id; st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        cn = st.text_input("Empresa"); ct = st.text_input("NIT")
        st.markdown("[🔍 RUES](https://www.rues.org.co/) | [🔍 DIAN](https://muisca.dian.gov.co/)")
        if st.button("Crear"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit, estado) VALUES (?,?,?,?)", (st.session_state.user_id, cn, ct, "🔴 Pendiente"))
            cid = cur.lastrowid; conn.commit(); conn.close()
            inicializar_programa_auditoria(cid); st.rerun()

    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/9334/9334544.png", width=80)
        st.title("💼 Encargos de Auditoría")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        conn.close()
        for _, r in df.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4,1])
                c1.write(f"**{r['client_name']}**\nNIT: {r['client_nit']}")
                if c2.button("Abrir", key=f"op_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
