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
    /* Ajuste para que el navegador reconozca campos de login */
    input[type="text"], input[type="password"] { border-radius: 5px; }
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

# --- TEMPLATE DE AUDITORÍA (NIA) ---
TEMPLATE_AUDITORIA = [
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente, incorporar el resumen y actualizar en función de los acontecimientos.", "Instrucciones: Revise la integridad de la gerencia."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP (Quality Review Partner).", "Instrucciones: Evaluar si es entidad de interés público."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Considerar el cumplimiento de requisitos éticos e independencia. , las amenazas a la independencia y las protecciones relacionadas, y preparar/aprobar el resumen.", "Instrucciones: Completar confirmaciones de independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia.", "Instrucciones: Revisar servicios no auditoría."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Asegurarse de que la carta de contratación esté actualizada y firmada.", "Instrucciones: Adjuntar Carta de Encargo."),
    ("100 - Aceptación y continuación de clientes", "1200", "(ISA 600) Considerar el alcance de la participación en la auditoría del grupo.", "Instrucciones: Multilocation audit."),
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo.", "Instrucciones: Asignación de recursos."),
    ("1100 - Comprensión del cliente y de la industria", "1000", "(ISA 315) Obtener o actualizar la comprensión del cliente.", "Instrucciones: Entendimiento del negocio."),
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, ISA 315) Evaluar y responder al riesgo de fraude.", "Instrucciones: Triángulo del fraude.")
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

# --- VISTA: LOGIN (CON RECORDATORIO DE CORREO) ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    
    with t1:
        # Lógica de Inicio de Sesión Normal
        if 'recuperando' not in st.session_state:
            with st.form("login_form"):
                st.write("### Bienvenido de nuevo")
                e = st.text_input("Correo electrónico", key="login_email", autocomplete="email")
                p = st.text_input("Contraseña", type="password", key="login_password", autocomplete="current-password")
                submitted = st.form_submit_button("Ingresar")
                
                if submitted:
                    conn = get_db_connection()
                    u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", 
                                   (e, hash_pass(p))).fetchone()
                    conn.close()
                    if u:
                        st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas")
            
            # Botón para activar modo recuperación
            if st.button("¿Olvidó su contraseña?"):
                st.session_state.recuperando = True
                st.rerun()

        # LÓGICA DE RECUPERACIÓN (Aparece si presionan el botón)
        else:
            st.warning("### Recuperar acceso")
            st.write("Para validar su identidad, ingrese su correo y nombre completo de registro.")
            
            with st.form("recovery_form"):
                r_email = st.text_input("Correo electrónico")
                r_name = st.text_input("Nombre Completo (como se registró)")
                new_p = st.text_input("Nueva Contraseña", type="password")
                confirm_p = st.text_input("Confirmar Nueva Contraseña", type="password")
                
                col_rec1, col_rec2 = st.columns(2)
                with col_rec1:
                    btn_rec = st.form_submit_button("Actualizar Contraseña")
                with col_rec2:
                    if st.form_submit_button("Cancelar"):
                        del st.session_state.recuperando
                        st.rerun()

                if btn_rec:
                    if new_p != confirm_p:
                        st.error("Las nuevas contraseñas no coinciden")
                    elif len(new_p) < 4:
                        st.error("La clave debe ser de al menos 4 caracteres")
                    else:
                        conn = get_db_connection()
                        # Validamos que el correo y el nombre coincidan en la base de datos
                        user = conn.execute("SELECT id FROM users WHERE email=? AND full_name=?", 
                                          (r_email, r_name)).fetchone()
                        
                        if user:
                            conn.execute("UPDATE users SET password_hash=? WHERE id=?", 
                                       (hash_pass(new_p), user[0]))
                            conn.commit()
                            conn.close()
                            st.success("✅ Contraseña actualizada correctamente. Ya puede ingresar.")
                            del st.session_state.recuperando
                            # Pequeña pausa para que vean el éxito antes de recargar
                        else:
                            conn.close()
                            st.error("❌ Los datos no coinciden con nuestros registros.")
    
    with t2:
        # El código de registro permanece igual...
        with st.form("register_form"):
            n = st.text_input("Nombre Completo")
            em = st.text_input("Correo Institucional", autocomplete="email")
            ps = st.text_input("Contraseña", type="password", autocomplete="new-password")
            ps_c = st.text_input("Confirmar Contraseña", type="password")
            reg_submitted = st.form_submit_button("Crear mi cuenta")
            
            if reg_submitted:
                if ps != ps_c: st.error("Las contraseñas no coinciden")
                elif len(ps) < 4: st.error("Clave muy corta")
                else:
                    try:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", 
                                     (em, n, hash_pass(ps)))
                        conn.commit(); conn.close()
                        st.success("¡Registro exitoso! Ya puede iniciar sesión.")
                    except: st.error("El correo ya existe")

