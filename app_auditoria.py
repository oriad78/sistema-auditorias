import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { color: #d32f2f; font-weight: bold; font-size: 16px; margin-bottom: 5px; }
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 12px; 
        margin-bottom: 15px; 
        border-radius: 5px;
        font-size: 13px;
        color: #0d47a1;
    }
    .status-ball { font-size: 18px; margin-right: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Sin Iniciar")')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULO: MATERIALIDAD ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Determinación de la Materialidad")
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            benchmark = st.selectbox("Base (Benchmark)", ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"],
                index=0 if not datos else ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"].index(datos[1]))
            valor_base = st.number_input("Valor Base ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR (Ajustes)", 0.0, 10.0, datos[7] if datos else 5.0)

        m_gen, m_perf, m_ranr = valor_base*(p_gen/100), (valor_base*(p_gen/100))*(p_perf/100), (valor_base*(p_gen/100))*(p_ranr/100)

    res1, res2, res3 = st.columns(3)
    res1.metric("Mat. General", f"$ {m_gen:,.2f}")
    res2.metric("Mat. Desempeño", f"$ {m_perf:,.2f}")
    res3.metric("Límite RANR", f"$ {m_ranr:,.2f}")

    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Guardado")

# --- MÓDULO: PROGRAMA DE TRABAJO (MEJORADO) ---
def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo y Ejecución")
    
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name", conn, params=(client_id,))
    
    # Diccionario de bolitas de colores
    iconos_estado = {
        "Sin Iniciar": "🔴",
        "En Proceso": "🟡",
        "Terminado": "🟢"
    }

    for seccion in steps['section_name'].unique():
        with st.expander(f"📁 SECCIÓN: {seccion}", expanded=True):
            pasos_seccion = steps[steps['section_name'] == seccion]
            for _, row in pasos_seccion.iterrows():
                sid = row['id']
                estado_actual = row['status'] or "Sin Iniciar"
                
                # Encabezado con bolita y título
                st.markdown(f"<div class='step-header'>{iconos_estado.get(estado_actual)} {row['step_code']} - {row['description']}</div>", unsafe_allow_html=True)
                
                # Guía técnica (Instrucciones)
                if row['instructions']:
                    st.markdown(f"""<div class='instruction-box'><b>📘 Guía del Auditor:</b><br>{row['instructions']}</div>""", unsafe_allow_html=True)
                
                col_n, col_e = st.columns([3, 1])
                with col_n:
                    notas = st.text_area("Hallazgos y Conclusiones", value=row['user_notes'] or "", key=f"note_{sid}", placeholder="Escriba aquí la evidencia encontrada...")
                with col_e:
                    nuevo_estado = st.selectbox("Estado", ["Sin Iniciar", "En Proceso", "Terminado"], 
                                                index=["Sin Iniciar", "En Proceso", "Terminado"].index(estado_actual), key=f"est_{sid}")
                
                # Botón de guardar para este paso específico
                if st.button("Actualizar Paso", key=f"btn_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (notas, nuevo_estado, sid))
                    conn.commit()
                    st.success("Paso actualizado")
                    st.rerun()
                st.divider()
    conn.close()

# --- VISTA: EXPEDIENTE ---
def vista_expediente(client_id, client_name):
    c_t, c_v = st.columns([5, 1])
    c_t.title(f"📂 Expediente: {client_name}")
    if c_v.button("⬅️ Volver"):
        del st.session_state.active_id; st.rerun()

    if 'current_module' not in st.session_state: st.session_state.current_module = "Materialidad"

    # Navegación
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    if m1.button("📊 Materialidad", use_container_width=True): st.session_state.current_module = "Materialidad"
    if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.current_module = "Programa"
    if m3.button("📥 Exportar Datos", use_container_width=True): st.session_state.current_module = "Exportar"
    st.markdown("---")

    if st.session_state.current_module == "Materialidad":
        modulo_materialidad(client_id)
    elif st.session_state.current_module == "Programa":
        modulo_programa_trabajo(client_id)
    else:
        st.info("Módulo en desarrollo...")

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Salir"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Crear Cliente")
        name = st.text_input("Empresa"); nit = st.text_input("NIT")
        if st.button("Registrar Cliente"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, name, nit))
            cid = cur.lastrowid
            # Pasos iniciales con GUÍA técnica incorporada
            pasos_iniciales = [
                ("Planeación", "P-1", "Entendimiento de la Entidad", "Realizar entrevista con la gerencia y revisar actas de asamblea para identificar riesgos de negocio (NIA 315)."),
                ("Planeación", "P-2", "Confirmación de Independencia", "Firmar declaración de independencia de todo el equipo de auditoría (NIA 220)."),
                ("Caja y Bancos", "E-1", "Circularización de Bancos", "Enviar solicitudes de confirmación a todas las entidades financieras con las que el cliente tuvo relación en el año (NIA 505).")
            ]
            for sec, cod, desc, ins in pasos_iniciales:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions) VALUES (?,?,?,?,?)", (cid, sec, cod, desc, ins))
            conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        vista_expediente(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Auditorías")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** - NIT: {r['client_nit']}")
                if c2.button("Abrir", key=f"op_{r['id']}"):
                    st.session_state.active_id = r['id']; st.session_state.active_name = r['client_name']; st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.title("⚖️ AuditPro")
    e, p = st.text_input("Correo"), st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
        else: st.error("Credenciales inválidas")
    if st.button("Crear Usuario"):
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, "Usuario Nuevo", hash_pass(p)))
            conn.commit(); st.success("Creado")
        except: st.error("El correo ya existe")
        finally: conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
