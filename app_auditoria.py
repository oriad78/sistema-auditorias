import hashlib
import io
import sqlite3
import pandas as pd
import streamlit as st
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="AuditPro - Papeles de Trabajo", layout="wide")

# --- ESTILOS CSS PERSONALIZADOS (Para que se parezca a la imagen) ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 16px; }
    .section-header { background-color: #f0f2f6; padding: 5px; font-weight: bold; border-left: 5px solid #004080; }
    .stTextArea textarea { background-color: #fffef0; } /* Color nota amarilla tipo post-it */
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN Y BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla Usuarios
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE, full_name TEXT, password_hash TEXT)''')
    
    # Tabla Clientes (Encargos)
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        client_name TEXT, client_nit TEXT, audit_year INTEGER,
        tipo_encargo TEXT, estado TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # NUEVA TABLA: Pasos de Auditoría (El "Programa de Trabajo")
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        section_name TEXT,      -- Ej: Aceptación/continuación
        step_code TEXT,         -- Ej: 1000, 2000
        description TEXT,       -- El texto rojo de la imagen
        instructions TEXT,      -- Guía o Template oculto
        user_notes TEXT,        -- Lo que escribe el auditor
        status TEXT DEFAULT 'Pendiente',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE)''')

    # NUEVA TABLA: Archivos Adjuntos (Evidencias)
    cursor.execute('''CREATE TABLE IF NOT EXISTS step_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step_id INTEGER,
        file_name TEXT,
        file_data BLOB,
        file_type TEXT,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(step_id) REFERENCES audit_steps(id) ON DELETE CASCADE)''')

    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES DE LÓGICA ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Función para INICIALIZAR los pasos de la imagen cuando se crea un cliente nuevo
def inicializar_programa_auditoria(client_id):
    pasos_template = [
        # SECCIÓN 100: Aceptación
        ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente, incorporar el resumen y actualizar.", "Instrucciones: Revise la integridad de la gerencia y si el equipo tiene la competencia necesaria."),
        ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP (Quality Review Partner).", "Instrucciones: Determine si es una entidad de interés público."),
        ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Considerar el cumplimiento de requisitos éticos e independencia.", "Instrucciones: Llenar formulario de independencia de la firma."),
        ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Asegurarse de que la carta de contratación esté actualizada y firmada.", "Instrucciones: Adjuntar Carta de Encargo firmada."),
        
        # SECCIÓN 150: Administración
        ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo.", "Instrucciones: Asignar roles y cronograma en el sistema."),
        ("150 - Administración del proyecto", "3000", "(ISA 300) Preparar y monitorear el avance con relación al plan del proyecto.", "Instrucciones: Reunión de planeación."),

        # SECCIÓN 1100: Comprensión
        ("1100 - Comprensión del cliente y de la industria", "1000", "(ISA 315) Obtener o actualizar la comprensión del cliente y el ambiente en el que opera.", "Instrucciones: Documentar marco regulatorio y naturaleza de la entidad."),
        ("1100 - Comprensión del cliente y de la industria", "1500", "(ISA 315, ISA 520) Realizar procedimientos de revisión analítica preliminares.", "Instrucciones: Comparativo año actual vs anterior.")
    ]
    
    conn = get_db_connection()
    for seccion, codigo, desc, instr in pasos_template:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)",
                     (client_id, seccion, codigo, desc, instr))
    conn.commit()
    conn.close()