# --- VISTA: PAPELES DE TRABAJO ---
def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    # Obtenemos los datos actualizados del cliente
    c_data = conn.execute("SELECT client_name, client_nit, audit_year, tipo_encargo, estado FROM clients WHERE id = ?", (client_id,)).fetchone()
    
    st.markdown(f"## 📂 Expediente Digital: {client_name}")
    
    # --- BARRA DE ACCIONES SUPERIOR ---
    col_nav1, col_nav2, col_nav3 = st.columns([2, 2, 4])
    with col_nav1:
        if st.button("⬅️ Volver a Encargos"):
            if 'active_id' in st.session_state: del st.session_state['active_id']
            conn.close() # Cerramos antes de salir
            st.rerun()
    with col_nav2:
        editar = st.toggle("⚙️ Configurar Encargo")

    # --- PANEL DE CONFIGURACIÓN Y ELIMINACIÓN ---
    if editar:
        st.markdown("---")
        col_ed_izq, col_ed_der = st.columns([2, 1])
        
        with col_ed_izq:
            st.subheader("📝 Editar Datos Generales")
            with st.container(border=True):
                new_n = st.text_input("Nombre de la Empresa", value=c_data[0])
                new_t = st.text_input("NIT", value=c_data[1])
                col_ed1, col_ed2, col_ed3 = st.columns(3)
                new_y = col_ed1.number_input("Año", value=c_data[2])
                new_tp = col_ed2.selectbox("Tipo de Encargo", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria"], 
                                          index=["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria"].index(c_data[3]) if c_data[3] in ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria"] else 0)
                new_es = col_ed3.selectbox("Estado Global", ["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"],
                                          index=["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"].index(c_data[4]) if c_data[4] in ["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"] else 0)
                
                if st.button("💾 Guardar Cambios"):
                    conn.execute("""UPDATE clients SET client_name=?, client_nit=?, audit_year=?, tipo_encargo=?, estado=? 
                                 WHERE id=?""", (new_n, new_t, new_y, new_tp, new_es, client_id))
                    conn.commit()
                    st.session_state.active_name = new_n
                    st.success("✅ Datos actualizados")
                    conn.close() # Cerramos antes de recargar
                    st.rerun()

        with col_ed_der:
            st.subheader("⚠️ Zona de Peligro")
            with st.container(border=True):
                st.write("Esta acción es irreversible.")
                confirmar_borrado = st.checkbox("Confirmo que deseo borrar todo")
                if st.button("🗑️ Eliminar este Encargo", type="secondary", disabled=not confirmar_borrado):
                    conn.execute("DELETE FROM step_files WHERE step_id IN (SELECT id FROM audit_steps WHERE client_id=?)", (client_id,))
                    conn.execute("DELETE FROM audit_steps WHERE client_id=?", (client_id,))
                    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                    conn.commit()
                    conn.close() # Cerramos antes de salir
                    if 'active_id' in st.session_state: del st.session_state['active_id']
                    st.rerun()
        st.markdown("---")

    # --- LISTADO DE PASOS NIA ---
    # Nota: Aquí la conexión 'conn' sigue abierta, evitando el ProgrammingError
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id = ? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    if steps.empty:
        if st.button("🔄 Cargar Programa NIA"): 
            inicializar_programa_auditoria(client_id)
            conn.close()
            st.rerun()
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
                            conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                            conn.commit()
                            st.toast("Guardado")
                    with c2:
                        nuevo_est = st.selectbox("Estado", ["Pendiente", "En Proceso", "Cerrado"], 
                                               index=["Pendiente", "En Proceso", "Cerrado"].index(row['status']), key=f"e_{sid}")
                        if nuevo_est != row['status']:
                            conn.execute("UPDATE audit_steps SET status=? WHERE id=?", (nuevo_est, sid))
                            conn.commit()
                            conn.close()
                            st.rerun()
                        up_file = st.file_uploader("Adjuntar", key=f"f_{sid}")
                        if up_file:
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data, file_type) VALUES (?,?,?,?)", 
                                         (sid, up_file.name, up_file.read(), up_file.type))
                            conn.commit()
                            conn.close()
                            st.rerun()
                        
                        # Mostrar archivos para descargar
                        files = pd.read_sql_query("SELECT id, file_name, file_data FROM step_files WHERE step_id=?", conn, params=(sid,))
                        for _, f in files.iterrows():
                            st.download_button(f"⬇️ {f['file_name']}", f['file_data'], f['file_name'], key=f"d_{f['id']}")
    
    conn.close() # Cierre final de seguridad

# --- VISTA: PRINCIPAL (ENCARGOS) ---
def vista_principal():
    with st.sidebar:
        st.title(f"👨‍💼 {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        c_n = st.text_input("Empresa"); c_t = st.text_input("NIT")
        
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
    
    if 'active_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
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

# --- INICIO DE LA APLICACIÓN ---
if __name__ == "__main__":
    if 'user_id' not in st.session_state:
        vista_login()
    else:
        vista_principal()






