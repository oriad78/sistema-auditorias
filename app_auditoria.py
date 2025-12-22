import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Gestión de Carpetas", layout="wide")

# --- ESTILOS CSS PARA MEJORAR LA VISTA ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 15px; margin-top: 5px; }
    .stTextArea textarea { background-color: #fffef0; border: 1px solid #ddd; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

# --- PLANTILLA MAESTRA AGRUPADA POR CARPETAS ---
# Formato: (Nombre de Carpeta, Código, Descripción, Instrucciones)
TEMPLATE_AUDITORIA = [
    # CARPETA: 100 - Aceptación y continuación de clientes
    ("100 - Aceptación y continuación de clientes", "1000", "(ISA 220, 300) Evaluar la aceptación/continuación del cliente, incorporar el resumen y actualizar en función de los acontecimientos", "Revisar la integridad de la gerencia."),
    ("100 - Aceptación y continuación de clientes", "2000", "(ISA 220) Considerar la necesidad de designar a un QRP (Quality Review Partner)", "Evaluar entidades de interés público."),
    ("100 - Aceptación y continuación de clientes", "4000", "(ISA 200, 220, 300) Considerar el cumplimiento de requisitos éticos e independencia", "Preparar/aprobar el resumen de independencia."),
    ("100 - Aceptación y continuación de clientes", "4010", "Realizar otras tareas específicas relativas a independencia", "Verificar servicios adicionales."),
    ("100 - Aceptación y continuación de clientes", "5000", "(ISA 210, 300) Asegurarse de que la carta de contratación esté actualizada y firmada", "Confirmar términos del trabajo."),
    ("100 - Aceptación y continuación de clientes", "1200", "(ISA 600) Participación en la auditoría del grupo", "Evaluación de auditoría multilocal."),
    
    # CARPETA: 150 - Administración del proyecto
    ("150 - Administración del proyecto", "1000", "(ISA 300) Movilizar al equipo de trabajo", "Asignación de personal."),
    ("150 - Administración del proyecto", "3000", "(ISA 300) Preparar y monitorear el avance con relación al plan del proyecto", "Control de cronograma."),
    ("150 - Administración del proyecto", "2000", "Discutir y acordar objetivos de desarrollo personal para todos los miembros del equipo", "Reunión de equipo."),

    # CARPETA: 1100 - Comprensión del cliente y de la industria
    ("1100 - Comprensión del cliente y de la industria", "1000", "(ISA 315) Obtener o actualizar la comprensión del cliente y el ambiente en el que opera", "Análisis de entorno."),
    ("1100 - Comprensión del cliente y de la industria", "1500", "(ISA 315, ISA 520) Realizar procedimientos de revisión analítica preliminares", "Variaciones significativas."),
    ("1100 - Comprensión del cliente y de la industria", "3000", "Revisar las actas de reuniones y asambleas y obtener nuevos contratos", "Lectura de actas."),

    # CARPETA: 1250 - Evaluación del riesgo de fraude
    ("1250 - Evaluación del riesgo de fraude", "1000", "(ISA 240, ISA 315) Evaluar y responder al riesgo de fraude", "Triángulo del fraude."),
    ("1250 - Evaluación del riesgo de fraude", "2000", "Considerar la necesidad de usar especialistas en fraude/asesores legales", "Consultoría experta."),

    # CARPETA: 1700 - Evaluación del riesgo/significatividad
    ("1700 - Evaluación del riesgo/significatividad", "2000", "(ISA 250, ISA 315) Obtener comprensión de leyes y reglamentaciones", "Riesgo de incumplimiento legal.")
]

def inicializar_programa_auditoria(client_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM audit_steps WHERE client_id = ?", (client_id,))
    for carpeta, codigo, desc, instr in TEMPLATE_AUDITORIA:
        conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?)", 
                     (client_id, carpeta, codigo, desc, instr))
    conn.commit()
    conn.close()

def vista_papeles_trabajo(client_id, client_name):
    conn = get_db_connection()
    st.markdown(f"## 📂 Expediente: {client_name}")
    
    # Botón para volver y Configuración
    col1, col2 = st.columns([1, 5])
    if col1.button("⬅️ Volver"): del st.session_state.active_id; st.rerun()
    editar = col2.toggle("⚙️ Configurar Encargo")

    if editar:
        if st.button("🔄 Sincronizar Pasos (Cargar Carpetas)"):
            inicializar_programa_auditoria(client_id)
            st.success("Carpetas actualizadas")
            st.rerun()

    # --- VISTA DE CARPETAS EXPANDIBLES (Como la imagen) ---
    steps_df = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    if steps_df.empty:
        st.warning("No hay pasos cargados. Ve a 'Configurar Encargo' y presiona 'Sincronizar'.")
    else:
        # Agrupamos por el nombre de la carpeta (section_name)
        for carpeta in steps_df['section_name'].unique():
            with st.expander(f"📁 {carpeta}", expanded=True):
                # Filtramos los pasos que pertenecen a esta carpeta
                pasos_carpeta = steps_df[steps_df['section_name'] == carpeta]
                for _, row in pasos_carpeta.iterrows():
                    sid = row['id']
                    st.markdown(f"<div class='step-header'>🚩 {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                    
                    # Espacio para trabajo
                    notas = st.text_area("Desarrollo del paso", value=row['user_notes'] or "", key=f"nt_{sid}")
                    if st.button("💾 Guardar", key=f"btn_{sid}"):
                        conn.execute("UPDATE audit_steps SET user_notes=? WHERE id=?", (notas, sid))
                        conn.commit()
                        st.toast(f"Paso {row['step_code']} guardado")
    conn.close()

# --- LÓGICA DE INICIO (Simplificada para el ejemplo) ---
if __name__ == "__main__":
    # Simulación de estado de sesión para pruebas
    if 'active_id' not in st.session_state:
        st.title("Gestión de Auditoría")
        if st.button("Abrir Encargo de Ejemplo"):
            st.session_state.active_id = 1
            st.session_state.active_name = "Empresa ABC SAS"
            st.rerun()
    else:
        vista_papeles_trabajo(st.session_state.active_id, st.session_state.active_name)