# --- VISTA: DETALLE DE AUDITORÍA (PAPELES DE TRABAJO) ---
def vista_papeles_trabajo(client_id, client_name):
    st.markdown(f"## 📂 Papeles de Trabajo: {client_name}")
    
    if st.button("⬅️ Volver al Panel Principal"):
        del st.session_state['active_client_id']
        st.rerun()

    conn = get_db_connection()
    
    # Obtener pasos
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id = ? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    if steps.empty:
        st.warning("⚠️ Este encargo no tiene programa de auditoría cargado.")
        if st.button("🔄 Cargar Programa Estándar (NIA/ISA)"):
            inicializar_programa_auditoria(client_id)
            st.rerun()
    else:
        # Agrupar por secciones (Como en la imagen: 100, 150, etc.)
        secciones = steps['section_name'].unique()
        
        for seccion in secciones:
            with st.expander(f"📁 {seccion}", expanded=True):
                pasos_seccion = steps[steps['section_name'] == seccion]
                
                for _, row in pasos_seccion.iterrows():
                    step_id = row['id']
                    
                    # Estructura visual del paso (Rojo como pediste)
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    
                    # Contenedor del trabajo (simulando documento)
                    c1, c2 = st.columns([3, 1])
                    
                    with c1:
                        # 1. Instrucciones ocultables (Template)
                        with st.expander("📘 Ver Guía / Template del Procedimiento"):
                            st.info(row['instructions'])
                        
                        # 2. Espacio de trabajo (Word-like simple)
                        notas = st.text_area(f"📝 Desarrollo del paso {row['step_code']}", 
                                           value=row['user_notes'] if row['user_notes'] else "",
                                           height=150,
                                           key=f"note_{step_id}",
                                           placeholder="Escriba aquí el desarrollo del procedimiento, conclusiones, o inserte viñetas...")
                        
                        if st.button(f"💾 Guardar Nota {row['step_code']}", key=f"btn_save_{step_id}"):
                            conn.execute("UPDATE audit_steps SET user_notes = ? WHERE id = ?", (notas, step_id))
                            conn.commit()
                            st.toast("Nota guardada", icon="✅")

                    with c2:
                        # 3. Estado del paso
                        st.caption("Estado:")
                        estado_actual = row['status']
                        nuevo_estado = st.selectbox("", ["Pendiente", "En Proceso", "Revisado", "Cerrado"], 
                                                  index=["Pendiente", "En Proceso", "Revisado", "Cerrado"].index(estado_actual),
                                                  key=f"status_{step_id}", label_visibility="collapsed")
                        
                        if nuevo_estado != estado_actual:
                            conn.execute("UPDATE audit_steps SET status = ? WHERE id = ?", (nuevo_estado, step_id))
                            conn.commit()
                            st.rerun()

                        # 4. Adjuntos (Archivos)
                        st.divider()
                        st.caption("📎 Evidencias (Word, Excel, PDF)")
                        uploaded_file = st.file_uploader("", type=['docx', 'xlsx', 'pdf', 'jpg', 'png'], key=f"file_{step_id}", label_visibility="collapsed")
                        
                        if uploaded_file:
                            binary_data = uploaded_file.read()
                            conn.execute("INSERT INTO step_files (step_id, file_name, file_data, file_type) VALUES (?, ?, ?, ?)",
                                         (step_id, uploaded_file.name, binary_data, uploaded_file.type))
                            conn.commit()
                            st.toast("Archivo adjunto", icon="📎")
                            st.rerun()

                        # Listar archivos existentes
                        files = pd.read_sql_query("SELECT id, file_name, file_data FROM step_files WHERE step_id = ?", conn, params=(step_id,))
                        if not files.empty:
                            for _, f_row in files.iterrows():
                                st.download_button(f"⬇️ {f_row['file_name']}", data=f_row['file_data'], file_name=f_row['file_name'], key=f"dl_{f_row['id']}")

                    st.markdown("---") # Separador entre pasos
    
    conn.close()

# --- VISTA PRINCIPAL (MODIFICADA PARA IR AL DETALLE) ---
def vista_principal():
    with st.sidebar:
        st.title(f"👨‍💼 Auditor: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()
        
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        c_name = st.text_input("Nombre Cliente")
        c_nit = st.text_input("NIT")
        c_year = st.number_input("Año", value=2025)
        c_tipo = st.selectbox("Tipo", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Interna"])
        
        if st.button("Crear Encargo"):
            if c_name and c_nit:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO clients (user_id, client_name, client_nit, audit_year, tipo_encargo, estado) VALUES (?,?,?,?,?,?)",
                             (st.session_state.user_id, c_name, c_nit, c_year, c_tipo, "🔴 Pendiente"))
                new_client_id = cur.lastrowid # Obtenemos el ID del nuevo cliente
                conn.commit()
                conn.close()
                
                # AUTOMÁTICAMENTE CARGAMOS LA ESTRUCTURA DE LA IMAGEN
                inicializar_programa_auditoria(new_client_id)
                
                st.success("Encargo creado con programa de auditoría base.")
                st.rerun()

    # Si hay un cliente seleccionado, mostramos sus papeles de trabajo
    if 'active_client_id' in st.session_state:
        vista_papeles_trabajo(st.session_state.active_client_id, st.session_state.active_client_name)
    else:
        # PANTALLA DE LISTADO (DASHBOARD)
        st.image("https://cdn-icons-png.flaticon.com/512/2645/2645853.png", width=80) 
        st.title("📊 Panel de Control de Auditorías")
        
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, client_name, client_nit, audit_year, estado FROM clients WHERE user_id = ? ORDER BY created_at DESC", 
                               conn, params=(st.session_state.user_id,))
        conn.close()

        if not df.empty:
            for _, row in df.iterrows():
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                    with col1: st.subheader(f"🏢 {row['client_name']}")
                    with col2: st.caption(f"NIT: {row['client_nit']}")
                    with col3: st.caption(f"Estado: {row['estado']}")
                    with col4:
                        # ESTE BOTÓN ABRE EL EXPEDIENTE DETALLADO
                        if st.button(f"📂 Abrir Expediente", key=f"open_{row['id']}"):
                            st.session_state.active_client_id = row['id']
                            st.session_state.active_client_name = row['client_name']
                            st.rerun()
                    st.divider()
        else:
            st.info("No tienes encargos activos. Crea uno en la barra lateral.")

# --- LOGIN (SIN CAMBIOS) ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    with t1:
        e = st.text_input("Correo", key="log_user")
        p = st.text_input("Clave", type="password", key="log_pass")
        if st.button("Entrar"):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u:
                st.session_state.user_id = u[0]
                st.session_state.user_name = u[1]
                st.rerun()
            else: st.error("Datos incorrectos")
    with t2:
        n = st.text_input("Nombre")
        em = st.text_input("Email Reg")
        ps = st.text_input("Clave Reg", type="password")
        if st.button("Registrar"):
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (em, n, hash_pass(ps)))
                conn.commit()
                st.success("Registrado. Ahora ingresa.")
            except: st.error("Error al registrar.")

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
