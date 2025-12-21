import hashlib
import io
import re
import sqlite3
import pandas as pd
import streamlit as st
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="AuditPro - Gestión Contable Inteligente", layout="wide")

# --- CONEXIÓN Y BASE DE DATOS ---
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
    conn.commit()
    conn.close()

create_tables()

# --- FUNCIONES DE LÓGICA ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def buscar_nit_historico(nombre, user_id):
    if not nombre or len(nombre) < 3: return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT client_nit FROM clients 
                      WHERE user_id = ? AND client_name LIKE ? 
                      ORDER BY created_at DESC LIMIT 1''', (user_id, f"%{nombre}%"))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# --- EXPORTACIONES ---
def generar_pdf(df, auditor):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, "REPORTE DE GESTION DE AUDITORIA", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(190, 10, f"Auditor: {auditor}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", 'B', 9)
    cols = ["Cliente", "NIT", "Año", "Tipo", "Estado"]
    widths = [60, 35, 15, 45, 35]
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 10, col, 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 8)
    for _, row in df.iterrows():
        pdf.cell(widths[0], 10, str(row['Cliente'])[:30], 1)
        pdf.cell(widths[1], 10, str(row['NIT']), 1)
        pdf.cell(widths[2], 10, str(row['Año']), 1)
        pdf.cell(widths[3], 10, str(row['Tipo']), 1)
        pdf.cell(widths[4], 10, str(row['Estado']), 1)
        pdf.ln()
    return bytes(pdf.output())

# --- VISTA: LOGIN ---
def vista_login():
    st.title("⚖️ AuditPro: Sistema para Contadores")
    t1, t2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrar Auditor"])
    
    with t1:
        e = st.text_input("Correo electrónico", key="login_user")
        p = st.text_input("Contraseña", type="password", key="login_pwd")
        if st.button("Ingresar"):
            conn = get_db_connection()
            u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
            conn.close()
            if u:
                st.session_state.user_id, st.session_state.user_name = u[0], u[1]
                st.rerun()
            else: st.error("Credenciales incorrectas")

    with t2:
        n = st.text_input("Nombre Completo")
        em = st.text_input("Correo Institucional")
        ps = st.text_input("Clave", type="password")
        ps_c = st.text_input("Confirmar Clave", type="password")
        if st.button("Crear mi cuenta"):
            if ps != ps_c: st.error("Las claves no coinciden")
            else:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (em, n, hash_pass(ps)))
                    conn.commit()
                    conn.close()
                    st.success("¡Registro exitoso!")
                except: st.error("El correo ya existe")

# --- VISTA: APLICACIÓN PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.title(f"👨‍💼 Auditor: {st.session_state.user_name}")
        if st.button("Cerrar Sesión"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.divider()
        st.subheader("➕ Nuevo Encargo")
        
        c_name = st.text_input("Nombre de la Empresa", placeholder="Ej: Inversiones S.A.S.")
        
        sugerencia = buscar_nit_historico(c_name, st.session_state.user_id)
        val_nit = ""
        if sugerencia:
            st.info(f"💡 Historial: NIT {sugerencia}")
            if st.button("Usar NIT sugerido"):
                st.session_state.temp_nit = sugerencia
            val_nit = st.session_state.get('temp_nit', "")

        c_nit = st.text_input("NIT (Con puntos y guión)", value=val_nit, placeholder="900.000.000-0")
        
        # --- CONSULTAS OFICIALES CON COLOR AZUL ---
        st.caption("Consultas oficiales (se abren en otra pestaña):")
        col_c1, col_c2 = st.columns(2)
        # Se mantiene la estructura de Markdown para conservar el color azul de los links
        col_c1.markdown("[🔍 RUES Avanzado](https://www.rues.org.co/busqueda-avanzada)", unsafe_allow_html=True)
        col_c2.markdown("[🔍 DIAN (RUT)](https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces)", unsafe_allow_html=True)
        
        c_year = st.number_input("Año Fiscal", value=2025)
        c_tipo = st.selectbox("Tipo de Auditoría", ["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Auditoría Interna", "Due Diligence"])
        c_estado = st.selectbox("Estado del Trabajo", ["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"])
        
        if st.button("💾 Registrar Encargo"):
            if c_name and c_nit:
                conn = get_db_connection()
                conn.execute("INSERT INTO clients (user_id, client_name, client_nit, audit_year, tipo_encargo, estado) VALUES (?,?,?,?,?,?)",
                             (st.session_state.user_id, c_name, c_nit, c_year, c_tipo, c_estado))
                conn.commit()
                conn.close()
                if 'temp_nit' in st.session_state: del st.session_state.temp_nit
                st.success("Encargo guardado")
                st.rerun()
            else: st.warning("Nombre y NIT son obligatorios")

    # --- PANEL CENTRAL ---
    st.image("https://cdn-icons-png.flaticon.com/512/2645/2645853.png", width=80) 
    st.title("📊 Panel de Control de Auditorías")
    
    query = st.text_input("🔍 Buscador inteligente por NIT o Empresa", placeholder="Escriba para filtrar...")
    
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT id, client_name as 'Cliente', client_nit as 'NIT', 
        audit_year as 'Año', tipo_encargo as 'Tipo', estado as 'Estado' 
        FROM clients WHERE user_id = ? ORDER BY created_at DESC""", 
        conn, params=(st.session_state.user_id,))
    conn.close()

    if query:
        df = df[df['Cliente'].str.contains(query, case=False, na=False) | df['NIT'].str.contains(query, case=False, na=False)]

    if not df.empty:
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.download_button("📥 Exportar Excel", data=df.to_csv(index=False).encode('utf-8'), file_name="encargos.csv")
        with col_r2:
            st.download_button("📥 Exportar PDF", data=generar_pdf(df, st.session_state.user_name), file_name="reporte.pdf")

        st.divider()
        st.subheader("⚡ Gestión de Avances")
        df_edit = df.copy()
        df_edit.insert(0, "🗑️", False)
        
        res_tabla = st.data_editor(
            df_edit,
            column_config={
                "id": None,
                "Estado": st.column_config.SelectboxColumn("Estado Actual", options=["🔴 Pendiente", "🟡 En Ejecución", "🟢 Finalizado"]),
                "Tipo": st.column_config.SelectboxColumn("Tipo de Auditoría", options=["Revisoría Fiscal", "Auditoría Externa", "Auditoría Tributaria", "Auditoría Interna", "Due Diligence"])
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("💾 Sincronizar Cambios"):
            conn = get_db_connection()
            for _, row in res_tabla.iterrows():
                conn.execute("UPDATE clients SET estado=?, tipo_encargo=? WHERE id=?", (row['Estado'], row['Tipo'], row['id']))
            conn.commit()
            conn.close()
            st.success("¡Base de datos actualizada!")
            st.rerun()

        ids_borrar = res_tabla[res_tabla["🗑️"] == True]["id"].tolist()
        if ids_borrar:
            if st.button(f"❌ Eliminar {len(ids_borrar)} seleccionados", type="primary"):
                conn = get_db_connection()
                conn.execute(f"DELETE FROM clients WHERE id IN ({','.join(['?']*len(ids_borrar))})", ids_borrar)
                conn.commit()
                conn.close()
                st.rerun()
    else:
        st.info("No hay registros para mostrar.")

# --- INICIO ---
if __name__ == "__main__":
    if 'user_id' not in st.session_state:
        vista_login()
    else:
        vista_principal()
